"""Carregamento do catálogo, vocabulário controlado, clusters de edição e
busca exata/fuzzy de título+autor.

O catálogo é pequeno (~200 livros) e cabe inteiro em memória. Tudo aqui é
determinístico e independe do LLM/embeddings.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

from rapidfuzz import fuzz, process

from . import config


def normalize(text: str) -> str:
    """minúsculas + sem acentos + espaços colapsados. Base de toda comparação."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    no_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", no_accents.lower()).strip()


# Sufixos de edição/variante que NÃO mudam a "obra" — usados para agrupar duplicatas.
_EDITION_SUFFIX = re.compile(
    r"\s*[-—:]\s*("
    r"(nova|segunda|terceira|2a|3a|2ª|3ª)\s+edicao"
    r"|edicao\s+(revista|comentada|ampliada|especial|definitiva|atualizada)"
    r"|novos\s+caminhos"
    r"|antologia"
    r"|uma\s+introducao"
    r").*$",
    re.IGNORECASE,
)


def _work_key(titulo: str, autores: list[str]) -> str:
    """Chave de 'obra' para agrupar edições/variantes do mesmo título.

    Agrupamos apenas pelo TÍTULO normalizado (sem sufixo de edição). O autor é
    ignorado de propósito: no catálogo (sintético) as variantes de edição do mesmo
    título às vezes vêm com autores diferentes, e o objetivo do cluster é deduplicar
    quase-idênticos para as métricas de recuperação não ficarem distorcidas."""
    return _EDITION_SUFFIX.sub("", normalize(titulo)).strip()


class Catalog:
    def __init__(self, books_path: Path | None = None):
        self.path = Path(books_path or config.BOOKS_PATH)
        self.raw_bytes = self.path.read_bytes()
        self.books: list[dict] = json.loads(self.raw_bytes.decode("utf-8"))
        self.by_id: dict[str, dict] = {b["id"]: b for b in self.books}

        # Vocabulário controlado (valores REAIS presentes nos dados).
        self.generos_vocab: list[str] = sorted({g for b in self.books for g in b.get("generos", [])})
        self.publico_vocab: list[str] = sorted({b.get("publico_alvo", "") for b in self.books if b.get("publico_alvo")})
        self.idiomas_vocab: list[str] = sorted({b.get("idioma", "") for b in self.books if b.get("idioma")})

        # Clusters de edição: cluster_id estável por "obra".
        self._cluster_of: dict[str, str] = {}
        work_to_cluster: dict[str, str] = {}
        for b in self.books:
            wk = _work_key(b["titulo"], b.get("autores", []))
            if wk not in work_to_cluster:
                work_to_cluster[wk] = f"C{len(work_to_cluster):04d}"
            self._cluster_of[b["id"]] = work_to_cluster[wk]

        # Índice para busca fuzzy de título(+autor).
        self._title_author_index: dict[str, str] = {
            b["id"]: normalize(f"{b['titulo']} {' '.join(b.get('autores', []))}") for b in self.books
        }

    # --- acesso ---
    def get(self, book_id: str) -> Optional[dict]:
        return self.by_id.get(book_id)

    def cluster_of(self, book_id: str) -> str:
        return self._cluster_of.get(book_id, book_id)

    def __len__(self) -> int:
        return len(self.books)

    # --- texto para embedding / BM25 ---
    @staticmethod
    def doc_text(book: dict) -> str:
        """Texto canônico indexado. Inclui gênero/público (sinal semântico de audiência),
        mas NÃO ano/idioma — esses ficam só como filtro estruturado."""
        autores = ", ".join(book.get("autores", []))
        generos = ", ".join(book.get("generos", []))
        return (
            f"{book['titulo']}. {autores}. "
            f"Gêneros: {generos}. Público: {book.get('publico_alvo', '')}. "
            f"{book.get('sinopse', '')}"
        )

    def all_doc_texts(self) -> list[str]:
        return [self.doc_text(b) for b in self.books]

    @property
    def ids(self) -> list[str]:
        return [b["id"] for b in self.books]

    # --- busca de pertencimento (Q10) ---
    def find_title(self, query: str, threshold: int | None = None) -> list[dict]:
        """Retorna livros cujo título+autor casam com a consulta acima do limiar
        (rapidfuzz token_set_ratio). Lista vazia => provavelmente fora do catálogo."""
        threshold = config.TITLE_MATCH_THRESHOLD if threshold is None else threshold
        q = normalize(query)
        if not q:
            return []
        matches = process.extract(
            q, self._title_author_index, scorer=fuzz.token_set_ratio, limit=5
        )
        # process.extract com dict retorna (valor, score, chave=id)
        return [self.by_id[book_id] for _val, score, book_id in matches if score >= threshold]

    # --- validação de vocabulário (anti-filtro-vazio) ---
    def match_vocab(self, value: str, vocab: list[str], threshold: int = 80) -> Optional[str]:
        """Mapeia um valor proposto pelo planner ao termo de vocabulário mais próximo;
        None se nada passar do limiar (descartamos para não zerar o filtro)."""
        if not value:
            return None
        norm_vocab = {normalize(v): v for v in vocab}
        nv = normalize(value)
        if nv in norm_vocab:
            return norm_vocab[nv]
        best = process.extractOne(nv, list(norm_vocab.keys()), scorer=fuzz.token_set_ratio)
        if best and best[1] >= threshold:
            return norm_vocab[best[0]]
        return None

    def match_generos(self, values: Iterable[str]) -> list[str]:
        out = []
        for v in values:
            m = self.match_vocab(v, self.generos_vocab)
            if m and m not in out:
                out.append(m)
        return out

    def match_publico(self, values: Iterable[str]) -> list[str]:
        """Público é texto livre; casamos por substring normalizada (ex.: 'infantil'
        deve pegar 'Crianças de 4 a 10 anos' via mapeamento de palavras-chave)."""
        out: list[str] = []
        synonyms = {
            "infantil": ["crianca", "infantil"],
            "crianca": ["crianca", "infantil"],
            "criancas": ["crianca", "infantil"],
            "jovem": ["jovens", "juvenil", "adolescente"],
            "juvenil": ["jovens", "juvenil", "adolescente"],
            "ensino medio": ["ensino medio"],
            "ensino fundamental": ["ensino fundamental"],
            "universitario": ["universitario"],
        }
        for v in values:
            nv = normalize(v)
            keys = synonyms.get(nv, [nv])
            for pub in self.publico_vocab:
                npub = normalize(pub)
                if any(k in npub for k in keys) and pub not in out:
                    out.append(pub)
            # fallback fuzzy direto
            if not out:
                m = self.match_vocab(v, self.publico_vocab)
                if m:
                    out.append(m)
        return out


@lru_cache(maxsize=1)
def get_catalog() -> Catalog:
    """Singleton do catálogo (carrega uma vez por processo)."""
    return Catalog()
