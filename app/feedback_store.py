"""Persistência do FEEDBACK humano — o ÚNICO lugar que escreve data/feedback.jsonl.

Por quê: o dataset passou a ser alimentado por DOIS caminhos (o endpoint HTTP /feedback e a
tool MCP enviar_feedback). Duplicar a escrita divergiria formato e locking — e uma linha
JSONL intercalada por escritas concorrentes invalidaria o dataset (cada linha precisa ser
JSON autossuficiente). Aqui: 1 evento = 1 linha, append serializado por lock, validação já
feita pelo chamador via models.FeedbackRequest (o contrato é um só para todos os caminhos).
"""
from __future__ import annotations

import json
import threading
import time

from . import config
from .models import FeedbackRequest

# Serializa os appends: o endpoint roda no threadpool do FastAPI e o MCP é outro processo —
# o lock cobre a concorrência intra-processo; entre processos, appends pequenos (<4 KB) com
# open/write/close são atômicos o bastante para JSONL local (produção usaria fila/banco).
_lock = threading.Lock()


def save(req: FeedbackRequest) -> dict:
    """Grava UM evento de feedback e devolve o registro completo (com timestamp do servidor).
    O chamador decide o que fazer com o retorno (HTTP loga evento; MCP devolve ao agente)."""
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
    with _lock:
        config.FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(config.FEEDBACK_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    return record
