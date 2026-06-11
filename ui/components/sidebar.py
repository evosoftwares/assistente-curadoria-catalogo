"""Sidebar: status do backend, ações da conversa e (recolhidas) as perguntas do desafio.

Hierarquia pensada pela intenção de uso: quem consulta o catálogo NÃO precisa das
perguntas-exemplo — elas existem para a demo da banca (roteiro Q8→Q4→Q10), então vivem
num expander recolhido. O "Modo técnico" liga a telemetria por resposta (debug) — desligado
por padrão: o usuário final vê só conversa e livros.
"""
from __future__ import annotations

import re
from pathlib import Path

import streamlit as st

import state

# ui/components/sidebar.py -> components -> ui -> raiz do projeto
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


@st.cache_data
def _load_questions() -> list[str]:
    txt = (DATA_DIR / "questions.txt").read_text(encoding="utf-8")
    return [re.sub(r"^\d+\.\s*", "", ln).strip() for ln in txt.splitlines()
            if re.match(r"^\d+\.", ln.strip())]


def render(health: dict) -> None:
    with st.sidebar:
        # --- Status: o MODO real do backend, sempre visível (degradado nunca é surpresa) ---
        st.subheader("Catálogo")
        c1, c2 = st.columns(2)
        c1.metric("Livros", health.get("catalog_size", "?"))
        c2.metric("Busca", "híbrida" if health.get("semantic_ready") else "BM25")
        c3, c4 = st.columns(2)
        c3.metric("LLM", health.get("llm_backend", "?") if health.get("llm_available") else "off")
        c4.metric("Embeddings", health.get("embeddings_backend", "?"))
        st.caption(f"Modelo: `{health.get('model', '?')}`")

        st.divider()

        # --- Ações ---
        if st.button("Nova conversa", use_container_width=True):
            state.clear()
            st.rerun()
        # key="debug_mode" sincroniza direto com o session_state (chave documentada em state.py)
        st.toggle("Modo técnico (debug por resposta)", key="debug_mode",
                  help="Mostra plano de recuperação, ids, latência, custo real e o tier "
                       "do roteamento em cada resposta — útil na apresentação técnica.")

        st.divider()

        # --- Perguntas do desafio: recolhidas (são da demo, não do dia a dia) ---
        # Rótulo INTEIRO no botão (sem cortar com "…"): o CSS do tema quebra linha e a
        # altura acompanha — texto cortado esconde exatamente o que diferencia as perguntas.
        with st.expander("Perguntas-exemplo do desafio (10)"):
            for i, q in enumerate(_load_questions(), 1):
                if st.button(f"{i}. {q}", key=f"ex{i}", use_container_width=True):
                    state.set_pending(q)
                    st.rerun()   # a pergunta entra no chat já no próximo desenho da tela

        st.caption("Cada pergunta é respondida de forma independente — "
                   "multi-turno real está no roadmap (v2).")
