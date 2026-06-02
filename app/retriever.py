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
        notes: list[str] = []                 # avisos (ex.: relaxamento) que sobem ao debug
        idx = list(range(len(self.ids)))      # começa com TODOS os índices (0..199) e vai estreitando

        if plan.ano_min is not None:          # "publicados a partir de X" / "últimos N anos"
            idx = [i for i in idx if self.catalog.books[i]["ano_publicacao"] >= plan.ano_min]
        if plan.ano_max is not None:          # "até o ano X"
            idx = [i for i in idx if self.catalog.books[i]["ano_publicacao"] <= plan.ano_max]
        if plan.idioma_contains:              # ex.: "japonês" (casa "tradução do japonês")
            needle = normalize(plan.idioma_contains)   # sem acento/minúsculo p/ comparar
            idx = [i for i in idx if needle in normalize(self.catalog.books[i].get("idioma", ""))]
        if plan.publico_alvo:                 # público é restrição FACTUAL -> sempre filtro duro
            wanted = set(plan.publico_alvo)   # set p/ teste de pertencimento O(1)
            idx = [i for i in idx if self.catalog.books[i].get("publico_alvo") in wanted]
        if plan.hard_genre_filter and plan.generos:  # gênero só é duro quando CATEGÓRICO (Q4/Q6)
            wanted = set(plan.generos)
            idx = [i for i in idx if wanted & set(self.catalog.books[i].get("generos", []))]  # interseção

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
        order = np.argsort(-scores)                  # posições ordenadas do maior score p/ o menor
        contrib = np.zeros(len(scores), dtype=np.float32)  # contribuição de cada doc (0 por padrão)
        for r, p in enumerate(order):                # r = rank (0 = melhor), p = posição do doc
            if skip_zero and scores[p] <= 1e-9:      # doc sem sinal naquele ranker (ex.: BM25=0)?
                continue                             # -> não contribui (evita rank artificial)
            contrib[p] = 1.0 / (k + r)               # fórmula RRF: decai suave com o rank
        return contrib

    def retrieve(
        self, plan: RetrievalPlan, query_vecs: Optional[list[np.ndarray]], top_k: Optional[int] = None
    ) -> tuple[list[RetrievalResult], dict]:
        # top_k vem do parâmetro ou do default global (config.TOP_K = 8).
        top_k = top_k or config.TOP_K
        # PASSO 1 — filtros duros: reduz os 200 livros ao subconjunto que satisfaz ano/idioma/
        # público (e gênero, se categórico). `notes` registra eventuais relaxamentos.
        cand, notes = self._hard_filter(plan)
        # Materializa os dicts dos livros candidatos (índices -> registros) p/ uso adiante.
        cand_books = [self.catalog.books[i] for i in cand]
        # Se o filtro FACTUAL zerou (ex.: "em japonês de 2025" inexistente), não há o que
        # ranquear: devolvemos vazio e a geração se abstém (não "empurramos" o catálogo todo).
        if not cand:
            return [], {"candidate_count": 0, "top_cosine": None, "notes": notes,
                        "semantic_used": False, "retrieved_ids": []}

        # Sub-queries do planner (1 por conceito; várias em perguntas "A ou B"). Filtramos as
        # que tokenizam vazio; se não sobrar nenhuma, caímos para o título do 1º candidato
        # (garante que o BM25 sempre tem termos com que trabalhar).
        subqueries = [q for q in (plan.semantic_queries or []) if tokenize(q)] or \
                     [" ".join(b["titulo"] for b in cand_books[:1])]

        # PASSO 2a — sinal LEXICAL (BM25). Uma pontuação por sub-query e MAX entre elas:
        # isso implementa o "OU" ("A ou B") de forma simétrica ao lado semântico.
        bm25_mats = [self.bm25.get_scores(tokenize(q)) for q in subqueries]  # cada: score sobre os 200
        bm25_all = np.max(np.vstack(bm25_mats), axis=0)                      # OR-máximo entre sub-queries
        bm25_sub = np.array([bm25_all[i] for i in cand], dtype=np.float32)   # recorta só os candidatos

        # PASSO 2b — sinal SEMÂNTICO (cosseno). Só roda se houver embeddings da consulta
        # (há chave/cache); senão fica None e a fusão usa BM25 sozinho (degradação graciosa).
        cos_sub = None
        top_cosine = None
        if query_vecs:
            # cosseno de cada sub-query contra o subconjunto candidato; MAX entre elas (mesmo "OU").
            mats = [self.index.cosine_scores(qv, subset_idx=cand) for qv in query_vecs]
            cos_sub = np.max(np.vstack(mats), axis=0) if mats else None
            if cos_sub is not None and len(cos_sub):
                top_cosine = float(np.max(cos_sub))  # guardado p/ observabilidade (não p/ abstenção — ver config)

        # PASSO 3 — FUSÃO por Reciprocal Rank Fusion. Constante k amortece o peso do topo.
        k = config.RRF_K
        # Contribuição do BM25 com skip_zero=True: documentos com BM25=0 (não compartilham
        # nenhum termo) NÃO recebem rank — senão a massa irrelevante ganharia posição só pela
        # ordem de empate, enviesando a fusão.
        fused = self._rrf_contribution(bm25_sub, k, skip_zero=True)
        # Soma a contribuição do cosseno (se houver). Cosseno é contínuo (sem empates em massa),
        # então ranqueamos TODOS (skip_zero=False). fused[p] = 1/(k+rank_bm25) + 1/(k+rank_cos).
        if cos_sub is not None:
            fused = fused + self._rrf_contribution(cos_sub, k, skip_zero=False)

        # PASSO 4 — boost de gênero SOFT: só quando o gênero é TEMA da busca (não filtro duro).
        if plan.generos and not plan.hard_genre_filter:
            wanted = set(plan.generos)            # gêneros pedidos
            boost = 0.2 / k                        # ~1/5 de uma contribuição rank-0: empurra sem dominar
            for p, b in enumerate(cand_books):     # p = posição no subconjunto candidato
                if wanted & set(b.get("generos", [])):  # interseção não-vazia = livro é do gênero pedido
                    fused[p] += boost

        # PASSO 5 — ordena por score fundido (desc). argsort(-x) = índices do maior p/ menor.
        order = list(np.argsort(-fused))
        # Se o conjunto filtrado é pequeno (<= top_k), devolve TODO ele ranqueado — a fusão não
        # pode "perder" um membro que passou no filtro duro. Caso contrário, corta no top_k.
        limit = len(cand) if len(cand) <= top_k else top_k
        results: list[RetrievalResult] = []
        for p in order[:limit]:                    # p percorre as melhores posições, em ordem
            results.append(
                RetrievalResult(
                    book=cand_books[p],            # o livro naquela posição
                    fused=float(fused[p]),         # score fundido (para o pipeline expor/ordenar)
                    cosine=float(cos_sub[p]) if cos_sub is not None else None,  # cosseno bruto (debug)
                    bm25=float(bm25_sub[p]),       # score lexical bruto (debug)
                )
            )
        # `debug` alimenta retrieval_debug (observabilidade) e a avaliação (retrieved_ids).
        debug = {
            "candidate_count": len(cand),                       # quantos passaram no filtro duro
            "top_cosine": top_cosine,                           # maior cosseno (sinal de relevância)
            "notes": notes,                                     # relaxamentos/avisos do filtro
            "semantic_used": cos_sub is not None,               # rodou em modo híbrido ou BM25-only?
            "retrieved_ids": [r.book["id"] for r in results],   # IDs entregues (p/ métricas e demo)
        }
        return results, debug

    def candidates(self, plan: RetrievalPlan) -> list[dict]:
        """Conjunto pós-filtro SEM ranqueio — usado por group_by/aggregation/diversity, que
        operam sobre TODO o subconjunto (ex.: "liste por categoria" precisa dos 26, não do top-8)."""
        cand, _ = self._hard_filter(plan)
        return [self.catalog.books[i] for i in cand]
