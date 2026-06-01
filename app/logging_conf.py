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
import time
import uuid

_logger = logging.getLogger("curadoria")
if not _logger.handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(_h)
    _logger.setLevel(logging.INFO)


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def log_event(event: str, **fields) -> None:
    record = {"ts": round(time.time(), 3), "event": event, **fields}
    _logger.info(json.dumps(record, ensure_ascii=False))
