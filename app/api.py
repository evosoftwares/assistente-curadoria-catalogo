"""API FastAPI. Endpoint principal: POST /ask.

- Inicializa o pipeline uma única vez (carrega/constrói o índice) no startup.
- Loga cada requisição de forma estruturada.
- Limite de tamanho da pergunta vem do schema (AskRequest).
"""
from __future__ import annotations

import os
import time
from collections import deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from . import config
from .logging_conf import log_event, new_request_id
from .models import AskRequest, AskResponse
from .pipeline import AskPipeline

# Guardamos o pipeline em estado de módulo (não global solto) para o lifespan injetar 1 instância.
_state: dict = {}

# --- Estado de SEGURANÇA (em processo) ---
# Rate limit: por IP, guardamos os timestamps das chamadas recentes (janela deslizante de 60s).
_rate: dict[str, deque] = {}
# Circuit breaker de custo: gasto acumulado no processo; acima do teto, recusamos novas chamadas.
_spent_usd = 0.0


def _client_ip(request: Request) -> str:
    # IP do chamador para o rate limit. (Atrás de proxy, X-Forwarded-For; senão, o socket.)
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


def _enforce_limits(request: Request) -> None:
    """Aplica rate limit por IP e o teto global de custo ANTES de gastar tokens.
    Levanta HTTP 429 (Too Many Requests) — OWASP LLM: proteção contra abuso/consumo (LLM10/DoS)."""
    # Teto global de custo (circuit breaker): protege contra um runaway de gasto.
    if config.DAILY_COST_CAP_USD and _spent_usd >= config.DAILY_COST_CAP_USD:
        raise HTTPException(status_code=429, detail="Teto de custo do período atingido. Tente mais tarde.")
    # Rate limit por IP (janela de 60s). RATE_LIMIT_RPM=0 desliga.
    if config.RATE_LIMIT_RPM:
        now = time.time()
        ip = _client_ip(request)
        bucket = _rate.setdefault(ip, deque())
        while bucket and now - bucket[0] > 60:   # descarta timestamps fora da janela de 1 min
            bucket.popleft()
        if len(bucket) >= config.RATE_LIMIT_RPM:
            raise HTTPException(status_code=429, detail="Muitas requisições. Aguarde um momento.")
        bucket.append(now)
        # Bound do dicionário de IPs (anti-DoS de memória): se muitos IPs distintos, limpa os vazios.
        if len(_rate) > 10_000:
            for k in [k for k, v in _rate.items() if not v]:
                _rate.pop(k, None)


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


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    # Handler global: NUNCA devolvemos stack trace/detalhe interno ao cliente (OWASP — evita
    # divulgação de informação). Logamos o detalhe no servidor; o cliente recebe mensagem genérica.
    log_event("error", path=str(request.url.path), error_type=type(exc).__name__, error=str(exc)[:300])
    if isinstance(exc, HTTPException):           # 429 etc. preservam o status/mensagem pretendidos
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return JSONResponse(status_code=500, content={"detail": "Erro interno. Tente novamente."})


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
def ask(req: AskRequest, request: Request) -> AskResponse:
    # Endpoint principal exigido pelo desafio. Toda a lógica vive no pipeline (testável fora do
    # HTTP); aqui orquestramos segurança + request_id + log estruturado. O tamanho/sanitização da
    # pergunta já vêm validados pelo schema AskRequest (Pydantic) antes de chegar aqui.
    global _spent_usd
    _enforce_limits(request)                     # rate limit por IP + teto de custo (pode levantar 429)
    pipe: AskPipeline = _state["pipeline"]
    rid = new_request_id()
    resp = pipe.ask(req.question)                # processamento (cache -> plano -> retrieval -> geração)
    d = resp.retrieval_debug
    _spent_usd += d.estimated_cost_usd           # alimenta o circuit breaker de custo
    # Log estruturado por requisição (observabilidade): 1 linha JSON com latência por etapa,
    # tokens, custo, ids recuperados, abstenção e plano — base p/ dashboards de produção.
    # LGPD/privacidade: só registramos a pergunta CRUA se LOG_QUESTIONS=true (em produção, off).
    log_event(
        "ask",
        request_id=rid,
        question=(req.question if config.LOG_QUESTIONS else f"<oculto:{len(req.question)} chars>"),
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
