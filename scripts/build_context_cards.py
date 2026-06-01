"""Contextual Retrieval (adaptado a docs curtos): gera offline um "cartão de contexto"
por livro — 1-2 frases densas com temas, tom, subgênero e "indicado para quem gosta de…".

Por que: o catálogo é templado (87 sinopses p/ 200 livros) e pobre em texto livre. Os
cartões enriquecem o texto indexado (BM25 + embeddings), melhorando recall sem mexer no
runtime. Saída: data/context_cards.json {id: cartão}. Versione esse arquivo.

Gera em LOTES (structured output) para economizar chamadas. Requer GEMINI_API_KEY.
Uso:  python scripts/build_context_cards.py [--force]   (depois rode build_index.py --force)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pydantic import BaseModel  # noqa: E402

from app import config  # noqa: E402
from app.catalog import get_catalog  # noqa: E402
from app.llm import get_client  # noqa: E402

BATCH = 10

SYSTEM = """Você escreve "cartões de contexto" curtos para indexar livros num sistema de busca.
Para CADA livro, escreva 1-2 frases densas (máx ~35 palavras) cobrindo: temas centrais, tom/estilo,
subgênero e "indicado para quem gosta de…". Use SOMENTE título, sinopse, gêneros e público fornecidos;
NÃO invente fatos específicos (prêmios, enredo detalhado, personagens). Português. Devolva o JSON do schema."""


class Card(BaseModel):
    id: str
    card: str


class CardBatch(BaseModel):
    cards: list[Card]


def _book_line(b: dict) -> str:
    return (f'id={b["id"]} | título="{b["titulo"]}" | gêneros={b.get("generos")} | '
            f'público="{b.get("publico_alvo","")}" | sinopse="{b.get("sinopse","")}"')


def main() -> int:
    force = "--force" in sys.argv
    client = get_client()
    if not client.available:
        print("ERRO: build_context_cards requer GEMINI_API_KEY.")
        return 1
    cat = get_catalog()
    existing: dict[str, str] = {}
    if config.CONTEXT_CARDS_PATH.exists() and not force:
        existing = json.loads(config.CONTEXT_CARDS_PATH.read_text(encoding="utf-8"))

    todo = [b for b in cat.books if b["id"] not in existing]
    if not todo:
        print(f"Todos os {len(cat.books)} cartões já existem. Use --force para regenerar.")
        return 0

    cards = dict(existing)
    total_in = total_out = 0
    for start in range(0, len(todo), BATCH):
        chunk = todo[start:start + BATCH]
        user = "Livros:\n" + "\n".join(_book_line(b) for b in chunk)
        data, usage = client.generate_structured(SYSTEM, user, CardBatch, model=config.GEMINI_MODEL)
        total_in += usage.input_tokens; total_out += usage.output_tokens
        for item in data.get("cards", []):
            if item.get("id") and item.get("card"):
                cards[item["id"]] = item["card"].strip()
        print(f"  lote {start//BATCH+1}: +{len(chunk)} livros (total {len(cards)}/{len(cat.books)})")

    config.CONTEXT_CARDS_PATH.write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding="utf-8")
    from app.llm import Usage
    cost = Usage(config.GEMINI_MODEL, total_in, total_out).cost_usd
    missing = [b["id"] for b in cat.books if b["id"] not in cards]
    print(f"OK: {len(cards)} cartões -> {config.CONTEXT_CARDS_PATH.name} | tokens {total_in}/{total_out} "
          f"~US${cost:.4f}" + (f" | FALTARAM: {missing}" if missing else ""))
    print("Agora rode: python scripts/build_index.py --force  (re-embeddar com os cartões)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
