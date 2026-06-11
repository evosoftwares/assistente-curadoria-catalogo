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
# Feedback humano (👍/👎) por resposta — JSON-lines, gitignored (dado de uso real; vira o
# gold-set vivo do v2 e, depois, dados de treino). Path trocável p/ testes/volume Docker.
FEEDBACK_PATH = Path(os.getenv("FEEDBACK_FILE", str(DATA_DIR / "feedback.jsonl")))
# Log de USO persistido (espelho em arquivo dos eventos JSON do stdout): alimenta o B.I.
# (dashboard /kpis) com operação real — custo, latência, tiers, cache. Gitignored; os testes
# desligam via conftest.py (senão perguntas de teste poluiriam o painel). Rotação de arquivo
# é preocupação de produção (coletor real); para o MVP/demo, append-only basta.
USAGE_LOG_ENABLED = os.getenv("USAGE_LOG_ENABLED", "true").lower() == "true"
USAGE_LOG_PATH = Path(os.getenv("USAGE_LOG_FILE", str(DATA_DIR / "usage_log.jsonl")))

# --- Credenciais / modelos ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_PLANNER_MODEL = os.getenv("GEMINI_PLANNER_MODEL", "gemini-2.5-flash-lite")
GEMINI_JUDGE_MODEL = os.getenv("GEMINI_JUDGE_MODEL", "gemini-2.5-flash")
GEMINI_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
# Variantes por PESO p/ o roteamento inteligente (tier light/heavy; vazio -> usa o padrão do papel).
GEMINI_MODEL_LIGHT = os.getenv("GEMINI_MODEL_LIGHT", "gemini-2.5-flash-lite")
GEMINI_MODEL_HEAVY = os.getenv("GEMINI_MODEL_HEAVY", "")

# --- Roteamento de modelos (OpenRouter) ---
# LLM_BACKEND escolhe quem serve o CHAT (planner/geração/juiz):
#   "auto" (padrão) -> OpenRouter se houver OPENROUTER_API_KEY; senão Gemini direto.
#   "openrouter" / "gemini" forçam o backend.
# EMBEDDINGS não passam pelo OpenRouter (não há endpoint de embeddings lá): ficam no Gemini
# (llm.get_embedder) ou no backend local — ver EMBEDDINGS_BACKEND abaixo.
LLM_BACKEND = os.getenv("LLM_BACKEND", "auto").lower()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
# Slugs "provedor/modelo" do catálogo do OpenRouter; "openrouter/auto" delega a escolha ao roteador.
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash")
OPENROUTER_PLANNER_MODEL = os.getenv("OPENROUTER_PLANNER_MODEL", "google/gemini-2.5-flash-lite")
OPENROUTER_MODEL_LIGHT = os.getenv("OPENROUTER_MODEL_LIGHT", "google/gemini-2.5-flash-lite")
OPENROUTER_MODEL_HEAVY = os.getenv("OPENROUTER_MODEL_HEAVY", "")
# Juiz numa FAMÍLIA diferente do gerador — mitiga o viés "Gemini avaliando Gemini" (README §7).
OPENROUTER_JUDGE_MODEL = os.getenv("OPENROUTER_JUDGE_MODEL", "anthropic/claude-haiku-4.5")
# FALLBACK de roteamento: lista ordenada de modelos alternativos; se o primário falhar/ficar
# indisponível, o OpenRouter tenta o próximo — resiliência de provedor sem retry manual nosso.
OPENROUTER_FALLBACK_MODELS = [
    m.strip() for m in os.getenv("OPENROUTER_FALLBACK_MODELS", "").split(",") if m.strip()
]
# Critério de escolha de PROVEDOR p/ o mesmo modelo: "" (padrão do roteador), price, throughput, latency.
OPENROUTER_SORT = os.getenv("OPENROUTER_SORT", "").lower()
OPENROUTER_APP_TITLE = os.getenv("OPENROUTER_APP_TITLE", "Assistente de Curadoria do Catalogo")

# --- Economia de tokens (fluxo completo em docs/economia_de_tokens.md) ---
# Roteamento INTELIGENTE por solicitação: tarefas de só-narrar (fatos já computados) ou de
# contexto minúsculo caem no modelo LIGHT (barato); sínteses muito longas podem subir ao HEAVY.
SMART_ROUTING = os.getenv("SMART_ROUTING", "true").lower() == "true"
# Teto de SAÍDA por chamada (bound de custo; 0 desliga). ATENÇÃO ao calibrar: nos modelos
# Gemini 2.5 o "thinking" (ligado por padrão) CONTA dentro deste orçamento de saída — um teto
# apertado (ex.: 1024) trunca o JSON da resposta e derruba a geração em JSONDecodeError
# (visto em produção na Q1). 4096 dá folga p/ thinking + a maior resposta real (~600 tokens)
# e ainda limita o pior caso a ~US$0,01/chamada no flash.
LLM_MAX_OUTPUT_TOKENS = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "4096"))
# Cache de CHAMADAS ao LLM (além dos caches de resposta do pipeline): memória limitada e,
# opcionalmente, disco (data/llm_cache/, gitignored) p/ reaproveitar entre PROCESSOS (re-rodar
# eval/judge custa US$ 0). Seguro porque temperature=0 torna a chamada determinística.
LLM_CACHE_ENABLED = os.getenv("LLM_CACHE_ENABLED", "true").lower() == "true"
LLM_CACHE_MAX_ENTRIES = int(os.getenv("LLM_CACHE_MAX_ENTRIES", "512"))
LLM_CACHE_PERSIST = os.getenv("LLM_CACHE_PERSIST", "false").lower() == "true"
LLM_CACHE_DIR = DATA_DIR / "llm_cache"
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "60"))

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
# Só confie no header X-Forwarded-For se o serviço estiver ATRÁS de um proxy confiável.
# Caso contrário (default), o XFF é controlado pelo cliente e poderia ser forjado p/ burlar o
# rate limit — então usamos o IP real do socket.
TRUST_PROXY = os.getenv("TRUST_PROXY", "false").lower() == "true"
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
    # Slugs do OpenRouter (mesmos modelos por trás) — usados só como FALLBACK de estimativa:
    # no caminho roteado o custo REAL vem na própria resposta (usage.cost -> Usage.cost_override).
    "google/gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "google/gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
    "anthropic/claude-haiku-4.5": {"input": 1.00, "output": 5.00},
}


def price_for(model: str) -> dict:
    """Preço do modelo; cai no preço do Flash se desconhecido (estimativa conservadora)."""
    return PRICING.get(model, PRICING["gemini-2.5-flash"])


def has_api_key() -> bool:
    return bool(GEMINI_API_KEY)
