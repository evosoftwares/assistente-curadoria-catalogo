"""Entrypoint da UI — FINO de propósito: configura página/tema, valida o backend e
orquestra os componentes. A lógica vive nos módulos, espelhando a separação de
responsabilidades do backend (app/):

  ui/streamlit_app.py        orquestração (este arquivo — não cresce)
  ui/theme.py                Carbon Design System (IBM) por CSS + remoção do chrome
  ui/api_client.py           ÚNICA porta de saída para o backend (URL/timeout/erros)
  ui/state.py                ÚNICO dono do st.session_state (chaves, defaults, mutações)
  ui/components/sidebar.py   status do backend + ações + exemplos do desafio (recolhidos)
  ui/components/chat.py      estado vazio por INTENÇÃO + histórico + respostas + entrada

Experiência (desenhada pela intenção do usuário interno da editora): chat livre com
respostas ancoradas e OS LIVROS como cards visíveis; telemetria técnica só no "Modo
técnico". Cada pergunta é independente — multi-turno real: docs/ROADMAP.md (v2).

Rodar:  streamlit run ui/streamlit_app.py
(Backend no ar:  uvicorn app.api:app — ou tudo junto via scripts/run_local.ps1 / docker compose)
"""
from __future__ import annotations

import streamlit as st

import api_client
import browser_log
import state
import theme
from components import chat, sidebar

# layout="centered": coluna de leitura focada (Carbon privilegia colunas estreitas de
# texto); o que precisa de largura (JSON do plano) vive em expanders do modo técnico.
st.set_page_config(page_title="Curadoria do Catálogo", page_icon="📚", layout="centered")
theme.inject()
state.init()

st.title("Assistente de Curadoria do Catálogo")

# Gate do backend: sem API não há o que conversar — erro acionável em vez de tela quebrada.
try:
    health = api_client.get_health()
except Exception as e:
    st.error(f"Backend indisponível em {api_client.API_BASE}. "
             f"Suba com `uvicorn app.api:app` ou `scripts/run_local.ps1`. ({e})")
    st.stop()

sidebar.render(health)

# Estado do backend no console do navegador (F12) — uma vez por sessão, não a cada rerun.
if state.health_log_pending():
    browser_log.log_health(health)

# Tela vazia = onboarding por INTENÇÃO (o que dá para pedir); com conversa, só o chat.
if not state.history() and not st.session_state.pending:
    chat.render_empty_state()
else:
    chat.render_history()
chat.handle_input()
