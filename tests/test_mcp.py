"""Testes do servidor MCP (mcp_server.py) — sem rede, sem SDK externo.

Travam: o handshake JSON-RPC (initialize/tools/list), o despacho de tools/call, o
comportamento das 3 ferramentas com pipeline OFFLINE injetado, e que feedback de agente
cai no MESMO dataset (via feedback_store). Rode com:  python -m pytest -q
"""
from __future__ import annotations

import json

import pytest

import mcp_server
from app import config
from app.llm import GeminiClient
from app.pipeline import AskPipeline


@pytest.fixture(autouse=True)
def _offline(monkeypatch, tmp_path):
    # Pipeline 100% offline injetado (sem chave -> planner regex + BM25 + resposta template);
    # feedback vai para tmp (nunca o dataset real).
    monkeypatch.setattr(config, "FEEDBACK_PATH", tmp_path / "fb.jsonl")
    monkeypatch.setattr(mcp_server, "_pipe",
                        AskPipeline(client=GeminiClient(api_key=""),
                                    embedder=GeminiClient(api_key="")))
    yield


# ---------- protocolo ----------
def test_initialize_ecoa_versao_e_anuncia_tools():
    resp = mcp_server._handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                               "params": {"protocolVersion": "2025-03-26"}})
    r = resp["result"]
    assert r["protocolVersion"] == "2025-03-26"          # ecoa a versão do cliente
    assert "tools" in r["capabilities"]
    assert r["serverInfo"]["name"] == "curadoria-catalogo"


def test_notificacao_nao_tem_resposta():
    assert mcp_server._handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_tools_list_expoe_as_3_ferramentas():
    resp = mcp_server._handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    nomes = [t["name"] for t in resp["result"]["tools"]]
    assert nomes == ["perguntar_catalogo", "enviar_feedback", "kpis_resumo"]
    for t in resp["result"]["tools"]:                     # contrato: schema sempre presente
        assert t["inputSchema"]["type"] == "object" and t["description"]


def test_tools_call_desconhecida_e_erro_jsonrpc():
    resp = mcp_server._handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                               "params": {"name": "nao_existe", "arguments": {}}})
    assert resp["error"]["code"] == -32602


# ---------- ferramentas ----------
def test_perguntar_catalogo_offline_responde_com_fato():
    out = mcp_server.perguntar_catalogo("Qual é o livro mais antigo do nosso catálogo?")
    assert out["comportamento"] == "answer" and "1986" in out["resposta"]


def test_tools_call_fim_a_fim_devolve_content_text():
    resp = mcp_server._handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                               "params": {"name": "perguntar_catalogo",
                                          "arguments": {"pergunta": "Qual o livro mais antigo do catálogo?"}}})
    assert resp["result"]["isError"] is False
    corpo = json.loads(resp["result"]["content"][0]["text"])
    assert "1986" in corpo["resposta"]


def test_enviar_feedback_grava_no_mesmo_dataset():
    out = mcp_server.enviar_feedback("pergunta de agente", "resposta avaliada", util=False,
                                     comentario="faltou contexto")
    assert out["ok"] is True and out["verdict"] == "down"
    rec = json.loads(config.FEEDBACK_PATH.read_text(encoding="utf-8").strip())
    assert rec["verdict"] == "down" and rec["comment"] == "faltou contexto"


def test_erro_de_ferramenta_vira_isError_nao_crash():
    # argumento inválido (pergunta vazia viola min_length do contrato em perguntar? não —
    # aqui forçamos via enviar_feedback sem campos obrigatórios do Pydantic)
    resp = mcp_server._handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                               "params": {"name": "enviar_feedback",
                                          "arguments": {"pergunta": "x", "resposta": "y", "util": True}}})
    # pergunta "x" viola min_length=2 do FeedbackRequest -> erro CAPTURADO como isError
    assert resp["result"]["isError"] is True
    assert "erro" in resp["result"]["content"][0]["text"]


def test_kpis_resumo_estrutura_estavel():
    k = mcp_server.kpis_resumo()
    assert set(k) == {"qualidade", "operacao", "aceitacao"}   # contrato p/ agentes
