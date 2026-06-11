"""Tema Carbon (IBM Design System) aplicado por CSS sobre o Streamlit nativo.

Por que CSS injetado (e não um framework de frontend): o desafio pede UI mínima e
funcional; o Carbon entra como LINGUAGEM VISUAL — IBM Plex, cantos retos, Blue 60
(#0f62fe), camadas cinza (#f4f4f4), tags e cards — sem dependência nova e sem build.
Tokens de referência: https://carbondesignsystem.com (White theme).

Também REMOVE o chrome do Streamlit (menu ⋮ e botão Deploy no canto direito, barra
decorativa colorida, widget de status, footer): para o usuário interno da editora
isso é ruído sem função numa ferramenta de consulta.

A fonte IBM Plex vem do Google Fonts (precisa de internet); sem rede, degrada para a
sans-serif do sistema — o layout não quebra.
"""
from __future__ import annotations

import streamlit as st

_CARBON_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400&display=swap');

/* ---------- Tipografia: IBM Plex em tudo; Plex Mono no que é código/dado ---------- */
html, body, [data-testid="stAppViewContainer"] * {
    font-family: 'IBM Plex Sans', -apple-system, 'Segoe UI', sans-serif;
}
code, pre, [data-testid="stJson"] * { font-family: 'IBM Plex Mono', monospace; }
h1 { font-weight: 600; font-size: 1.6rem; }

/* ---------- Remove o chrome do Streamlit (acessos do canto direito + enfeites) ---------- */
#MainMenu, [data-testid="stToolbar"], [data-testid="stAppDeployButton"], .stDeployButton,
[data-testid="stDecoration"], [data-testid="stStatusWidget"], footer {
    display: none !important; visibility: hidden !important;
}
/* header fica, transparente (some o fundo, preserva o controle de recolher a sidebar) */
header[data-testid="stHeader"] { background: transparent; }

/* ---------- Carbon = cantos RETOS (border-radius 0 em superfícies e controles) ---------- */
.stButton > button, [data-testid="stExpander"] details, [data-testid="stChatMessage"],
[data-testid="stChatInput"] > div, div[data-baseweb="input"], div[data-baseweb="textarea"] {
    border-radius: 0 !important;
}

/* ---------- Mensagens do chat: cards planos com borda fina; resposta da IA na camada
     cinza com acento azul à esquerda (padrão Carbon de destaque de conteúdo) ---------- */
[data-testid="stChatMessage"] {
    background: #ffffff; border: 1px solid #e0e0e0;
    padding: 0.9rem 1rem; margin-bottom: 0.5rem;
}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
    background: #f4f4f4; border-left: 3px solid #0f62fe;
}

/* ---------- Entrada do chat: campo Carbon (borda fina; foco = sublinhado Blue 60) ---------- */
[data-testid="stChatInput"] { border: 1px solid #8d8d8d; background: #ffffff; }
[data-testid="stChatInput"]:focus-within {
    border-color: #0f62fe; box-shadow: 0 2px 0 0 #0f62fe;
}
[data-testid="stChatInput"] textarea { background: #ffffff; color: #161616; }

/* ---------- Botões NUNCA cortam texto: rótulo quebra linha e a altura acompanha
     (o default do Streamlit ellipsa/clipa rótulos longos — pior que quebrar) ---------- */
.stButton > button { white-space: normal !important; height: auto !important; }
.stButton > button div, .stButton > button p {
    white-space: normal !important; overflow: visible !important;
    text-overflow: clip !important; word-break: break-word;
}

/* ---------- Sidebar: camada cinza com divisa; botões "ghost" (lista, não pílulas) ---------- */
section[data-testid="stSidebar"] { background: #f4f4f4; border-right: 1px solid #e0e0e0; }
section[data-testid="stSidebar"] .stButton > button {
    background: transparent; border: none; color: #161616;
    justify-content: flex-start; text-align: left;
    padding: 0.35rem 0.5rem; font-size: 0.85rem; width: 100%;
}
section[data-testid="stSidebar"] .stButton > button:hover { background: #e0e0e0; color: #0f62fe; }

/* ---------- Botões da área principal (chips de intenção): tertiary do Carbon ---------- */
[data-testid="stMain"] .stButton > button, .main .stButton > button {
    background: #ffffff; border: 1px solid #0f62fe; color: #0f62fe;
    font-weight: 500; width: 100%; min-height: 3rem; padding: 0.6rem 0.9rem;
}
[data-testid="stMain"] .stButton > button:hover, .main .stButton > button:hover {
    background: #0f62fe; color: #ffffff;
}

/* ---------- Expanders e métricas discretos (valores/rótulos quebram, não cortam) ---------- */
[data-testid="stExpander"] details { border: 1px solid #e0e0e0; background: #ffffff; }
[data-testid="stMetricValue"] { font-size: 1.05rem; font-weight: 600; white-space: normal; overflow: visible; }
[data-testid="stMetricLabel"] { font-size: 0.72rem; color: #525252; }
[data-testid="stMetricLabel"] p { white-space: normal !important; }

/* ---------- Componentes próprios: tag (pílula Carbon) e card de referência ----------
     white-space normal: público-alvo é longo ("Profissionais de dados e analistas") —
     a tag quebra linha dentro da pílula em vez de estourar/cortar no limite do card. */
.cds-tag {
    display: inline-block; padding: 0.1rem 0.6rem; margin: 0 0.25rem 0.25rem 0;
    font-size: 0.74rem; line-height: 1.15rem; border-radius: 1rem;
    background: #e0e0e0; color: #161616; white-space: normal;
    max-width: 100%; overflow-wrap: break-word;
}
.cds-tag.blue   { background: #d0e2ff; color: #0043ce; }
.cds-tag.green  { background: #a7f0ba; color: #0e6027; }
.cds-tag.red    { background: #ffd7d9; color: #a2191f; }
.cds-tag.yellow { background: #fcf4d6; color: #684e00; }

.ref-card {
    background: #ffffff; border: 1px solid #e0e0e0;
    padding: 0.7rem 0.9rem; margin-bottom: 0.5rem;
}
.ref-card .t  { font-weight: 600; font-size: 0.9rem; color: #161616; }
.ref-card .id { color: #525252; font-family: 'IBM Plex Mono', monospace;
                font-size: 0.72rem; margin-left: 0.35rem; }
.ref-card .m  { color: #525252; font-size: 0.8rem; margin: 0.15rem 0 0.4rem; }

/* ---------- Estado vazio (boas-vindas orientadas à intenção) ---------- */
.hero { padding: 1.25rem 0 0.5rem; }
.hero h3 { font-weight: 400; color: #161616; margin-bottom: 0.25rem; }
.hero p  { color: #525252; font-size: 0.95rem; }
</style>
"""


def inject() -> None:
    """Injeta o tema uma vez por rerun — chamar logo após o set_page_config."""
    st.markdown(_CARBON_CSS, unsafe_allow_html=True)
