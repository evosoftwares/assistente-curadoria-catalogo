"""Métricas de RECUPERAÇÃO (decopladas da geração): recall@k, precision@k, MRR, nDCG@k.

- Avalia diretamente o planner+retriever (top_k grande), independente do gerador.
- Deduplica por CLUSTER de edição (app/catalog.cluster_of) para que edições duplicadas
  não distorçam precisão/recall.
- Relevância graduada: grade>=1 conta como relevante (binário); nDCG usa as notas.
- Exclui perguntas de agregação (Q8) e fora-do-catálogo (Q10): não são problemas de
  recuperação.

Uso:  python eval/retrieval_metrics.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: E402
from app.catalog import get_catalog  # noqa: E402
from app.embeddings import EmbeddingIndex  # noqa: E402
from app.llm import get_client  # noqa: E402
from app.planner import Planner  # noqa: E402
from app.retriever import HybridRetriever  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
KS = [5, 8, 20]
SKIP_TYPES = {"aggregation", "out_of_catalog"}


def ranked_clusters(ids: list[str], cluster_of) -> list[str]:
    """Ordena clusters por primeira aparição (dedup mantendo a melhor posição)."""
    seen, out = set(), []
    for i in ids:
        c = cluster_of(i)
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def main() -> int:
    cat = get_catalog()
    client = get_client()
    index = EmbeddingIndex(cat, client)
    semantic = index.load()
    if not semantic and (client.available or config.EMBEDDINGS_BACKEND == "local"):
        index.build(); semantic = True
    retr = HybridRetriever(cat, index)
    planner = Planner(cat, client)

    gold = json.loads((EVAL_DIR / "gold.json").read_text(encoding="utf-8"))
    per_q = []
    for item in gold:
        if item["type"] in SKIP_TYPES:
            continue
        # cluster de relevância (grade>=1) e nota por cluster (máx das notas)
        rel_grade: dict[str, int] = {}
        for r in item["relevant_ids"]:
            if r["grade"] >= 1:
                c = cat.cluster_of(r["id"])
                rel_grade[c] = max(rel_grade.get(c, 0), r["grade"])
        rel_clusters = set(rel_grade)
        if not rel_clusters:
            continue

        plan, _ = planner.plan(item["question"])
        qvecs = None
        if semantic:
            try:
                qvecs = [index.embed_query(q) for q in plan.semantic_queries] or None
            except Exception:
                qvecs = None
        results, _ = retr.retrieve(plan, qvecs, top_k=50)
        ranked = ranked_clusters([r.book["id"] for r in results], cat.cluster_of)

        row = {"qid": item["qid"], "type": item["type"], "n_rel": len(rel_clusters)}
        # MRR
        rr = 0.0
        for rank, c in enumerate(ranked, 1):
            if c in rel_clusters:
                rr = 1.0 / rank
                break
        row["mrr"] = round(rr, 3)
        for k in KS:
            topk = ranked[:k]
            hits = sum(1 for c in topk if c in rel_clusters)
            row[f"recall@{k}"] = round(hits / len(rel_clusters), 3)
            row[f"prec@{k}"] = round(hits / k, 3)
        # nDCG@8 (graded)
        k = 8
        dcg = sum((rel_grade.get(c, 0)) / math.log2(rank + 1) for rank, c in enumerate(ranked[:k], 1))
        ideal = sorted(rel_grade.values(), reverse=True)[:k]
        idcg = sum(g / math.log2(rank + 1) for rank, g in enumerate(ideal, 1))
        row["ndcg@8"] = round(dcg / idcg, 3) if idcg else 0.0
        per_q.append(row)

    # macro-média
    keys = ["mrr", "ndcg@8"] + [f"recall@{k}" for k in KS] + [f"prec@{k}" for k in KS]
    macro = {key: round(sum(r[key] for r in per_q) / len(per_q), 3) for key in keys} if per_q else {}

    mode = "híbrido (semântico+BM25)" if semantic else "BM25-only (sem embeddings/chave)"
    print(f"== Métricas de recuperação — modo: {mode} ==\n")
    hdr = ["Q", "tipo", "n_rel"] + keys
    print("| " + " | ".join(hdr) + " |")
    print("|" + "|".join("---" for _ in hdr) + "|")
    for r in per_q:
        vals = [str(r["qid"]), r["type"], str(r["n_rel"])] + [str(r[k]) for k in keys]
        print("| " + " | ".join(vals) + " |")
    if macro:
        print("| **macro** | — | — | " + " | ".join(str(macro[k]) for k in keys) + " |")

    out = {"mode": mode, "per_question": per_q, "macro": macro}
    (EVAL_DIR / "results_retrieval.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n-> {EVAL_DIR/'results_retrieval.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
