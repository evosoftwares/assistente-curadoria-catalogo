"""Sidebar: identidade do agente, ação principal, sugestões e (recolhidos) os detalhes técnicos.

Redesenhada para COERÊNCIA + AMIGABILIDADE: em vez de um painel de métricas técnicas (que
falava "openrouter/gemini/embeddings" para um usuário editorial), agora é o "perfil" do
assistente — espelha o "Oi! Sou seu assistente" do chat, mostra um status humano (🟢 pronto)
e tucks o jargão (modelo/backend) atrás do Modo técnico, que segue lá para a banca.
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
        ok = bool(health.get("llm_available"))
        n = health.get("catalog_size", "?")

        # --- Cartão de identidade (mesma "persona" do chat -> coerência visual) ---
        st.markdown(
            '<div class="agent-card">'
            '<div class="agent-avatar">📚</div>'
            '<div><div class="agent-name">Assistente de Curadoria</div>'
            '<div class="agent-role">Conheço o acervo e respondo com as fontes</div></div>'
            "</div>",
            unsafe_allow_html=True,
        )

        # --- Status HUMANO (não "LLM: openrouter"): verde pronto / amarelo modo básico ---
        if ok:
            st.markdown(
                '<div class="agent-status"><span class="dot"></span>Pronto para ajudar</div>'
                f'<div class="agent-sub">{n} livros no acervo · busca inteligente ativa</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="agent-status basic"><span class="dot"></span>Modo básico (sem IA generativa)</div>'
                f'<div class="agent-sub">{n} livros no acervo · busca por palavra-chave</div>',
                unsafe_allow_html=True,
            )

        st.write("")  # respiro antes da ação principal

        # --- Ação principal: convidativa (filled), key p/ o tema destacá-la dos itens-lista ---
        if st.button("✏️ Nova conversa", key="newchat", use_container_width=True):
            state.clear()
            st.rerun()

        # --- Sugestões: convite caloroso (as 10 do desafio ficam aqui, p/ a demo) ---
        with st.expander("💡 Não sabe o que perguntar?"):
            st.caption("Toque numa destas para experimentar:")
            for i, q in enumerate(_load_questions(), 1):
                if st.button(f"{i}. {q}", key=f"ex{i}", use_container_width=True):
                    state.set_pending(q)
                    st.rerun()

        st.divider()

        # --- Modo técnico: para a banca. Quando LIGADO, revela aqui o jargão que tiramos de cima. ---
        st.toggle("Modo técnico", key="debug_mode",
                  help="Mostra os bastidores em cada resposta — plano, ids, custo real e o "
                       "modelo que respondeu. Útil na apresentação técnica.")
        if state.debug_mode():
            busca = "híbrida (semântico+BM25)" if health.get("semantic_ready") else "BM25-only"
            st.caption(f"backend de chat: `{health.get('llm_backend', '?')}`")
            st.caption(f"modelo: `{health.get('model', '?')}`")
            st.caption(f"busca: {busca} · embeddings: `{health.get('embeddings_backend', '?')}`")

        st.caption("Respondo cada pergunta de forma independente — conversas com memória "
                   "(multi-turno) estão no roadmap. 🙂")
