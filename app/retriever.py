"""Recuperação híbrida.

Ordem (recomendada pelo red-team):
1. FILTROS DUROS são a fonte da verdade (ano/idioma sempre; gênero/público duros
   quando categóricos). 200 -> subconjunto. Se o subconjunto <= top_k, devolvemos
   TODO ele ranqueado (a fusão nunca derruba um membro filtrado).
2. Dentro do subconjunto, ranqueio HÍBRIDO: cosseno (semântico) + BM25 (lexical)
   fundidos por Reciprocal Rank Fusion. Filtros de gênero "soft" viram boost.
3. Guardamos o cosseno bruto do topo para um limiar de abstenção.
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
        if plan.publico_alvo:
            wanted = set(plan.publico_alvo)
            idx = [i for i in idx if self.catalog.books[i].get("publico_alvo") in wanted]
        if plan.hard_genre_filter and plan.generos:
            wanted = set(plan.generos)
            idx = [i for i in idx if wanted & set(self.catalog.books[i].get("generos", []))]

        if not idx:
            # Over-filtragem: relaxa gênero/público, mantém ano/idioma; se ainda vazio, usa tudo.
            notes.append("filtros duros zeraram; relaxando gênero/público")
            idx = list(range(len(self.ids)))
            if plan.ano_min is not None:
                idx = [i for i in idx if self.catalog.books[i]["ano_publicacao"] >= plan.ano_min]
            if plan.ano_max is not None:
                idx = [i for i in idx if self.catalog.books[i]["ano_publicacao"] <= plan.ano_max]
            if plan.idioma_contains:
                needle = normalize(plan.idioma_contains)
                idx = [i for i in idx if needle in normalize(self.catalog.books[i].get("idioma", ""))]
            if not idx:
                notes.append("ano/idioma também zeraram; usando catálogo inteiro")
                idx = list(range(len(self.ids)))
        return idx, notes

    @staticmethod
    def _rrf_ranks(scores: np.ndarray) -> dict[int, int]:
        """Mapa posição-no-subconjunto -> rank (0 = melhor) por score decrescente."""
        order = np.argsort(-scores)
        return {int(p): r for r, p in enumerate(order)}

    def retrieve(
        self, plan: RetrievalPlan, query_vecs: Optional[list[np.ndarray]], top_k: Optional[int] = None
    ) -> tuple[list[RetrievalResult], dict]:
        top_k = top_k or config.TOP_K
        cand, notes = self._hard_filter(plan)
        cand_books = [self.catalog.books[i] for i in cand]

        query_text = " ".join(plan.semantic_queries) or " ".join(b["titulo"] for b in cand_books[:1])
        q_tokens = tokenize(query_text)

        # --- BM25 sobre o subconjunto ---
        bm25_all = self.bm25.get_scores(q_tokens)  # vetor sobre TODOS os docs
        bm25_sub = np.array([bm25_all[i] for i in cand], dtype=np.float32)

        # --- Semântico (cosseno), OR entre sub-queries (pega o máximo) ---
        cos_sub = None
        top_cosine = None
        if query_vecs:
            mats = []
            for qv in query_vecs:
                mats.append(self.index.cosine_scores(qv, subset_idx=cand))
            cos_sub = np.max(np.vstack(mats), axis=0) if mats else None
            if cos_sub is not None and len(cos_sub):
                top_cosine = float(np.max(cos_sub))

        # --- Fusão RRF ---
        k = config.RRF_K
        fused = np.zeros(len(cand), dtype=np.float32)
        bm_ranks = self._rrf_ranks(bm25_sub)
        for p, r in bm_ranks.items():
            fused[p] += 1.0 / (k + r)
        if cos_sub is not None:
            cos_ranks = self._rrf_ranks(cos_sub)
            for p, r in cos_ranks.items():
                fused[p] += 1.0 / (k + r)

        # --- Boost de gênero soft (quando não é filtro duro) ---
        if plan.generos and not plan.hard_genre_filter:
            wanted = set(plan.generos)
            for p, b in enumerate(cand_books):
                if wanted & set(b.get("generos", [])):
                    fused[p] += 1.0 / k  # bônus equivalente a ~1 rank

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
