"""Recuperação híbrida.

Ordem (recomendada pelo red-team):
1. FILTROS DUROS são a fonte da verdade. ano/idioma e público são SEMPRE duros (são
   restrições FACTUAIS — o público-alvo é um atributo categórico do livro). O GÊNERO é
   duro só quando categórico (is_categorical); senão vira boost soft. 200 -> subconjunto.
   Se o subconjunto <= top_k, devolvemos TODO ele ranqueado (a fusão não derruba membro).
   Se o filtro factual (ano/idioma) zerar, devolvemos VAZIO (a geração se abstém).
2. Dentro do subconjunto, ranqueio HÍBRIDO: cosseno (semântico) + BM25 (lexical, OR por
   sub-query) fundidos por Reciprocal Rank Fusion (BM25 ignora zeros). Gênero soft = boost.
3. Expomos o cosseno bruto do topo (top_cosine) para observabilidade/debug. (Um limiar de
   abstenção por cosseno foi avaliado e descartado — ver nota em config.py.)
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

import numpy as np
from rank_bm25 import BM25Okapi

from . import config
from .catalog import Catalog, normalize
from .embeddings import EmbeddingIndex
from .models import RetrievalPlan

# Stopwords PT enxutas — não removemos nomes próprios (importam p/ Q9/Q10).
_STOPWORDS = {
    "a", "o", "os", "as", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das",
    "e", "ou", "que", "com", "sem", "para", "por", "no", "na", "nos", "nas", "em",
    "ao", "aos", "se", "sua", "seu", "suas", "seus", "the", "of", "sobre", "como",
    "qual", "quais", "quem", "tem", "temos", "ha", "nosso", "nossa", "nossos", "nossas",
}


def tokenize(text: str) -> list[str]:
    norm = normalize(text)
    tokens = re.split(r"[^0-9a-zà-ÿ]+", norm)
    return [t for t in tokens if len(t) >= 2 and t not in _STOPWORDS]


class RetrievalResult:
    def __init__(self, book: dict, fused: float, cosine: Optional[float], bm25: Optional[float]):
        self.book = book
        self.fused = fused
        self.cosine = cosine
        self.bm25 = bm25


class HybridRetriever:
    def __init__(self, catalog: Catalog, index: EmbeddingIndex):
        self.catalog = catalog
        self.index = index
        self.ids = catalog.ids
        self.pos = {bid: i for i, bid in enumerate(self.ids)}
        self._corpus_tokens = [tokenize(t) for t in catalog.all_doc_texts()]
        self.bm25 = BM25Okapi(self._corpus_tokens)

    # --- filtros duros ---
    def _hard_filter(self, plan: RetrievalPlan) -> tuple[list[int], list[str]]:
        notes: list[str] = []
        idx = list(range(len(self.ids)))

        if plan.ano_min is not None:
            idx = [i for i in idx if self.catalog.books[i]["ano_publicacao"] >= plan.ano_min]
        if plan.ano_max is not None:
            idx = [i for i in idx if self.catalog.books[i]["ano_publicacao"] <= plan.ano_max]
        if plan.idioma_contains:
            needle = normalize(plan.idioma_contains)
            idx = [i for i in idx if needle in normalize(self.catalog.books[i].get("idioma", ""))]
        if plan.publico_alvo:  # público é restrição factual -> sempre filtro duro
            wanted = set(plan.publico_alvo)
            idx = [i for i in idx if self.catalog.books[i].get("publico_alvo") in wanted]
        if plan.hard_genre_filter and plan.generos:
            wanted = set(plan.generos)
            idx = [i for i in idx if wanted & set(self.catalog.books[i].get("generos", []))]

        if not idx:
            # Over-filtragem: relaxamos só o filtro TEMÁTICO (gênero) e MANTEMOS as
            # restrições FACTUAIS — ano/idioma/público. Público é atributo categórico do
            # livro (não tema), então não pode ser silenciosamente trocado. Se ainda assim
            # zerar, devolvemos VAZIO (a geração ancorada se abstém) em vez de cair no
            # catálogo inteiro e "responder" como se houvesse resultados.
            notes.append("filtro temático (gênero) relaxado; ano/idioma/público mantidos")
            idx = list(range(len(self.ids)))
            if plan.ano_min is not None:
                idx = [i for i in idx if self.catalog.books[i]["ano_publicacao"] >= plan.ano_min]
            if plan.ano_max is not None:
                idx = [i for i in idx if self.catalog.books[i]["ano_publicacao"] <= plan.ano_max]
            if plan.idioma_contains:
                needle = normalize(plan.idioma_contains)
                idx = [i for i in idx if needle in normalize(self.catalog.books[i].get("idioma", ""))]
            if plan.publico_alvo:  # público é restrição FACTUAL -> mantido no relaxamento
                wanted = set(plan.publico_alvo)
                idx = [i for i in idx if self.catalog.books[i].get("publico_alvo") in wanted]
            if not idx:
                notes.append("nenhum livro satisfaz ano/idioma/público pedidos -> conjunto vazio (abstém)")
        return idx, notes

    @staticmethod
    def _rrf_contribution(scores: np.ndarray, k: int, skip_zero: bool = False) -> np.ndarray:
        """Contribuição RRF por documento: 1/(k+rank), rank por score decrescente.
        Com skip_zero=True, documentos com score<=0 NÃO contribuem (evita que a massa
        de BM25=0, lexicalmente irrelevante, receba ranks distintos só pela ordenação)."""
        order = np.argsort(-scores)
        contrib = np.zeros(len(scores), dtype=np.float32)
        for r, p in enumerate(order):
            if skip_zero and scores[p] <= 1e-9:
                continue
            contrib[p] = 1.0 / (k + r)
        return contrib

    def retrieve(
        self, plan: RetrievalPlan, query_vecs: Optional[list[np.ndarray]], top_k: Optional[int] = None
    ) -> tuple[list[RetrievalResult], dict]:
        top_k = top_k or config.TOP_K
        cand, notes = self._hard_filter(plan)
        cand_books = [self.catalog.books[i] for i in cand]
        if not cand:  # conjunto vazio (filtro factual insatisfazível) -> sem resultados
            return [], {"candidate_count": 0, "top_cosine": None, "notes": notes,
                        "semantic_used": False, "retrieved_ids": []}

        subqueries = [q for q in (plan.semantic_queries or []) if tokenize(q)] or \
                     [" ".join(b["titulo"] for b in cand_books[:1])]

        # --- BM25: OR por sub-query (max), espelhando o lado semântico ---
        bm25_mats = [self.bm25.get_scores(tokenize(q)) for q in subqueries]
        bm25_all = np.max(np.vstack(bm25_mats), axis=0)
        bm25_sub = np.array([bm25_all[i] for i in cand], dtype=np.float32)

        # --- Semântico (cosseno), OR entre sub-queries (pega o máximo) ---
        cos_sub = None
        top_cosine = None
        if query_vecs:
            mats = [self.index.cosine_scores(qv, subset_idx=cand) for qv in query_vecs]
            cos_sub = np.max(np.vstack(mats), axis=0) if mats else None
            if cos_sub is not None and len(cos_sub):
                top_cosine = float(np.max(cos_sub))

        # --- Fusão RRF. BM25 ignora zeros (massa lexicalmente irrelevante não recebe
        #     ranks artificiais); cosseno é contínuo e ranqueia todos. ---
        k = config.RRF_K
        fused = self._rrf_contribution(bm25_sub, k, skip_zero=True)
        if cos_sub is not None:
            fused = fused + self._rrf_contribution(cos_sub, k, skip_zero=False)

        # --- Boost de gênero soft (quando o gênero é TEMA, não filtro duro). Calibrado
        #     para subir poucas posições (não dominar): fração pequena de uma contribuição. ---
        if plan.generos and not plan.hard_genre_filter:
            wanted = set(plan.generos)
            boost = 0.2 / k
            for p, b in enumerate(cand_books):
                if wanted & set(b.get("generos", [])):
                    fused[p] += boost

        order = list(np.argsort(-fused))
        # Se o subconjunto filtrado é pequeno, devolve todo ele; senão, top_k.
        limit = len(cand) if len(cand) <= top_k else top_k
        results: list[RetrievalResult] = []
        for p in order[:limit]:
            results.append(
                RetrievalResult(
                    book=cand_books[p],
                    fused=float(fused[p]),
                    cosine=float(cos_sub[p]) if cos_sub is not None else None,
                    bm25=float(bm25_sub[p]),
                )
            )
        debug = {
            "candidate_count": len(cand),
            "top_cosine": top_cosine,
            "notes": notes,
            "semantic_used": cos_sub is not None,
            "retrieved_ids": [r.book["id"] for r in results],
        }
        return results, debug

    def candidates(self, plan: RetrievalPlan) -> list[dict]:
        """Apenas o conjunto pós-filtro (sem ranqueio) — usado por group_by/aggregation."""
        cand, _ = self._hard_filter(plan)
        return [self.catalog.books[i] for i in cand]
