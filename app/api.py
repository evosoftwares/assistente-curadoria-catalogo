"""API FastAPI. Endpoint principal: POST /ask.

- Inicializa o pipeline uma única vez (carrega/constrói o índice) no startup.
- Loga cada requisição de forma estruturada.
- Limite de tamanho da pergunta vem do schema (AskRequest).
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from . import config
from .logging_conf import log_event, new_request_id
from .models import AskRequest, AskResponse, FeedbackRequest
from .pipeline import AskPipeline

# Guardamos o pipeline em estado de módulo (não global solto) para o lifespan injetar 1 instância.
_state: dict = {}

# --- Estado de SEGURANÇA (em processo) ---
# /ask é síncrono -> roda no threadpool do FastAPI -> requisições concorrentes mutam este estado em
# paralelo. _lock serializa as leituras/escritas (achado SEC-02: sem ele, _spent_usd += e a mutação
# do deque correriam, subcontando o custo e podendo lançar RuntimeError).
_lock = threading.Lock()
# Rate limit: por IP, timestamps das chamadas recentes (janela deslizante de 60s).
_rate: dict[str, deque] = {}
# Circuit breaker de custo com JANELA DIÁRIA real (achado SEC-01: antes nunca resetava -> 429 eterno).
_spent_usd = 0.0
_cost_day: str | None = None
# Serializa os appends do feedback.jsonl: o endpoint é sync (threadpool) e duas escritas
# concorrentes no mesmo arquivo poderiam intercalar bytes — uma linha JSONL corrompida
# invalidaria o dataset (cada linha precisa ser parseável sozinha).
_fb_lock = threading.Lock()


def _account_cost(usd: float) -> None:
    # Soma o custo da requisição ao acumulado do dia (sob lock — read-modify-write atômico).
    global _spent_usd
    with _lock:
        _spent_usd += usd


def _client_ip(request: Request) -> str:
    # IP do chamador para o rate limit. SEGURANÇA: X-Forwarded-For é controlado pelo cliente —
    # só confiamos nele quando há um proxy confiável à frente (TRUST_PROXY); senão, um atacante
    # forjaria um XFF diferente por requisição e burlaria o rate limit. Default: IP real do socket.
    if config.TRUST_PROXY:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()       # 1º IP da cadeia = cliente original (via proxy)
    return request.client.host if request.client else "?"


def _enforce_limits(request: Request) -> None:
    """Aplica rate limit por IP e o teto de custo (janela diária) ANTES de gastar tokens.
    Levanta HTTP 429 — OWASP LLM10 (Unbounded Consumption): proteção contra abuso/consumo/DoS.
    Tudo sob _lock porque o endpoint é sync (threadpool) e o estado é compartilhado (SEC-02)."""
    global _spent_usd, _cost_day
    with _lock:
        # Reset DIÁRIO do teto de custo (SEC-01): zera ao virar o dia (UTC), em vez de só no restart.
        today = time.strftime("%Y-%m-%d", time.gmtime())
        if today != _cost_day:
            _cost_day, _spent_usd = today, 0.0
        if config.DAILY_COST_CAP_USD and _spent_usd >= config.DAILY_COST_CAP_USD:
            raise HTTPException(status_code=429, detail="Teto de custo diário atingido. Tente amanhã.")
        # Rate limit por IP (janela deslizante de 60s). RATE_LIMIT_RPM=0 desliga.
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
        llm_backend=pipe.client.backend,             # gemini direto ou roteado via openrouter
        model=pipe.client.generation_model,
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
        # Backend/modelo vêm do CLIENTE ativo (não de config fixa): com LLM_BACKEND=auto o
        # health mostra se o chat está roteado (openrouter) ou direto (gemini) — a UI e a
        # banca enxergam o modo real sem ler logs.
        "llm_backend": pipe.client.backend if pipe else config.LLM_BACKEND,
        "model": pipe.client.generation_model if pipe else "?",
        "embeddings_backend": config.EMBEDDINGS_BACKEND,
    }


_kpis_html: str | None = None  # cache em memória do dashboard (evita reconstruir a cada hit — COMP-04)


@app.get("/kpis", response_class=HTMLResponse)
def kpis(request: Request) -> str:
    """Dashboard web com todos os KPIs (gerado de eval/*.json). Rate-limitado (faz IO/CPU) e
    cacheado em memória; em erro NÃO vaza a exceção crua ao cliente (SEC-05/COMP-04)."""
    _enforce_limits(request)                          # /kpis também consome IO/CPU -> sob rate limit
    global _kpis_html
    if _kpis_html is not None:
        return _kpis_html
    html_path = config.BASE_DIR / "dashboard" / "index.html"
    try:
        _kpis_html = (html_path.read_text(encoding="utf-8") if html_path.exists()
                      else __import__("scripts.build_dashboard", fromlist=["build"]).build())
        return _kpis_html
    except Exception as e:
        # Loga o detalhe no servidor; ao cliente, mensagem genérica (sem str(e) -> sem vazar caminho).
        log_event("error", path="/kpis", error_type=type(e).__name__, error=str(e)[:300])
        return "<h1>Dashboard indisponível</h1><p>Veja os logs do servidor.</p>"


@app.post("/feedback")
def feedback(req: FeedbackRequest, request: Request) -> dict:
    """Coletor de FEEDBACK humano (👍/👎 + comentário) — 1º passo do loop do v2: cada
    registro vira matéria-prima do gold-set vivo e de futuros componentes treinados.
    Persistência em JSON-LINES (1 linha autossuficiente por evento — o formato que os
    consumidores parseiam sem estado). Nota LGPD: a pergunta é gravada CRUA mesmo com
    LOG_QUESTIONS=false — feedback é um opt-in explícito do usuário (clique), e sem a
    pergunta o registro não serve de dataset."""
    _enforce_limits(request)              # mesmo rate limit do /ask (escrita em disco é recurso)
    record = {
        "ts": round(time.time(), 3),
        "verdict": req.verdict,
        "question": req.question,
        "answer": req.answer,
        "comment": req.comment,
        "behavior": req.behavior,
        "reference_ids": req.reference_ids,
        "retrieved_ids": req.retrieved_ids,
        "context_ids": req.context_ids,
        "plan_json": req.plan_json,
        "cost_usd": req.cost_usd,
        "latency_ms": req.latency_ms,
        "from_cache": req.from_cache,
    }
    line = json.dumps(record, ensure_ascii=False)
    with _fb_lock:                        # appends serializados -> nenhuma linha intercalada
        config.FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(config.FEEDBACK_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    # Observabilidade sem duplicar payload: o log estruturado registra o evento e o tamanho
    # do dataset; o conteúdo integral está no feedback.jsonl.
    log_event("feedback", verdict=req.verdict, has_comment=bool(req.comment),
              n_references=len(req.reference_ids), behavior=req.behavior)
    return {"ok": True}


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, request: Request) -> AskResponse:
    # Endpoint principal exigido pelo desafio. Toda a lógica vive no pipeline (testável fora do
    # HTTP); aqui orquestramos segurança + request_id + log estruturado. O tamanho/sanitização da
    # pergunta já vêm validados pelo schema AskRequest (Pydantic) antes de chegar aqui.
    _enforce_limits(request)                     # rate limit por IP + teto de custo (pode levantar 429)
    pipe: AskPipeline = _state["pipeline"]
    rid = new_request_id()
    resp = pipe.ask(req.question)                # processamento (cache -> plano -> retrieval -> geração)
    d = resp.retrieval_debug
    _account_cost(d.estimated_cost_usd)          # alimenta o circuit breaker de custo (sob lock)
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
