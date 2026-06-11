"""Logs estruturados em JSON (uma linha por requisição).

Observabilidade barata que os líderes técnicos esperam: por requisição registramos
latências por etapa, tokens, custo estimado, ids recuperados, comportamento e plano.
Em produção, esses eventos iriam para um coletor (dashboards de p50/p95, taxa de
abstenção, custo/req).
"""
from __future__ import annotations

import json
import logging
import sys
import threading
import time
import uuid

from . import config

_logger = logging.getLogger("curadoria")
# Guarda contra handlers duplicados: uvicorn --reload reimporta o módulo; sem este `if`,
# cada reload adicionaria outro StreamHandler e a mesma linha sairia repetida.
if not _logger.handlers:
    _h = logging.StreamHandler(sys.stdout)
    # Formatter só com %(message)s: a linha JÁ é JSON; não queremos o prefixo do logging
    # poluindo o JSON (cada linha tem que ser parseável por um coletor).
    _h.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(_h)
    _logger.setLevel(logging.INFO)


def new_request_id() -> str:
    # ID curto por requisição para correlacionar logs (e, em produção, amarrar a um trace).
    return uuid.uuid4().hex[:12]


# Espelho em ARQUIVO dos eventos (data/usage_log.jsonl): é a fonte de "uso real" do B.I.
# (/kpis) — o stdout some quando o terminal fecha; o arquivo fica. Append sob lock
# (endpoint sync no threadpool) e SEMPRE em try/except: telemetria nunca derruba o /ask.
_file_lock = threading.Lock()


def _append_usage(line: str) -> None:
    if not config.USAGE_LOG_ENABLED:
        return
    try:
        with _file_lock:
            config.USAGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(config.USAGE_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception:
        pass   # sink de arquivo é observabilidade — falha silenciosa, nunca quebra a requisição


def log_event(event: str, **fields) -> None:
    """Emite UMA linha JSON por evento (JSON-lines). Esse formato é o que coletores
    (Langfuse/Phoenix/ELK) ingerem direto — log estruturado, não texto livre.
    A mesma linha vai ao stdout (coletor) e ao usage_log.jsonl (B.I. local)."""
    record = {"ts": round(time.time(), 3), "event": event, **fields}
    line = json.dumps(record, ensure_ascii=False)
    _logger.info(line)
    _append_usage(line)
