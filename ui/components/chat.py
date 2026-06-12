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
import json

import streamlit as st

import api_client
import browser_log
import state

# Comportamento (taxonomia interna do backend) -> selo na LÍNGUA DO USUÁRIO, em tom de colega
# (não de status técnico) + cor Carbon. As fontes aparecem nos cards logo abaixo do selo.
BADGE = {
    "answer": ("Encontrei no acervo", "green"),
    "abstain": ("Esse a gente não tem", "red"),
    "clarify": ("Me conta um pouco mais?", "blue"),
    "acknowledge_limitation": ("O catálogo não detalha isso", "yellow"),
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
    # Tom de COLEGA (não de manual): saudação em 1ª pessoa + promessa de confiança ("não invento").
    # Copy é o principal lever de "parecer amigável" — Carbon dá a casca limpa, o texto dá o calor.
    st.markdown(
        '<div class="hero"><h3>Oi! 👋 Sou seu assistente de curadoria</h3>'
        "<p>Pode falar comigo com naturalidade, do seu jeito. Conheço os 200 livros do nosso "
        "acervo de cor e respondo na hora — sempre te mostrando em quais livros me baseei. "
        "E se a gente não tiver o que você procura, eu digo na lata: <b>não invento</b>. 🙂</p>"
        '<p class="hero-cta">Não sabe por onde começar? É só tocar numa ideia:</p></div>',
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


def _send_feedback(msg: dict, index: int, verdict: str, comment: str | None) -> None:
    """Monta o payload COMPLETO do par pergunta+resposta (com plano/ids/custo do debug) e
    envia ao backend — é o registro que vira gold-set vivo. Em erro, avisa sem quebrar o
    chat (feedback é acessório; a conversa nunca pode travar por causa dele)."""
    dbg = msg.get("debug") or {}
    payload = {
        "verdict": verdict,
        "question": msg.get("question") or "?",
        "answer": (msg.get("content") or "")[:8000],
        "comment": comment or None,
        "behavior": str(dbg.get("behavior", "")),
        "reference_ids": [r.get("id") for r in (msg.get("references") or []) if r.get("id")],
        "retrieved_ids": dbg.get("retrieved_ids") or [],
        "context_ids": dbg.get("context_ids") or [],
        "plan_json": json.dumps(dbg.get("plan") or {}, ensure_ascii=False)[:4000],
        "cost_usd": dbg.get("estimated_cost_usd", 0.0),
        "latency_ms": (dbg.get("latency_ms") or {}).get("total_ms"),
        "from_cache": bool(dbg.get("from_cache")),
    }
    try:
        api_client.send_feedback(payload)
    except Exception as e:
        st.toast(f"Ih, não consegui salvar seu feedback agora. Tenta de novo? ({e})", icon="⚠️")
        return
    state.set_feedback(index, verdict)
    st.rerun()   # redesenha: os botões viram o "obrigado" (1 voto por resposta)


def _feedback_row(msg: dict, index: int) -> None:
    """👍 envia direto; 👎 abre um popover com comentário OPCIONAL (o motivo do erro é o
    dado mais valioso do dataset — mas exigi-lo mataria a taxa de resposta).
    Layout: rótulo-guia + par de botões de LARGURA IGUAL (use_container_width em colunas
    iguais e estreitas) — alinhados como um par, não soltos/ragged."""
    if msg.get("feedback"):
        marca = "👍" if msg["feedback"] == "up" else "👎"
        st.caption(f"{marca} Valeu pelo retorno! Ele ajuda a deixar o assistente cada vez melhor.")
        return
    st.caption("Esta resposta te ajudou?")
    # Container COM KEY -> ganha a classe `st-key-fbrowN`, que o tema usa para forçar o emoji
    # AO LADO do texto (nowrap) SÓ aqui — sem reabrir o corte dos rótulos longos (chips/sidebar).
    # Colunas iguais e estreitas; o espaçador (4) empurra o par 👍/👎 para a esquerda.
    with st.container(key=f"fbrow{index}"):
        c1, c2, _ = st.columns([1, 1, 4])
        # icon= (nativo do Streamlit): renderiza o emoji AO LADO do texto pelo layout do
        # próprio framework — não depende de CSS e nunca empilha (o "👍 Sim" no label quebrava
        # na coluna estreita; com icon separado do rótulo, fica sempre na horizontal).
        if c1.button("Sim", icon="👍", key=f"fbu{index}", use_container_width=True):
            _send_feedback(msg, index, "up", None)
        with c2.popover("Não", icon="👎", use_container_width=True):
            st.markdown("**O que faltou?** _(opcional, mas ajuda muito)_")
            comment = st.text_area(
                "comentário", key=f"fbc{index}", max_chars=1000, label_visibility="collapsed",
                placeholder="Ex.: faltou o público-alvo, ou a resposta ficou genérica demais…")
            if st.button("Enviar", key=f"fbs{index}", use_container_width=True):
                _send_feedback(msg, index, "down", comment.strip() or None)


def _render_assistant(msg: dict, index: int) -> None:
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

    # Feedback humano por resposta (👍/👎) — alimenta data/feedback.jsonl via POST /feedback.
    _feedback_row(msg, index)


def render_history() -> None:
    for i, m in enumerate(state.history()):
        with st.chat_message(m["role"]):
            if m["role"] == "user":
                st.write(m["content"])
            else:
                _render_assistant(m, i)


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
        with st.spinner("Deixa eu procurar nos nossos livros…"):
            try:
                data = api_client.ask(prompt)
            except Exception as e:
                # Erro de rede/API não entra no histórico (não é resposta) — só avisa, com calma.
                st.error(f"Ops, tropecei aqui e não consegui responder agora. Tenta de novo em "
                         f"instantes? (detalhe técnico: {e})")
                return
        msg = state.add_assistant(data["answer"], data["references"], data["retrieval_debug"],
                                  question=prompt)
        _render_assistant(msg, len(state.history()) - 1)
    # Log completo no console do navegador (F12): fluxo seguido, referências, custo e o
    # debug bruto — só quando a resposta É NOVA (re-render de histórico não duplica logs).
    browser_log.log_qa(prompt, data)
