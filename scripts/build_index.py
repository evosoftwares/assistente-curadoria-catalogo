"""Constrói (e cacheia) o índice de embeddings do catálogo.

Uso:
    python scripts/build_index.py [--force]

Requer GEMINI_API_KEY (backend gemini) OU sentence-transformers (backend local).
O cache vai para data/embeddings.npy + data/embeddings_meta.json e é commitado,
para que a recuperação rode offline sem re-embeddar.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.catalog import get_catalog  # noqa: E402
from app.embeddings import EmbeddingIndex  # noqa: E402
from app.llm import Usage, get_client  # noqa: E402


def main() -> int:
    force = "--force" in sys.argv
    catalog = get_catalog()
    client = get_client()
    backend = config.EMBEDDINGS_BACKEND

    if backend != "local" and not client.available:
        print("ERRO: GEMINI_API_KEY ausente e EMBEDDINGS_BACKEND != local.")
        print("Defina a chave no .env ou use EMBEDDINGS_BACKEND=local (sentence-transformers).")
        return 1

    index = EmbeddingIndex(catalog, client)
    if not force and index.load():
        print(f"Cache válido encontrado ({index.matrix.shape}). Use --force para reconstruir.")
        return 0

    print(f"Construindo embeddings: backend={backend}, "
          f"modelo={config.LOCAL_EMBEDDING_MODEL if backend=='local' else config.GEMINI_EMBEDDING_MODEL}, "
          f"dim={config.EMBEDDING_DIM}, {len(catalog)} livros...")
    t0 = time.perf_counter()
    index.build(save=True)
    dt = time.perf_counter() - t0

    # Estimativa de custo de indexação (apenas backend gemini).
    if backend != "local":
        total_chars = sum(len(t) for t in catalog.all_doc_texts())
        approx_tokens = total_chars // 4  # ~4 chars/token
        cost = Usage(model=config.GEMINI_EMBEDDING_MODEL, input_tokens=approx_tokens).cost_usd
        print(f"~{approx_tokens} tokens embeddados | custo estimado de indexação: US${cost:.6f}")

    print(f"OK em {dt:.1f}s -> {config.EMBEDDINGS_PATH.name} {index.matrix.shape} "
          f"(+ {config.EMBEDDINGS_META_PATH.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
