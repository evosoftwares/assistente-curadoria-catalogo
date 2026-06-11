"""Testes do coletor de FEEDBACK (POST /feedback) — sem LLM/sem rede.

Travam o contrato do 1º passo do loop v2: persistência em JSON-LINES (1 linha JSON
autossuficiente por evento — o que os consumidores de dataset parseiam sem estado),
validação/sanitização de entrada (anti-DoS, mesma postura do /ask) e resposta {ok: true}.
Rode com:  python -m pytest -q
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import api, config
from app.llm import GeminiClient
from app.pipeline import AskPipeline


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "RATE_LIMIT_RPM", 0)        # foco no contrato, não no limite
    monkeypatch.setattr(config, "DAILY_COST_CAP_USD", 0.0)
    monkeypatch.setattr(config, "FEEDBACK_PATH", tmp_path / "feedback.jsonl")  # nunca o real
    api._rate.clear(); api._spent_usd = 0.0; api._cost_day = None
    with TestClient(api.app, raise_server_exceptions=False) as c:
        api._state["pipeline"] = AskPipeline(client=GeminiClient(api_key=""))  # degradado
        yield c


def _payload(**over) -> dict:
    base = {
        "verdict": "up",
        "question": "Quais livros temos sobre IA?",
        "answer": "Temos X (BK0001).",
        "behavior": "answer",
        "reference_ids": ["BK0001"],
        "retrieved_ids": ["BK0001", "BK0002"],
        "context_ids": ["BK0001", "BK0002"],
        "plan_json": '{"source": "fallback"}',
        "cost_usd": 0.001,
        "latency_ms": 1234.5,
        "from_cache": False,
    }
    base.update(over)
    return base


def test_feedback_persiste_jsonl(client):
    assert client.post("/feedback", json=_payload()).status_code == 200
    assert client.post("/feedback",
                       json=_payload(verdict="down", comment="faltou o ano")).status_code == 200
    linhas = config.FEEDBACK_PATH.read_text(encoding="utf-8").strip().splitlines()
    assert len(linhas) == 2                       # 1 evento = 1 linha (append-only)
    rec = json.loads(linhas[1])                   # cada linha é JSON autossuficiente
    assert rec["verdict"] == "down" and rec["comment"] == "faltou o ano"
    assert rec["question"].startswith("Quais") and "ts" in rec
    assert rec["reference_ids"] == ["BK0001"]     # o par pergunta+resposta+contexto completo


def test_feedback_valida_verdict(client):
    # Literal["up","down"]: qualquer outro valor é rejeitado pelo schema (422), não gravado.
    assert client.post("/feedback", json=_payload(verdict="talvez")).status_code == 422
    assert not config.FEEDBACK_PATH.exists()


def test_feedback_limita_tamanhos(client):
    # Bounds anti-DoS: comentário e plano serializado têm teto — corpo gigante não persiste.
    assert client.post("/feedback", json=_payload(comment="x" * 1001)).status_code == 422
    assert client.post("/feedback", json=_payload(plan_json="x" * 4001)).status_code == 422


def test_feedback_sanitiza_controle_e_invisiveis(client):
    # Mesma sanitização do /ask (COMP-06): zero-width (U+200B) e controle (U+0000) não
    # entram no dataset. Escapes explícitos no fonte: arquivo .py permanece ASCII-são.
    sujo = "fal\u200btou\u0000 contexto"
    r = client.post("/feedback", json=_payload(comment=sujo))
    assert r.status_code == 200
    rec = json.loads(config.FEEDBACK_PATH.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert rec["comment"] == "faltou contexto"
