"""Configuração global da suíte.

Desliga o espelho de uso em arquivo (usage_log.jsonl) durante os testes: os endpoints
são exercitados com perguntas sintéticas ("pergunta 0...", "spoof ...") que poluiriam o
B.I. de uso real (/kpis). Os testes que PRECISAM de persistência (feedback) apontam o
path para tmp_path via monkeypatch — nunca para os arquivos reais de data/.
"""
from __future__ import annotations

from app import config

config.USAGE_LOG_ENABLED = False
