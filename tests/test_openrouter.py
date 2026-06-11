"""Testes do ROTEAMENTO DE MODELOS (OpenRouter), do cache de chamadas LLM e do roteamento
inteligente por solicitação — 100% offline (httpx.MockTransport + monkeypatch, sem rede).

Travam os invariantes novos: seleção de backend (auto/openrouter/gemini), embedder sempre
Gemini, schema estrito OpenAI-compatível, payload de roteamento (models/fallback, provider,
usage.include, max_tokens), custo real via usage.cost, fallback sem response_format em 4xx,
cache de chamadas (2ª chamada idêntica não vai à rede) e tiers do roteamento inteligente.
Rode com:  python -m pytest -q
"""
from __future__ import annotations

import json

import httpx
import pytest

from app import config
from app import llm as llm_mod
from app.llm import (
    GeminiClient,
    LLMCache,
    OpenRouterClient,
    Usage,
    _extract_json_text,
    _strict_json_schema,
    get_client,
    get_embedder,
)
from app.models import AnswerOut, Behavior, PlannerLLMOutput
from app.pipeline import AskPipeline, route_generation_model


@pytest.fixture(autouse=True)
def _isolado(monkeypatch):
    """Cada teste parte limpo: singletons de cliente zerados e cache de chamadas vazio."""
    monkeypatch.setattr(llm_mod, "_client", None)
    monkeypatch.setattr(llm_mod, "_embedder", None)
    llm_mod._llm_cache.clear()
    yield
    llm_mod._llm_cache.clear()


def _mock_http(handler) -> httpx.Client:
    return httpx.Client(base_url=config.OPENROUTER_BASE_URL,
                        transport=httpx.MockTransport(handler))


def _resp(content: str, model: str = "google/gemini-2.5-flash",
          cost: float | None = 0.0001, in_tok: int = 50, out_tok: int = 20) -> dict:
    usage = {"prompt_tokens": in_tok, "completion_tokens": out_tok}
    if cost is not None:
        usage["cost"] = cost
    return {"model": model, "choices": [{"message": {"content": content}}], "usage": usage}


# ---------- helpers de JSON ----------
def test_strict_schema_fecha_objetos_e_exige_tudo():
    s = _strict_json_schema(PlannerLLMOutput)
    assert s["additionalProperties"] is False
    assert set(s["required"]) == set(s["properties"].keys())   # modo estrito: todas as props
    for d in (s.get("$defs") or {}).values():                  # sub-objetos também fechados
        if "properties" in d:
            assert d["additionalProperties"] is False
            assert set(d["required"]) == set(d["properties"].keys())
    assert '"default"' not in json.dumps(s)                    # keyword removida (estrito)


def test_extract_json_text_limpa_cercas_e_prosa():
    cercado = '```json\n{"answer": "ok", "cited_ids": []}\n```'
    assert json.loads(_extract_json_text(cercado)) == {"answer": "ok", "cited_ids": []}
    prosa = 'Claro! Aqui está: {"a": 1} — espero ter ajudado.'
    assert json.loads(_extract_json_text(prosa)) == {"a": 1}


# ---------- custo ----------
def test_usage_cost_override_precede_tabela():
    direto = Usage(model="gemini-2.5-flash", input_tokens=1_000_000, output_tokens=0)
    assert direto.cost_usd == pytest.approx(0.30)              # tabela (US$/Mtok)
    roteado = Usage(model="x", input_tokens=1_000_000, output_tokens=0, cost_override=0.07)
    assert roteado.cost_usd == pytest.approx(0.07)             # custo real da resposta vence


# ---------- seleção de backend ----------
def test_get_client_auto_usa_openrouter_quando_ha_chave(monkeypatch):
    monkeypatch.setattr(config, "LLM_BACKEND", "auto")
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "sk-or-teste")
    assert isinstance(get_client(), OpenRouterClient)


def test_get_client_auto_cai_no_gemini_sem_chave_or(monkeypatch):
    monkeypatch.setattr(config, "LLM_BACKEND", "auto")
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")
    assert isinstance(get_client(), GeminiClient)


def test_get_embedder_e_sempre_gemini(monkeypatch):
    monkeypatch.setattr(config, "LLM_BACKEND", "openrouter")
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "sk-or-teste")
    assert isinstance(get_client(), OpenRouterClient)   # chat roteado...
    assert isinstance(get_embedder(), GeminiClient)     # ...mas embeddings ficam no Gemini


