"""API FastAPI. Endpoint principal: POST /ask.

- Inicializa o pipeline uma única vez (carrega/constrói o índice) no startup.
- Loga cada requisição de forma estruturada.
- Limite de tamanho da pergunta vem do schema (AskRequest).
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .logging_conf import log_event, new_request_id
from .models import AskRequest, AskResponse
from .pipeline import AskPipeline

_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
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
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    pipe: AskPipeline = _state.get("pipeline")
    return {
        "status": "ok",
        "catalog_size": len(pipe.catalog) if pipe else 0,
        "semantic_ready": bool(pipe and pipe.index.matrix is not None),
        "llm_available": bool(pipe and pipe.client.available),
        "model": config.GEMINI_MODEL,
        "embeddings_backend": config.EMBEDDINGS_BACKEND,
    }


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    pipe: AskPipeline = _state["pipeline"]
    rid = new_request_id()
    resp = pipe.ask(req.question)
    d = resp.retrieval_debug
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
