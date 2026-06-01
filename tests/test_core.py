"""Testes de regressão dos componentes DETERMINÍSTICOS (sem LLM/sem rede).

Travam os invariantes que a auditoria identificou como críticos: resolução de data,
agregação com empate, diversidade, verificação/coerção de citações, busca de título
(incl. anti-fragmento), reconciliação do planner e o comportamento E2E das 10 perguntas
em modo BM25-only. Rode com:  python -m pytest -q
"""
from __future__ import annotations

import json
from pathlib import Path

from app import tools
from app.catalog import get_catalog
from app.llm import GeminiClient
from app.models import Aggregation, Behavior
from app.pipeline import AskPipeline, _coerce_id_list
from app.planner import fallback_plan, resolve_year_bounds
from app.retriever import HybridRetriever, tokenize

ROOT = Path(__file__).resolve().parent.parent
CAT = get_catalog()


def _offline_pipeline() -> AskPipeline:
    """Pipeline sem chave: planner fallback + recuperação BM25-only + geração template."""
    return AskPipeline(client=GeminiClient(api_key=""))


# --- datas ---
def test_resolve_year_bounds_ultimos_3_anos():
    # CURRENT_YEAR=2026 (config) -> 'últimos 3 anos' == ano >= 2023
    assert resolve_year_bounds(3, None, None) == (2023, None)
    assert resolve_year_bounds(None, 2010, None) == (2010, None)


# --- agregação com empate ---
def test_aggregate_min_max_tie():
    books = [
        {"id": "A", "ano_publicacao": 1990}, {"id": "B", "ano_publicacao": 2024},
        {"id": "C", "ano_publicacao": 2024}, {"id": "D", "ano_publicacao": 2005},
    ]
    agg = tools.aggregate_min_max(books)
    assert agg["min_year"] == 1990 and [b["id"] for b in agg["oldest"]] == ["A"]
    assert agg["max_year"] == 2024 and {b["id"] for b in agg["newest"]} == {"B", "C"}


def test_aggregate_real_catalog():
    agg = tools.aggregate_min_max(CAT.books)
    assert agg["min_year"] == 1986 and agg["oldest"][0]["id"] == "BK0124"
    assert agg["max_year"] == 2024 and len(agg["newest"]) == 13


# --- diversidade ---
def test_diversify_one_per_value_and_completion():
    books = [{"id": str(i), "publico_alvo": "X"} for i in range(4)] + [{"id": "y", "publico_alvo": "Y"}]
    div = tools.diversify(books, "publico_alvo", n=3)
    assert div["distinct_count"] == 2  # só X e Y existem
    assert len(div["selected"]) == 3   # completa além de 1-por-faixa para atingir n


# --- citações ---
def test_coerce_id_list():
    assert _coerce_id_list(["BK0001", "BK0002"]) == ["BK0001", "BK0002"]
    assert _coerce_id_list("BK0133") == ["BK0133"]          # string NÃO vira lista de chars
    assert _coerce_id_list([1, "BK0001", None]) == ["BK0001"]  # descarta não-strings
    assert _coerce_id_list({"x": 1}) == []


# --- busca de título (anti-fragmento + abstenção) ---
def test_find_title_present_and_absent():
    assert CAT.find_title("Memórias Póstumas de Brás Cubas") == []   # fora do catálogo
    assert CAT.find_title("Dom Casmurro") == []
    full = CAT.find_title("Sistemas distribuídos para profissionais")
    assert full and any("distribu" in b["titulo"].lower() for b in full)
    # fragmento NÃO deve afirmar posse de um título maior (token_sort baixo)
    assert CAT.find_title("Liderança") == []


# --- planner determinístico (fallback) ---
def test_planner_aggregation_both_extremes():
    p = fallback_plan("Qual é o livro mais antigo? E o mais recente?", CAT)
    assert Aggregation.min_year in p.aggregations and Aggregation.max_year in p.aggregations
    assert p.is_ambiguous is False


def test_planner_single_extreme():
    p = fallback_plan("Qual o livro mais recente do catálogo?", CAT)
    assert p.aggregations == [Aggregation.max_year]


def test_planner_title_not_ambiguous():
    p = fallback_plan('Você tem o livro "Dom Casmurro" de Machado de Assis?', CAT)
    assert p.title_lookup and p.is_ambiguous is False  # título vence -> abstenção, não clarify


def test_planner_ambiguous_q9():
    p = fallback_plan('aquele livro do autor japonês sobre cidades, qual provavelmente é?', CAT)
    assert p.is_ambiguous is True and "japon" in (p.idioma_contains or "")


def test_planner_relative_year():
    p = fallback_plan("livros publicados nos últimos 3 anos, liste por categoria", CAT)
    assert p.ano_min == 2023 and p.group_by.value == "genero"


# --- tokenização / RRF ---
def test_tokenize_pt():
    toks = tokenize("Os livros sobre o CÉREBRO humano")
    assert "cerebro" in toks and "humano" in toks and "os" not in toks  # acento e stopword


def test_rrf_skips_zero_scores():
    import numpy as np
    scores = np.array([0.0, 0.0, 5.0], dtype=np.float32)
    contrib = HybridRetriever._rrf_contribution(scores, k=60, skip_zero=True)
    assert contrib[0] == 0.0 and contrib[1] == 0.0 and contrib[2] > 0.0  # zeros não contribuem


# --- E2E determinístico das 10 perguntas (BM25-only) ---
def test_e2e_behaviors_offline():
    gold = json.loads((ROOT / "eval" / "gold.json").read_text(encoding="utf-8"))
    pipe = _offline_pipeline()
    for item in gold:
        resp = pipe.ask(item["question"])
        assert resp.retrieval_debug.behavior.value == item["expected_behavior"], \
            f"Q{item['qid']}: esperado {item['expected_behavior']}, obtido {resp.retrieval_debug.behavior.value}"


def test_q10_abstains_with_no_references():
    pipe = _offline_pipeline()
    r = pipe.ask('Você tem em catálogo "Memórias Póstumas de Brás Cubas" de Machado de Assis?')
    assert r.retrieval_debug.behavior == Behavior.abstain and r.references == []
