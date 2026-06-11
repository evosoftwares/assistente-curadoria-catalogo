"""Estado da conversa — o ÚNICO dono do st.session_state.

Por quê: espalhar `st.session_state["..."]` pelos componentes cria acoplamento invisível
(um typo numa chave vira bug silencioso, e ninguém sabe quem muta o quê). Aqui ficam as
chaves, os defaults e as operações permitidas; os componentes só chamam funções nomeadas.

O histórico é VISUAL: o backend responde cada pergunta de forma independente (sem memória
de conversa) — multi-turno real é evolução planejada (docs/ROADMAP.md, v2).
"""
from __future__ import annotations

from typing import Optional

import streamlit as st


def init() -> None:
    """Garante as chaves com defaults — chamar uma vez no entrypoint, antes dos componentes."""
    st.session_state.setdefault("messages", [])     # [{role, content, references?, debug?}]
    st.session_state.setdefault("pending", None)    # pergunta vinda do hero/atalhos
    st.session_state.setdefault("debug_mode", False)  # telemetria por resposta (toggle da sidebar)


def debug_mode() -> bool:
    """Modo técnico ligado? (o toggle da sidebar usa key='debug_mode' e muta direto —
    esta função existe para os componentes LEREM por nome, não por chave mágica)."""
    return bool(st.session_state.get("debug_mode", False))


def history() -> list[dict]:
    return st.session_state.messages


def add_user(content: str) -> None:
    st.session_state.messages.append({"role": "user", "content": content})


def add_assistant(content: str, references: list[dict], debug: dict) -> dict:
    """Anexa a resposta e a DEVOLVE: quem chama renderiza o mesmo dict que foi guardado
    (histórico e resposta recém-chegada nunca divergem)."""
    msg = {"role": "assistant", "content": content, "references": references, "debug": debug}
    st.session_state.messages.append(msg)
    return msg


def clear() -> None:
    st.session_state.messages = []


def set_pending(question: str) -> None:
    # Os botões da sidebar não retornam valor no fluxo do chat_input — registram a
    # pergunta aqui e o próximo rerun a consome (pop_pending) como se digitada.
    st.session_state.pending = question


def pop_pending() -> Optional[str]:
    q = st.session_state.pending
    st.session_state.pending = None
    return q
