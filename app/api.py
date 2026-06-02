"""API FastAPI. Endpoint principal: POST /ask.

- Inicializa o pipeline uma única vez (carrega/constrói o índice) no startup.
- Loga cada requisição de forma estruturada.
- Limite de tamanho da pergunta vem do schema (AskRequest).
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from . import config
from .logging_conf import log_event, new_request_id
from .models import AskRequest, AskResponse
from .pipeline import AskPipeline

# Guardamos o pipeline em estado de módulo (não global solto) para o lifespan injetar 1 instância.
_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # lifespan do FastAPI: construímos o pipeline UMA vez no startup (carrega catálogo + índice
    # de embeddings) e reusamos em toda requisição. Construir por-requisição re-leria o índice a
    # cada chamada — caro e desnecessário. O log de startup vira um "cartão de saúde" observável.
    pipe = AskPipeline()
    _state["pipeline"] = pipe
    log_event(
        "startup",
        catalog_size=len(pipe.catalog),
        embeddings_backend=config.EMBEDDINGS_BACKEND,
        semantic_ready=pipe.index.matrix is not None,
        llm_available=pipe.client.available,
        model=config.GEMINI_MODEL,
    )
    yield
    _state.clear()


app = FastAPI(title="Assistente de Curadoria do Catálogo", version="1.0.0", lifespan=lifespan)
# CORS restrito à UI local (cada /ask custa tokens — não deixamos qualquer origem chamar).
# Ajuste CORS_ORIGINS no .env para outros hosts.
_origins = [o.strip() for o in os.getenv(
    "CORS_ORIGINS", "http://localhost:8501,http://127.0.0.1:8501").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware, allow_origins=_origins, allow_methods=["GET", "POST"], allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    # Health expõe o MODO em que o serviço subiu (semântico pronto? LLM disponível?) — útil
    # para a UI mostrar "BM25-only/degradado" e para a banca ver o estado sem ler logs.
    pipe: AskPipeline = _state.get("pipeline")
    return {
        "status": "ok",
        "catalog_size": len(pipe.catalog) if pipe else 0,
        "semantic_ready": bool(pipe and pipe.index.matrix is not None),
        "llm_available": bool(pipe and pipe.client.available),
        "model": config.GEMINI_MODEL,
        "embeddings_backend": config.EMBEDDINGS_BACKEND,
    }


@app.get("/kpis", response_class=HTMLResponse)
def kpis() -> str:
    """Dashboard web com todos os KPIs do projeto (gerado de eval/*.json)."""
    html_path = config.BASE_DIR / "dashboard" / "index.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    try:
        from scripts.build_dashboard import build
        return build()
    except Exception as e:
        return f"<h1>Dashboard indisponível</h1><p>Rode <code>python scripts/build_dashboard.py</code>. ({e})</p>"


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    # Endpoint principal exigido pelo desafio. Toda a lógica vive no pipeline (testável fora do
    # HTTP); aqui só orquestramos request_id + log estruturado. O limite de tamanho da pergunta
    # vem do schema AskRequest (Pydantic valida antes de chegar aqui).
    pipe: AskPipeline = _state["pipeline"]
    rid = new_request_id()
    resp = pipe.ask(req.question)
    d = resp.retrieval_debug
    # Log estruturado por requisição (observabilidade): 1 linha JSON com latência por etapa,
    # tokens, custo, ids recuperados, abstenção e plano — base p/ dashboards de produção.
    log_event(
        "ask",
        request_id=rid,
        question=req.question,
        behavior=d.behavior.value,
        retrieved_ids=d.retrieved_ids,
        candidate_count=d.candidate_count,
        top_cosine=d.top_cosine,
        latency_ms=d.latency_ms,
        tokens=d.tokens,
        cost_usd=d.estimated_cost_usd,
        from_cache=d.from_cache,
        n_references=len(resp.references),
        notes=d.notes,
    )
    return resp