# ---------- chamadas roteadas (mockadas) ----------
def test_generate_structured_payload_roteamento_e_custo_real(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_FALLBACK_MODELS", ["anthropic/claude-haiku-4.5"])
    monkeypatch.setattr(config, "OPENROUTER_SORT", "price")
    visto: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        visto["payload"] = json.loads(request.content.decode("utf-8"))
        visto["auth"] = request.headers.get("authorization")
        # o fallback atendeu: o campo model da RESPOSTA diz quem realmente serviu
        return httpx.Response(200, json=_resp(
            '{"answer": "Sim.", "cited_ids": ["BK0001"]}',
            model="anthropic/claude-haiku-4.5", cost=0.00042, in_tok=100, out_tok=20))

    cli = OpenRouterClient(api_key="sk-or-teste", http=_mock_http(handler))
    data, usage = cli.generate_structured("sys", "user", AnswerOut, model="google/gemini-2.5-flash")

    assert data == {"answer": "Sim.", "cited_ids": ["BK0001"]}
    p = visto["payload"]
    assert p["models"][0] == "google/gemini-2.5-flash"            # primário + fallback ordenados
    assert "anthropic/claude-haiku-4.5" in p["models"]
    assert p["response_format"]["json_schema"]["strict"] is True  # schema estrito
    assert p["provider"]["require_parameters"] is True            # só provedores que honram schema
    assert p["provider"]["sort"] == "price"                       # roteamento por preço
    assert p["usage"] == {"include": True}                        # pede o custo real na resposta
    assert p["max_tokens"] == config.LLM_MAX_OUTPUT_TOKENS        # teto de saída (bound de custo)
    assert visto["auth"] == "Bearer sk-or-teste"
    assert usage.model == "anthropic/claude-haiku-4.5"            # quem REALMENTE atendeu
    assert usage.cost_usd == pytest.approx(0.00042)               # custo real (override)


def test_fallback_sem_response_format_em_rejeicao_4xx():
    chamadas: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        chamadas.append(payload)
        if "response_format" in payload:   # provedor/modelo sem suporte a json_schema
            return httpx.Response(400, json={"error": {"message": "response_format not supported"}})
        return httpx.Response(200, json=_resp('```json\n{"answer": "ok", "cited_ids": []}\n```',
                                              cost=None))

    cli = OpenRouterClient(api_key="k", http=_mock_http(handler))
    data, usage = cli.generate_structured("s", "u", AnswerOut, model="m")
    assert data["answer"] == "ok"
    assert len(chamadas) == 2 and "response_format" not in chamadas[1]  # repetiu SEM o schema
    assert usage.cost_usd >= 0.0   # sem usage.cost -> estimativa pela tabela (não quebra)


def test_generate_text_as_json_limpa_cercas_para_o_juiz():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_resp('```json\n{"veredito": "CORRETA"}\n```'))

    cli = OpenRouterClient(api_key="k", http=_mock_http(handler))
    texto, _ = cli.generate_text("s", "u", model="m", as_json=True)
    assert json.loads(texto)["veredito"] == "CORRETA"   # judge.py faz json.loads direto


def test_indisponivel_sem_chave_levanta_runtime_error():
    cli = OpenRouterClient(api_key="")
    assert cli.available is False
    with pytest.raises(RuntimeError):
        cli.generate_structured("s", "u", AnswerOut)


