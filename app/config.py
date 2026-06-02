"""Configuração centralizada (lida do ambiente / .env).

Tudo que pode mudar entre execuções — IDs de modelo, parâmetros de recuperação,
preços — vive aqui, para que a troca seja de uma linha (ex.: se um modelo do
Gemini sofrer rate-limit ou for descontinuado durante a demo).
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Caminhos ---
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
BOOKS_PATH = DATA_DIR / "books.json"
QUESTIONS_PATH = DATA_DIR / "questions.txt"
EMBEDDINGS_PATH = DATA_DIR / "embeddings.npy"
EMBEDDINGS_META_PATH = DATA_DIR / "embeddings_meta.json"
CONTEXT_CARDS_PATH = DATA_DIR / "context_cards.json"  # Contextual Retrieval (gerado offline)

# --- Credenciais / modelos ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_PLANNER_MODEL = os.getenv("GEMINI_PLANNER_MODEL", "gemini-2.5-flash-lite")
GEMINI_JUDGE_MODEL = os.getenv("GEMINI_JUDGE_MODEL", "gemini-2.5-flash")
GEMINI_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")

# --- Embeddings ---
# "gemini"  -> usa a API do Gemini (padrão; cacheado em disco)
# "local"   -> sentence-transformers offline (exige `pip install sentence-transformers`)
EMBEDDINGS_BACKEND = os.getenv("EMBEDDINGS_BACKEND", "gemini").lower()
LOCAL_EMBEDDING_MODEL = os.getenv("LOCAL_EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))

# --- Recuperação / comportamento ---
CURRENT_YEAR = int(os.getenv("CURRENT_YEAR", "2026"))
TOP_K = int(os.getenv("TOP_K", "8"))
RRF_K = int(os.getenv("RRF_K", "60"))
# NOTA: um limiar de cosseno para abstenção foi AVALIADO e DESCARTADO — neste catálogo
# templado os cossenos in-scope (0,64-0,75) e fora-de-escopo (0,60-0,63) se sobrepõem,
# então o cosseno não separa bem. A abstenção vem do title-lookup (Q10) + geração ancorada
# (que já responde "não consta" quando nada serve). top_cosine segue exposto p/ observabilidade.
# token_set_ratio (0-100) mínimo para considerar um título "presente no catálogo".
TITLE_MATCH_THRESHOLD = int(os.getenv("TITLE_MATCH_THRESHOLD", "90"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))

# Cache semântico de resposta: além do exact-match (sha256), reusa a resposta quando uma
# pergunta nova é semanticamente quase idêntica a uma anterior (cosseno >= limiar).
SEMANTIC_CACHE_ENABLED = os.getenv("SEMANTIC_CACHE_ENABLED", "true").lower() == "true"
# 0.92 calibrado: paráfrases reais ficam ~0,85-0,98 e perguntas de tópico distinto ~0,64,
# então 0,92 pega paráfrases próximas sem risco de servir resposta de outra pergunta.
SEMANTIC_CACHE_THRESHOLD = float(os.getenv("SEMANTIC_CACHE_THRESHOLD", "0.92"))

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

# --- Segurança / limites (OWASP LLM Top 10: abuso, DoS, custo, privacidade) ---
# Rate limit por IP no /ask (cada chamada custa tokens -> protege contra abuso/custo).
RATE_LIMIT_RPM = int(os.getenv("RATE_LIMIT_RPM", "30"))            # 0 desliga
# Teto de custo acumulado por processo (circuit breaker de gasto). 0 desliga.
DAILY_COST_CAP_USD = float(os.getenv("DAILY_COST_CAP_USD", "5.0"))
# Caches em memória LIMITADOS: evita crescimento ilimitado (DoS de memória) com perguntas únicas.
MAX_CACHE_ENTRIES = int(os.getenv("MAX_CACHE_ENTRIES", "1000"))
# LGPD/privacidade: registrar a pergunta CRUA no log? Em produção, prefira false (ou redação de PII).
LOG_QUESTIONS = os.getenv("LOG_QUESTIONS", "true").lower() == "true"

# --- Preços (USD por 1M de tokens) — confirmados em jun/2026 (ai.google.dev/pricing) ---
PRICING = {
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "gemini-embedding-001": {"input": 0.15, "output": 0.0},
}


def price_for(model: str) -> dict:
    """Preço do modelo; cai no preço do Flash se desconhecido (estimativa conservadora)."""
    return PRICING.get(model, PRICING["gemini-2.5-flash"])


def has_api_key() -> bool:
    return bool(GEMINI_API_KEY)
