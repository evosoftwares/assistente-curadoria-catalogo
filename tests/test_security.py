"""Testes da camada de SEGURANÇA e dos fixes da auditoria v3 (sem Gemini/sem rede).

Travam regressões nas defesas: rate limit (e anti-bypass de XFF), teto de custo, sanitização
(controle + Unicode invisível), evicção de cache, dedup de citações, gating do cache semântico,
e handler global de exceção (não vaza stack). Rode com:  python -m pytest -q
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import api, config
from app.llm import GeminiClient
from app.models import AskRequest
from app.pipeline import AskPipeline, _cacheable, _coerce_id_list


# ---------- unidade (sem HTTP) ----------
def test_coerce_id_list_dedup_e_tipo():
    assert _coerce_id_list(["BK0001", "BK0001", "BK0002"]) == ["BK0001", "BK0002"]  # dedup, ordem
    assert _coerce_id_list("BK0133") == ["BK0133"]            # string vira [string]
    assert _coerce_id_list([1, "BK0001", None]) == ["BK0001"]  # descarta não-strings


def test_cacheable_pula_numero_e_negacao():
    assert _cacheable("livros sobre liderança de equipes") is True
    assert _cacheable("livros publicados após 2015") is False     # número/data
    assert _cacheable("livros NÃO infantis") is False             # negação
    assert _cacheable("livros sem ilustração") is False           # negação


def test_sanitizacao_remove_controle_e_invisivel():
    # \x00/\x07 (controle), ​ (zero-width), ‮ (bidi override) devem sumir; \n preservado.
    r = AskRequest(question="  liv\x00ro​ sobre‮ cérebro\x07  ")
    assert r.question == "livro sobre cérebro"
    assert "​" not in r.question and "‮" not in r.question


def test_client_ip_ignora_xff_sem_proxy(monkeypatch):
    monkeypatch.setattr(config, "TRUST_PROXY", False)
    req = type("R", (), {"client": type("C", (), {"host": "10.0.0.1"})(),
                         "headers": {"x-forwarded-for": "9.9.9.9"}})()
    assert api._client_ip(req) == "10.0.0.1"          # XFF forjado é ignorado -> usa o socket
    monkeypatch.setattr(config, "TRUST_PROXY", True)
    assert api._client_ip(req) == "9.9.9.9"           # com proxy confiável, respeita o XFF


def test_cache_eviccao_limitada(monkeypatch):
    monkeypatch.setattr(config, "MAX_CACHE_ENTRIES", 5)
    pipe = AskPipeline(client=GeminiClient(api_key=""))   # degradado (sem Gemini)
    for i in range(9):
        pipe.ask(f"pergunta unica numero {i} sobre tema distinto {i}")
    assert len(pipe._cache) <= 5                          # FIFO limitou o cache


# ---------- HTTP (TestClient, pipeline degradado injetado) ----------
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_RPM", 2)
    monkeypatch.setattr(config, "DAILY_COST_CAP_USD", 0.0)   # desliga o teto p/ testar rate limit
    api._rate.clear(); api._spent_usd = 0.0; api._cost_day = None  # reset do estado de segurança
    with TestClient(api.app, raise_server_exceptions=False) as c:
        api._state["pipeline"] = AskPipeline(client=GeminiClient(api_key=""))  # degradado, sem custo
        yield c


def test_rate_limit_429(client):
    codes = [client.post("/ask", json={"question": f"pergunta {i} sobre livros"}).status_code
             for i in range(4)]
    assert codes == [200, 200, 429, 429]


def test_xff_spoof_nao_burla_rate_limit(client):
    codes = [client.post("/ask", json={"question": f"spoof {i} sobre livros"},
                         headers={"x-forwarded-for": f"9.9.9.{i}"}).status_code for i in range(4)]
    assert codes == [200, 200, 429, 429]   # IPs forjados não criam buckets distintos (TRUST_PROXY=false)


def test_validacao_rejeita_pergunta_curta(client):
    assert client.post("/ask", json={"question": "a"}).status_code == 422


def test_handler_nao_vaza_stacktrace(client, monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_RPM", 0)        # desliga rate limit p/ chegar no pipeline
    def boom(_q):
        raise ValueError("segredo-interno-xyz")
    api._state["pipeline"].ask = boom                       # força erro não-tratado no pipeline
    resp = client.post("/ask", json={"question": "qualquer pergunta válida"})
    assert resp.status_code == 500
    assert "segredo-interno-xyz" not in resp.text and "ValueError" not in resp.text  # sem leak
    assert "Erro interno" in resp.json()["detail"]
