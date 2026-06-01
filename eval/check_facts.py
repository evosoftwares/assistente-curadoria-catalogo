"""Asserções determinísticas: fecha o circuito entre o gold COMPUTADO e o que o
sistema de fato calcula. Diferente do juiz (cego ao catálogo) e das métricas de
recuperação (que excluem agregação), aqui comparamos programaticamente:

- Q4: o filtro gênero=Didático + público=ensino médio == relevant_ids do gold.
- Q6: o conjunto ano>=ano_min == relevant_ids do gold.
- Q8: tools.aggregate_min_max(catálogo INTEIRO) == expected_value (oldest/newest/anos).

Roda SEM chave (puro determinístico). Sai com código !=0 se algo divergir — serve
como teste de regressão da verdade determinística.

Uso:  python eval/check_facts.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import tools  # noqa: E402
from app.catalog import get_catalog  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent


def main() -> int:
    cat = get_catalog()
    gold = {g["qid"]: g for g in json.loads((EVAL_DIR / "gold.json").read_text(encoding="utf-8"))}
    books = cat.books
    fails = []

    def check(name, got, exp):
        ok = sorted(got) == sorted(exp)
        print(f"  [{'OK' if ok else 'FALHA'}] {name}: got={sorted(got)} exp={sorted(exp)}" if not ok
              else f"  [OK] {name} ({len(exp)} itens)")
        if not ok:
            fails.append(name)

    print("== Asserções determinísticas (verdade computada vs gold) ==")

    # Q4 — filtro categórico
    q4_exp = [r["id"] for r in gold[4]["relevant_ids"]]
    q4_got = [b["id"] for b in books if "Didático" in b["generos"] and "ensino médio" in b["publico_alvo"]]
    check("Q4 didáticos ensino médio", q4_got, q4_exp)

    # Q6 — filtro de ano relativo
    ano_min = gold[6]["expected_value"]["ano_min"]
    q6_exp = [r["id"] for r in gold[6]["relevant_ids"]]
    q6_got = [b["id"] for b in books if b["ano_publicacao"] >= ano_min]
    check(f"Q6 ano>={ano_min}", q6_got, q6_exp)

    # Q8 — agregação min/max sobre o catálogo inteiro
    agg = tools.aggregate_min_max(books)
    ev = gold[8]["expected_value"]
    print(f"  Q8 min_year computado={agg['min_year']} (gold={ev['min_year']}) | "
          f"max_year computado={agg['max_year']} (gold={ev['max_year']})")
    if agg["min_year"] != ev["min_year"] or agg["max_year"] != ev["max_year"]:
        fails.append("Q8 anos")
    check("Q8 oldest_ids", [b["id"] for b in agg["oldest"]], ev["oldest_ids"])
    check("Q8 newest_ids (empate)", [b["id"] for b in agg["newest"]], ev["newest_ids"])

    print()
    if fails:
        print(f"FALHOU: {fails}")
        return 1
    print("TODAS as asserções determinísticas passaram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
