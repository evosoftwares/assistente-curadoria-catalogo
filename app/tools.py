"""Ferramentas determinísticas. Nunca confiamos no LLM para aritmética/agregação
ou para garantir diversidade: computamos em Python e passamos o resultado pronto
para o gerador apenas narrar.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Optional


def aggregate_min_max(books: list[dict]) -> dict:
    """Retorna ano mín/máx e os livros empatados em cada extremo.
    (No catálogo, 'mais recente' é um empate de vários livros de 2024.)"""
    if not books:
        return {}
    anos = [b["ano_publicacao"] for b in books]
    ymin, ymax = min(anos), max(anos)
    return {
        "min_year": ymin,
        "max_year": ymax,
        "oldest": [b for b in books if b["ano_publicacao"] == ymin],
        "newest": [b for b in books if b["ano_publicacao"] == ymax],
    }


def group_by_genero(books: list[dict]) -> "OrderedDict[str, list[dict]]":
    """Agrupa por gênero PRIMÁRIO (primeiro da lista), preservando ordem de aparição."""
    groups: "OrderedDict[str, list[dict]]" = OrderedDict()
    for b in sorted(books, key=lambda x: x["ano_publicacao"], reverse=True):
        g = (b.get("generos") or ["(sem gênero)"])[0]
        groups.setdefault(g, []).append(b)
    return groups


def diversify(books: list[dict], field: str, n: int, max_per_value: int = 1) -> dict:
    """Seleção gananciosa preservando a ordem de ranqueamento: no máximo
    ``max_per_value`` itens por valor distinto do campo, até ``n`` itens.
    Retorna a seleção e as faixas distintas encontradas (para honestidade sobre limitações)."""
    seen: dict[str, int] = {}
    selected: list[dict] = []
    for b in books:
        key = b.get(field, "")
        if seen.get(key, 0) < max_per_value:
            selected.append(b)
            seen[key] = seen.get(key, 0) + 1
        if len(selected) >= n:
            break
    # Se ainda faltam itens e há livros sobrando, completa ignorando a restrição.
    if len(selected) < n:
        for b in books:
            if b not in selected:
                selected.append(b)
            if len(selected) >= n:
                break
    return {
        "selected": selected[:n],
        "distinct_values": list(seen.keys()),
        "distinct_count": len(seen),
    }
