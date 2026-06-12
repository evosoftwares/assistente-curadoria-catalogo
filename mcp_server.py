"""Servidor MCP do assistente — expõe o catálogo como FERRAMENTA para agentes de IA.

O Claude Code conecta automaticamente ao abrir esta pasta (via .mcp.json); qualquer outro
cliente MCP fala o mesmo protocolo: JSON-RPC 2.0 sobre stdio, 1 mensagem por linha.

POR QUE SEM O SDK `mcp`: o pacote oficial exige starlette>=1.x e o FastAPI pinado do
projeto exige starlette<0.42 — conflito direto de dependências. Como o transporte stdio
do MCP se resume a 3 métodos (initialize, tools/list, tools/call), implementamos o
protocolo em ~100 linhas SEM dependência nova — coerente com a regra do desafio de não
esconder a lógica atrás de frameworks ("queremos ver suas decisões").

Tools expostas:
- perguntar_catalogo(pergunta)  -> resposta ancorada + livros usados + custo/comportamento
- enviar_feedback(...)          -> grava no MESMO dataset do loop v2 (data/feedback.jsonl)
- kpis_resumo()                 -> números-chave de qualidade, operação e aceitação

Teste manual rápido (sem cliente MCP):
  echo {"jsonrpc":"2.0","id":1,"method":"tools/list"} | .venv\\Scripts\\python.exe mcp_server.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))   # permite `from app import ...` rodando da raiz como script

PROTOCOL_FALLBACK = "2025-06-18"   # versão respondida se o cliente não declarar a dele

# Pipeline preguiçoso: criar no 1º uso (carrega catálogo + índice) — o handshake initialize
# responde instantâneo mesmo a frio, e testes podem INJETAR um pipeline offline aqui.
_pipe = None


def _pipeline():
    global _pipe
    if _pipe is None:
        from app.pipeline import AskPipeline
        _pipe = AskPipeline()
    return _pipe


# ---------------------------------------------------------------------------
# As ferramentas (funções puras — o protocolo abaixo só as despacha)
# ---------------------------------------------------------------------------
def perguntar_catalogo(pergunta: str) -> dict:
    """Mesmo pipeline do POST /ask, em processo (não precisa da API HTTP no ar)."""
    r = _pipeline().ask(pergunta)
    d = r.retrieval_debug
    return {
        "resposta": r.answer,
        "comportamento": d.behavior.value,   # answer | abstain | clarify | acknowledge_limitation
        "livros_usados": [{"id": x.id, "titulo": x.titulo, "autores": x.autores,
                           "ano": x.ano_publicacao} for x in r.references],
        "custo_usd": d.estimated_cost_usd,
        "do_cache": d.from_cache,
    }


def enviar_feedback(pergunta: str, resposta: str, util: bool, comentario: str = "") -> dict:
    """Valida com o MESMO contrato do endpoint HTTP (FeedbackRequest) e grava pelo MESMO
    store — feedback de agente e de humano caem no mesmo dataset do loop v2."""
    from app import feedback_store
    from app.models import FeedbackRequest
    req = FeedbackRequest(verdict="up" if util else "down", question=pergunta,
                          answer=resposta, comment=(comentario or None))
    rec = feedback_store.save(req)
    return {"ok": True, "verdict": rec["verdict"]}


def kpis_resumo() -> dict:
    """Números-chave para um agente decidir se confia/usa o assistente. Leitura defensiva:
    arquivo ausente vira seção vazia (nunca erro)."""
    def _json(p: Path, default):
        try:
            return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default
        except Exception:
            return default

    def _jsonl(p: Path) -> list[dict]:
        out = []
        if p.exists():
            for ln in p.read_text(encoding="utf-8").splitlines():
                try:
                    out.append(json.loads(ln))
                except Exception:
                    continue
        return out

    retr = _json(ROOT / "eval" / "results_retrieval.json", {})
    judge = _json(ROOT / "eval" / "results_judge.json", {})
    usage = [r for r in _jsonl(ROOT / "data" / "usage_log.jsonl") if r.get("event") == "ask"]
    fb = _jsonl(ROOT / "data" / "feedback.jsonl")
    up = sum(1 for r in fb if r.get("verdict") == "up")
    down = sum(1 for r in fb if r.get("verdict") == "down")
    custos = [r.get("cost_usd", 0) or 0 for r in usage]
    return {
        "qualidade": {
            "macro_retrieval": retr.get("macro", {}),
            "juiz_confiavel": judge.get("trustworthy"),
            "faithfulness": judge.get("faithfulness_macro"),
        },
        "operacao": {
            "requisicoes_registradas": len(usage),
            "custo_medio_usd": round(sum(custos) / len(custos), 6) if custos else None,
        },
        "aceitacao": {"votos_uteis": up, "votos_negativos": down,
                      "taxa_pct": round(100 * up / (up + down)) if (up + down) else None},
    }


# Registro único: schema (o que o cliente vê em tools/list) + função (o que tools/call roda).
TOOLS: list[dict] = [
    {
        "name": "perguntar_catalogo",
        "description": ("Pergunta em português sobre o catálogo de 200 livros da editora. "
                        "Retorna resposta ancorada nos dados, com os livros usados como fonte "
                        "(referências verificadas), comportamento e custo. Não inventa: se o "
                        "livro não existe, diz que não consta."),
        "inputSchema": {"type": "object",
                        "properties": {"pergunta": {"type": "string",
                                                    "description": "A pergunta, em português."}},
                        "required": ["pergunta"]},
        "fn": perguntar_catalogo,
    },
    {
        "name": "enviar_feedback",
        "description": ("Registra se uma resposta do catálogo foi útil (true) ou não (false), "
                        "com comentário opcional. Alimenta o dataset de melhoria contínua "
                        "(mesmo arquivo do feedback humano da UI)."),
        "inputSchema": {"type": "object",
                        "properties": {"pergunta": {"type": "string"},
                                       "resposta": {"type": "string"},
                                       "util": {"type": "boolean"},
                                       "comentario": {"type": "string"}},
                        "required": ["pergunta", "resposta", "util"]},
        "fn": enviar_feedback,
    },
    {
        "name": "kpis_resumo",
        "description": ("Números-chave do assistente: qualidade da recuperação (recall/MRR), "
                        "confiabilidade do juiz, requisições registradas, custo médio real e "
                        "taxa de aceitação do feedback humano."),
        "inputSchema": {"type": "object", "properties": {}},
        "fn": kpis_resumo,
    },
]


# ---------------------------------------------------------------------------
# Protocolo (JSON-RPC 2.0, transporte stdio em linhas)
# ---------------------------------------------------------------------------
def _result(mid, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _error(mid, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def _handle(msg: dict) -> dict | None:
    """Despacha UMA mensagem. Retorna None para notificações (não têm resposta)."""
    method = msg.get("method")
    mid = msg.get("id")
    if method == "initialize":
        client_proto = (msg.get("params") or {}).get("protocolVersion") or PROTOCOL_FALLBACK
        return _result(mid, {
            "protocolVersion": client_proto,        # ecoa a versão do cliente (compatibilidade)
            "capabilities": {"tools": {}},          # só ferramentas — sem resources/prompts
            "serverInfo": {"name": "curadoria-catalogo", "version": "1.0.0"},
        })
    if mid is None:                                  # notificações (ex.: notifications/initialized)
        return None
    if method == "ping":
        return _result(mid, {})
    if method == "tools/list":
        return _result(mid, {"tools": [{k: t[k] for k in ("name", "description", "inputSchema")}
                                       for t in TOOLS]})
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        tool = next((t for t in TOOLS if t["name"] == name), None)
        if tool is None:
            return _error(mid, -32602, f"ferramenta desconhecida: {name}")
        try:
            out = tool["fn"](**args)
            # Resultado como texto JSON legível (contrato de tools/call: content[]).
            return _result(mid, {"content": [{"type": "text",
                                              "text": json.dumps(out, ensure_ascii=False, indent=2)}],
                                 "isError": False})
        except Exception as e:
            # Erro vira resultado isError=true (o agente lê e decide) — nunca derruba o servidor.
            return _result(mid, {"content": [{"type": "text",
                                              "text": f"erro: {type(e).__name__}: {e}"}],
                                 "isError": True})
    return _error(mid, -32601, f"método não suportado: {method}")


def main() -> None:
    # stdout é O CANAL DO PROTOCOLO: qualquer print/log que vaze para ele corrompe o framing.
    # O logger da app escreve no stdout por padrão — redirecionamos seus handlers p/ stderr.
    import logging
    for h in logging.getLogger("curadoria").handlers:
        h.stream = sys.stderr

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue                                 # lixo na entrada não derruba o servidor
        resp = _handle(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()                       # flush imediato: o cliente espera a linha


if __name__ == "__main__":
    main()