# ---------- cache de CHAMADAS ----------
def test_cache_de_chamada_evita_segunda_ida_a_rede(monkeypatch):
    monkeypatch.setattr(config, "LLM_CACHE_ENABLED", True)
    n = {"chamadas": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        n["chamadas"] += 1
        return httpx.Response(200, json=_resp('{"answer": "x", "cited_ids": []}'))

    cli = OpenRouterClient(api_key="k", http=_mock_http(handler))
    d1, u1 = cli.generate_structured("sys-cache", "user-cache", AnswerOut, model="m")
    d2, u2 = cli.generate_structured("sys-cache", "user-cache", AnswerOut, model="m")
    assert n["chamadas"] == 1                      # 2ª chamada idêntica: respondida do cache
    assert d1 == d2
    assert u2.cached is True and u2.cost_usd == 0.0 and u2.input_tokens == 0
    assert u1.cached is False                      # a 1ª foi real (e pagou o custo)


def test_cache_chave_inclui_modelo_e_temperatura(monkeypatch):
    monkeypatch.setattr(config, "LLM_TEMPERATURE", 0.0)
    k1 = LLMCache.key("openrouter", "m1", "structured:X", "s", "u")
    k2 = LLMCache.key("openrouter", "m2", "structured:X", "s", "u")   # outro modelo
    monkeypatch.setattr(config, "LLM_TEMPERATURE", 0.7)
    k3 = LLMCache.key("openrouter", "m1", "structured:X", "s", "u")   # outra temperatura
    assert len({k1, k2, k3}) == 3


# ---------- roteamento inteligente por solicitação ----------
class _StubClient:
    light_model = "modelo-light"
    generation_model = "modelo-standard"
    heavy_model = "modelo-heavy"


def test_roteamento_inteligente_tiers(monkeypatch):
    monkeypatch.setattr(config, "SMART_ROUTING", True)
    c = _StubClient()
    livro = {"id": "BK0001"}
    # narrar fatos computados (agregação/grupo) -> light
    assert route_generation_model(c, Behavior.answer, [livro] * 30, "FATOS...") == ("modelo-light", "light")
    # contexto minúsculo (título encontrado) -> light
    assert route_generation_model(c, Behavior.answer, [livro], None) == ("modelo-light", "light")
    # busca semântica típica -> standard
    assert route_generation_model(c, Behavior.answer, [livro] * 8, None) == ("modelo-standard", "standard")
    # síntese longa sem fatos prontos -> heavy
    assert route_generation_model(c, Behavior.answer, [livro] * 50, None) == ("modelo-heavy", "heavy")
    # comportamentos sensíveis NUNCA caem no light (nuance > centavos)
    assert route_generation_model(c, Behavior.clarify, [livro], None) == ("modelo-standard", "standard")
    assert route_generation_model(c, Behavior.acknowledge_limitation, [livro], None)[1] == "standard"


def test_roteamento_desligado_usa_standard(monkeypatch):
    monkeypatch.setattr(config, "SMART_ROUTING", False)
    c = _StubClient()
    assert route_generation_model(c, Behavior.answer, [], "FATOS")[1] == "standard"


# ---------- E2E pelo pipeline com OpenRouter mockado ----------
def test_pipeline_e2e_openrouter_mockado():
    """Pergunta Q8 inteira pelo pipeline com o chat roteado (mock): planner estruturado,
    agregação determinística, tier LIGHT na narração, citação verificada e custo real somado."""
    def handler(request: httpx.Request) -> httpx.Response:
        p = json.loads(request.content.decode("utf-8"))
        nome = (p.get("response_format", {}).get("json_schema", {}) or {}).get("name", "")
        if nome == "PlannerLLMOutput":
            content = json.dumps({"semantic_queries": ["livro mais antigo"], "aggregation": "min_year"})
        else:   # geração ancorada (AnswerOut)
            content = json.dumps({"answer": 'O mais antigo é "Ensaios sobre o pouco" (BK0124), de 1986.',
                                  "cited_ids": ["BK0124"]})
        return httpx.Response(200, json=_resp(content, model=p["model"], cost=0.0001))

    chat = OpenRouterClient(api_key="sk-or-x", http=_mock_http(handler))
    pipe = AskPipeline(client=chat, embedder=GeminiClient(api_key=""))   # embeddings offline (cache)
    r = pipe.ask("Qual é o livro mais antigo do nosso catálogo?")

    assert r.references and r.references[0].id == "BK0124"               # citação verificada
    assert r.retrieval_debug.behavior == Behavior.answer
    assert any("tier=light" in n for n in r.retrieval_debug.notes)       # fatos prontos -> light
    assert r.retrieval_debug.estimated_cost_usd == pytest.approx(0.0002) # planner + geração (custo real)


def test_pipeline_degrada_com_openrouter_sem_chave():
    """Sem OPENROUTER_API_KEY o chat fica indisponível: planner regex + resposta determinística
    (sem rede), e os embeddings seguem o embedder injetado (também offline)."""
    pipe = AskPipeline(client=OpenRouterClient(api_key=""), embedder=GeminiClient(api_key=""))
    r = pipe.ask("Qual é o livro mais antigo do nosso catálogo?")
    assert r.retrieval_debug.behavior == Behavior.answer
    assert "1986" in r.answer                       # agregação determinística no template degradado
