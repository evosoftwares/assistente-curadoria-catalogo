"""UI mínima (Streamlit) para a demo ao vivo.

Mostra a resposta, as REFERÊNCIAS (livros usados) e um painel de debug com o plano
de recuperação, ids recuperados, latências por etapa e custo estimado — útil para a
banca enxergar o RAG por dentro mesmo quando a resposta não é perfeita.

Rodar:  streamlit run ui/streamlit_app.py
(É necessário ter o backend no ar:  uvicorn app.api:app)
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import httpx
import streamlit as st

API_BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@st.cache_data
def load_questions() -> list[str]:
    txt = (DATA_DIR / "questions.txt").read_text(encoding="utf-8")
    return [re.sub(r"^\d+\.\s*", "", ln).strip() for ln in txt.splitlines()
            if re.match(r"^\d+\.", ln.strip())]


def ask_api(question: str) -> dict:
    r = httpx.post(f"{API_BASE}/ask", json={"question": question}, timeout=60.0)
    r.raise_for_status()
    return r.json()


st.set_page_config(page_title="Curadoria do Catálogo", page_icon="📚", layout="wide")
st.title("📚 Assistente de Curadoria do Catálogo")
st.caption("Pergunte em português sobre o catálogo. As respostas vêm ancoradas nos livros (RAG híbrido).")

# Estado do backend
try:
    health = httpx.get(f"{API_BASE}/health", timeout=10.0).json()
    cols = st.columns(4)
    cols[0].metric("Catálogo", health.get("catalog_size", "?"))
    cols[1].metric("Semântico", "on" if health.get("semantic_ready") else "BM25-only")
    cols[2].metric("LLM", "on" if health.get("llm_available") else "degradado")
    cols[3].metric("Modelo", health.get("model", "?"))
except Exception as e:
    st.error(f"Backend indisponível em {API_BASE}. Suba com `uvicorn app.api:app`. ({e})")
    st.stop()

with st.sidebar:
    st.subheader("Perguntas-exemplo")
    if "q" not in st.session_state:
        st.session_state.q = ""
    for i, q in enumerate(load_questions(), 1):
        if st.button(f"{i}. {q[:48]}…", key=f"ex{i}", use_container_width=True):
            st.session_state.q = q

question = st.text_area("Sua pergunta", value=st.session_state.get("q", ""), height=90)
go = st.button("Perguntar", type="primary")

if go and question.strip():
    with st.spinner("Consultando o catálogo…"):
        try:
            data = ask_api(question)
        except Exception as e:
            st.error(f"Erro ao chamar a API: {e}")
            st.stop()

    dbg = data["retrieval_debug"]
    badge = {"answer": "✅ resposta", "abstain": "🚫 abstenção",
             "clarify": "❓ esclarecer", "acknowledge_limitation": "⚠️ limitação"}.get(dbg["behavior"], dbg["behavior"])
    st.markdown(f"**Comportamento:** {badge}")
    st.markdown("### Resposta")
    st.write(data["answer"])

    if data["references"]:
        st.markdown("### Referências (livros usados)")
        for ref in data["references"]:
            with st.expander(f"{ref['titulo']} ({ref['id']}) — {ref['ano_publicacao']}"):
                st.write(f"**Autores:** {', '.join(ref['autores'])}")
                st.write(f"**Gêneros:** {', '.join(ref['generos'])}")
                st.write(f"**Público:** {ref['publico_alvo']}  |  **Idioma:** {ref['idioma']}  |  **ISBN:** {ref['isbn']}")
                if ref.get("score") is not None:
                    st.caption(f"score de fusão: {ref['score']}")
    else:
        st.info("Sem referências (abstenção ou nada relevante).")

    with st.expander("🔍 Debug de recuperação (plano, ids, latência, custo)"):
        c1, c2, c3 = st.columns(3)
        c1.metric("Candidatos pós-filtro", dbg["candidate_count"])
        c2.metric("Latência total (ms)", dbg["latency_ms"].get("total_ms", "?"))
        c3.metric("Custo (US$)", dbg["estimated_cost_usd"])
        st.write("**Plano de recuperação:**")
        st.json(dbg["plan"])
        st.write("**IDs recuperados (top-k):**", dbg["retrieved_ids"])
        st.write("**Tokens:**", dbg["tokens"])
        if dbg.get("top_cosine") is not None:
            st.write("**Cosseno do topo:**", round(dbg["top_cosine"], 4))
        if dbg.get("notes"):
            st.write("**Notas:**", dbg["notes"])
        st.caption(f"from_cache={dbg['from_cache']}")
