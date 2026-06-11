"""Painel de chat: estado vazio orientado à INTENÇÃO, histórico, respostas e entrada.

Desenhado para a intenção real do usuário interno da editora (editorial/marketing/vendas/
atendimento): ele quer PERGUNTAR e ver OS LIVROS — por isso:
- as REFERÊNCIAS são cards visíveis logo abaixo da resposta (são o produto, não um anexo);
- o selo de comportamento fala a língua do usuário ("não consta no catálogo", "preciso de
  mais contexto") em vez do jargão interno (abstain/clarify);
- a telemetria técnica (plano, ids, custo, tier) fica atrás do "Modo técnico" da sidebar —
  ruído zero para o usuário final, 1 clique para a banca;
- a tela vazia ensina O QUE dá para pedir com 4 intenções típicas clicáveis
  (tema · lista · filtro · checagem de título).

`_render_assistant` é a função ÚNICA de render de resposta — usada no histórico e na
resposta recém-chegada, para os dois caminhos nunca divergirem.
"""
from __future__ import annotations

import html

import streamlit as st

import api_client
import state

# Comportamento (taxonomia interna do backend) -> selo na LÍNGUA DO USUÁRIO + cor Carbon.
BADGE = {
    "answer": ("Resposta com fontes", "green"),
    "abstain": ("Não consta no catálogo", "red"),
    "clarify": ("Preciso de mais contexto", "blue"),
    "acknowledge_limitation": ("Limitação do dado", "yellow"),
}

# Intenções típicas do dia a dia da editora (mapeiam 1:1 aos caminhos do pipeline:
# semântico · diversidade · filtro+grupo · pertencimento). O rótulo É a pergunta enviada.
INTENTS = [
    "Quais livros temos sobre inteligência artificial?",
    "Sugira 5 livros infantis variados para o Dia das Crianças",
    "Lançamentos dos últimos 3 anos, por categoria",
    'Temos o livro "Memórias Póstumas de Brás Cubas" de Machado de Assis?',
]

_MAX_CARDS = 4   # cards visíveis por resposta; o resto vai num expander (Q6 traz 26 livros)


def render_empty_state() -> None:
    """Boas-vindas quando não há conversa: comunica O QUE o assistente sabe fazer.
    Clicar numa intenção envia a pergunta (set_pending + rerun p/ a tela já nascer limpa)."""
    st.markdown(
        '<div class="hero"><h3>Como posso ajudar com o catálogo?</h3>'
        "<p>Pergunte como você falaria com um colega que conhece os 200 livros de cor — "
        "eu respondo em segundos, sempre mostrando as fontes.</p></div>",
        unsafe_allow_html=True,
    )
    cols = st.columns(2)
    for i, q in enumerate(INTENTS):
        if cols[i % 2].button(q, key=f"intent{i}", use_container_width=True):
            state.set_pending(q)
            st.rerun()   # rerun: a próxima renderização já entra no modo conversa (sem o hero)


def _ref_card(ref: dict) -> str:
    """Card Carbon de UM livro. html.escape em TODO campo interpolado: o catálogo é dado
    não-confiável também no frontend (mesma postura anti-injeção do backend)."""
    titulo = html.escape(ref["titulo"])
    autores = html.escape(", ".join(ref["autores"]))
    tags = "".join(f'<span class="cds-tag">{html.escape(g)}</span>' for g in ref["generos"][:3])
    tags += f'<span class="cds-tag blue">{html.escape(ref["publico_alvo"])}</span>'
    return (f'<div class="ref-card"><div class="t">{titulo}'
            f'<span class="id">{html.escape(ref["id"])}</span></div>'
            f'<div class="m">{autores} · {ref["ano_publicacao"]}</div>{tags}</div>')


def _render_assistant(msg: dict) -> None:
    dbg = msg["debug"]
    label, color = BADGE.get(dbg["behavior"], (dbg["behavior"], ""))
    st.markdown(f'<span class="cds-tag {color}">{label}</span>', unsafe_allow_html=True)
    st.write(msg["content"])

    # Referências como CARDS visíveis (o usuário veio atrás dos livros). Acima de
    # _MAX_CARDS, o excedente vai num expander para a conversa não virar um mural.
    refs = msg["references"]
    if refs:
        for ref in refs[:_MAX_CARDS]:
            st.markdown(_ref_card(ref), unsafe_allow_html=True)
        if len(refs) > _MAX_CARDS:
            with st.expander(f"Ver os outros {len(refs) - _MAX_CARDS} livros"):
                for ref in refs[_MAX_CARDS:]:
                    st.markdown(_ref_card(ref), unsafe_allow_html=True)

    # Telemetria só no MODO TÉCNICO (toggle na sidebar): plano, ids, latência, custo real
    # e o tier do roteamento inteligente — a auditoria que a banca quer ver, sem poluir
    # a experiência de quem só quer consultar o catálogo.
    if state.debug_mode():
        with st.expander("🔍 Debug (plano, ids, latência, custo, roteamento)"):
            c1, c2, c3 = st.columns(3)
            c1.metric("Candidatos pós-filtro", dbg["candidate_count"])
            c2.metric("Latência (ms)", dbg["latency_ms"].get("total_ms", "?"))
            c3.metric("Custo (US$)", dbg["estimated_cost_usd"])
            st.write("**Plano de recuperação:**")
            st.json(dbg["plan"])
            st.write("**IDs recuperados (top-k):**", dbg["retrieved_ids"])
            st.write("**Tokens:**", dbg["tokens"])
            if dbg.get("top_cosine") is not None:
                st.write("**Cosseno do topo:**", round(dbg["top_cosine"], 4))
            if dbg.get("notes"):
                st.write("**Notas:**", dbg["notes"])  # inclui o tier do roteamento
            st.caption(f"from_cache={dbg['from_cache']}")


def render_history() -> None:
    for m in state.history():
        with st.chat_message(m["role"]):
            if m["role"] == "user":
                st.write(m["content"])
            else:
                _render_assistant(m)


def handle_input() -> None:
    """Lê a pergunta (chat livre OU intenção/atalho pendente) e processa.
    O Streamlit redesenha a tela a cada interação: a resposta processada aqui aparece
    inline AGORA e é re-renderizada a partir do histórico nos próximos reruns."""
    prompt = st.chat_input("Pergunte qualquer coisa sobre o catálogo…")
    if prompt is None:
        prompt = state.pop_pending()   # intenção do hero ou atalho da sidebar
    if not prompt:
        return

    state.add_user(prompt)
    with st.chat_message("user"):
        st.write(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Consultando o catálogo…"):
            try:
                data = api_client.ask(prompt)
            except Exception as e:
                # Erro de rede/API não entra no histórico (não é resposta) — só avisa.
                st.error(f"Erro ao chamar a API: {e}")
                return
        msg = state.add_assistant(data["answer"], data["references"], data["retrieval_debug"])
        _render_assistant(msg)
