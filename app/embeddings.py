"""Índice de embeddings com cache em disco.

Decisões:
- Backend padrão = Gemini (`gemini-embedding-001`, 768d via MRL). Sem dependência
  pesada (torch). Cache em disco chaveado por sha256(books.json)+backend+modelo+dim,
  então só re-embeddamos quando o catálogo muda. O cache é commitado no repo para
  o revisor rodar a recuperação OFFLINE, sem chave.
- `task_type` assimétrico: RETRIEVAL_DOCUMENT no corpus, RETRIEVAL_QUERY na consulta.
- Vetores L2-normalizados → produto interno == cosseno.
- Backend opcional "local" (sentence-transformers) para operação 100% offline.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

import numpy as np

from . import config
from .catalog import Catalog
from .llm import GeminiClient, get_client


def _l2_normalize(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


def _catalog_hash(catalog: Catalog) -> str:
    return hashlib.sha256(catalog.raw_bytes).hexdigest()[:16]


class EmbeddingIndex:
    """Matriz (N, dim) alinhada a ``catalog.ids``."""

    def __init__(self, catalog: Catalog, client: Optional[GeminiClient] = None):
        self.catalog = catalog
        self.client = client or get_client()
        self.backend = config.EMBEDDINGS_BACKEND
        self.dim = config.EMBEDDING_DIM
        self.matrix: Optional[np.ndarray] = None
        self.ids: list[str] = []
        self._local_model = None  # lazy

    # --- metadados do cache ---
    def _meta(self) -> dict:
        model = (
            config.LOCAL_EMBEDDING_MODEL if self.backend == "local" else config.GEMINI_EMBEDDING_MODEL
        )
        return {
            "catalog_hash": _catalog_hash(self.catalog),
            "backend": self.backend,
            "model": model,
            "dim": self.dim,
            "ids": self.catalog.ids,
        }

    def _cache_valid(self) -> bool:
        if not config.EMBEDDINGS_PATH.exists() or not config.EMBEDDINGS_META_PATH.exists():
            return False
        try:
            saved = json.loads(config.EMBEDDINGS_META_PATH.read_text(encoding="utf-8"))
        except Exception:
            return False
        cur = self._meta()
        return all(saved.get(k) == cur.get(k) for k in ("catalog_hash", "backend", "model", "dim"))

    # --- construção / carga ---
    def load(self) -> bool:
        if not self._cache_valid():
            return False
        self.matrix = np.load(config.EMBEDDINGS_PATH)
        self.ids = json.loads(config.EMBEDDINGS_META_PATH.read_text(encoding="utf-8"))["ids"]
        return True

    def build(self, save: bool = True) -> "EmbeddingIndex":
        texts = self.catalog.all_doc_texts()
        if self.backend == "local":
            vecs = self._embed_local(texts)
            # O modelo local define a própria dimensão (ex.: MiniLM=384); não forçamos 768.
            if vecs:
                self.dim = len(vecs[0])
        else:
            vecs = self.client.embed(texts, task_type="RETRIEVAL_DOCUMENT", dim=self.dim)
        self.matrix = _l2_normalize(np.asarray(vecs, dtype=np.float32))
        self.ids = self.catalog.ids
        if save:
            np.save(config.EMBEDDINGS_PATH, self.matrix)
            config.EMBEDDINGS_META_PATH.write_text(
                json.dumps(self._meta(), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return self

    def load_or_build(self) -> "EmbeddingIndex":
        if not self.load():
            self.build()
        return self

    # --- consulta ---
    def embed_query(self, query: str) -> np.ndarray:
        if self.backend == "local":
            vec = self._embed_local([query])[0]
        else:
            vec = self.client.embed([query], task_type="RETRIEVAL_QUERY", dim=self.dim)[0]
        v = np.asarray(vec, dtype=np.float32)
        n = np.linalg.norm(v)
        return v / n if n else v

    def cosine_scores(self, query_vec: np.ndarray, subset_idx: Optional[list[int]] = None) -> np.ndarray:
        """Cosseno entre a consulta e (um subconjunto de) os documentos. Como tudo
        está normalizado, é só o produto interno."""
        assert self.matrix is not None, "Índice não carregado/construído."
        mat = self.matrix if subset_idx is None else self.matrix[subset_idx]
        return mat @ query_vec

    # --- backend local opcional ---
    def _embed_local(self, texts: list[str]) -> list[list[float]]:
        if self._local_model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as e:
                raise RuntimeError(
                    "EMBEDDINGS_BACKEND=local exige sentence-transformers "
                    "(`pip install sentence-transformers`)."
                ) from e
            self._local_model = SentenceTransformer(config.LOCAL_EMBEDDING_MODEL)
        embs = self._local_model.encode(texts, normalize_embeddings=False)
        return [list(map(float, e)) for e in embs]
