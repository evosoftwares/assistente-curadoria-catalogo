"""Ferramentas DETERMINÍSTICAS.

Por que existir: LLMs erram aritmética, contagem e "garanta N itens diferentes". Então o que
é cálculo a gente calcula em Python e entrega o resultado PRONTO para o gerador só narrar
(via bloco "FATOS COMPUTADOS" do prompt). Isso é o que faz Q8 (mín/máx), Q6 (por categoria) e
Q2 (diversidade) ficarem corretos onde um RAG ingênuo erraria.
"""
from __future__ import annotations

from collections import OrderedDict


def aggregate_min_max(books: list[dict]) -> dict:
    """Ano mín/máx + TODOS os livros empatados em cada extremo (Q8).

    Por que devolver a lista de empatados, não um só: no catálogo o "mais recente" é um
    EMPATE de 13 livros de 2024. Cravar um único seria errado — a resposta correta sinaliza
    o empate. Por isso filtramos todos os que batem o extremo, em vez de pegar o primeiro."""
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
    """Agrupa por gênero PRIMÁRIO (primeiro da lista) para "liste por categoria" (Q6).

    Por que o primeiro gênero (e não todos): um livro tem vários gêneros; agrupar por todos
    o faria aparecer em várias categorias (contagem inflada). O primeiro é o gênero dominante.
    Ordenamos por ano desc para a lista de cada categoria sair do mais novo ao mais antigo."""
    groups: "OrderedDict[str, list[dict]]" = OrderedDict()
    for b in sorted(books, key=lambda x: x["ano_publicacao"], reverse=True):
        g = (b.get("generos") or ["(sem gênero)"])[0]
        groups.setdefault(g, []).append(b)
    return groups


def diversify(books: list[dict], field: str, n: int, max_per_value: int = 1) -> dict:
    """Seleção gananciosa: no máx ``max_per_value`` itens por valor distinto de ``field``, até ``n`` (Q2).

    Por que: "5 livros de FAIXAS ETÁRIAS DIFERENTES" é uma restrição de DIVERSIDADE que nem o
    top-k nem o prompt garantem (o top-k traria 5 da mesma faixa). Então forçamos um-por-faixa
    aqui, em código. Devolvemos também ``distinct_count`` para o pipeline ser HONESTO quando o
    dado não suporta o pedido (no catálogo só há 1 faixa infantil → vira 'acknowledge_limitation')."""
    seen: dict[str, int] = {}
    selected: list[dict] = []
    # 1ª passada: respeita a cota por valor, preservando a ordem de relevância recebida.
    for b in books:
        key = b.get(field, "")
        if seen.get(key, 0) < max_per_value:
            selected.append(b)
            seen[key] = seen.get(key, 0) + 1
        if len(selected) >= n:
            break
    # 2ª passada: se não atingimos n (poucas faixas distintas), completamos com o que sobrou —
    # melhor entregar n títulos do que menos; a honestidade sobre a falta de diversidade fica
    # por conta do distinct_count que devolvemos.
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
