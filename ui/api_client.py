"""Cliente HTTP do frontend — a ÚNICA porta de saída para o backend.

Por quê: os componentes visuais não devem conhecer URL, timeout nem formato de erro.
Trocar a API de lugar (porta diferente, `http://api:8000` dentro do Docker via
API_BASE_URL, autenticação futura) é mexer SÓ aqui — mesmo princípio do backend,
onde o resto do código é agnóstico ao provedor de LLM (app/llm.py).
"""
from __future__ import annotations

import os

import httpx

# Em Docker, o compose injeta API_BASE_URL=http://api:8000 (nome do serviço na rede
# interna); localmente cai no default 127.0.0.1:8000 do uvicorn.
API_BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")


def get_health(timeout: float = 10.0) -> dict:
    """GET /health — diz em que MODO o backend está (semântico? LLM? qual backend/modelo).
    Deixa a UI mostrar 'degradado/BM25-only' em vez de quebrar misteriosamente."""
    r = httpx.get(f"{API_BASE}/health", timeout=timeout)
    r.raise_for_status()
    return r.json()


def ask(question: str, timeout: float = 60.0) -> dict:
    """POST /ask — timeout folgado (60s): a geração domina a latência (~7s típico),
    e um pico de provedor não deve derrubar a pergunta do usuário."""
    r = httpx.post(f"{API_BASE}/ask", json={"question": question}, timeout=timeout)
    r.raise_for_status()
    return r.json()
