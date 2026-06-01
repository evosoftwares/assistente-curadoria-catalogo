"""Roda as 10 perguntas do gold-set pelo pipeline e gera:
- eval/results_manual.json  (respostas + referências + debug, para o juiz e métricas)
- eval/results_manual.md    (tabela markdown para CLASSIFICAÇÃO MANUAL humana)

Roda em processo (não precisa do servidor no ar). Use após `build_index.py` para
obter o comportamento híbrido completo; sem chave, roda em modo BM25-only/degradado.

Uso:  python eval/run_manual.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.pipeline import AskPipeline  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent


def _load_existing_labels() -> dict[int, tuple[str, str, str]]:
    """Lê (rótulo, modo de falha, notas) já preenchidos em results_manual.md, por qid."""
    md = EVAL_DIR / "results_manual.md"
    out: dict[int, tuple[str, str, str]] = {}
    if not md.exists():
        return out
    for ln in md.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in ln.split("|")]
        # | Q | Tipo | Esperado | Observado | Refs | Rótulo | Modo | Notas |  -> 10 partes
        if len(cells) >= 9 and cells[1].isdigit() and cells[6] in {"CORRETA", "PARCIAL", "ERRADA"}:
            out[int(cells[1])] = (cells[6], cells[7], cells[8])
    return out


def main() -> int:
    gold = json.loads((EVAL_DIR / "gold.json").read_text(encoding="utf-8"))
    pipe = AskPipeline()
    rows = []
    for item in gold:
        resp = pipe.ask(item["question"])
        d = resp.retrieval_debug
        rows.append({
            "qid": item["qid"],
            "question": item["question"],
            "type": item["type"],
            "expected_behavior": item["expected_behavior"],
            "behavior_observed": d.behavior.value,
            "answer": resp.answer,
            "references": [r.id for r in resp.references],
            "retrieved_ids": d.retrieved_ids,
            "context_ids": d.context_ids,
            "candidate_count": d.candidate_count,
            "top_cosine": d.top_cosine,
            "cost_usd": d.estimated_cost_usd,
            "latency_ms": d.latency_ms,
            "notes": d.notes,
        })

    (EVAL_DIR / "results_manual.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # PRESERVA rótulos manuais já preenchidos (CORRETA/PARCIAL/ERRADA + modo + notas) —
    # assim re-rodar este script não destrói a classificação humana / o κ do juiz.
    existing = _load_existing_labels()

    # Tabela markdown para rótulo humano (em branco só se ainda não houver rótulo).
    lines = [
        "# Resultados — classificação manual",
        "",
        f"Modo: {'híbrido' if pipe.index.matrix is not None else 'BM25-only'} | "
        f"LLM: {'on' if pipe.client.available else 'degradado (sem chave)'}",
        "",
        "| Q | Tipo | Esperado | Observado | Refs | Rótulo manual | Modo de falha | Notas |",
        "|---|------|----------|-----------|------|---------------|---------------|-------|",
    ]
    for r in rows:
        refs = ",".join(r["references"]) or "—"
        match = "✅" if r["behavior_observed"] == r["expected_behavior"] else "⚠️"
        label, modo, notas = existing.get(r["qid"], ("_(preencher)_", "_(preencher)_", ""))
        lines.append(
            f"| {r['qid']} | {r['type']} | {r['expected_behavior']} | "
            f"{match}{r['behavior_observed']} | {refs} | {label} | {modo} | {notas} |"
        )
    lines += [
        "",
        "## Respostas completas",
        "",
    ]
    for r in rows:
        lines.append(f"### Q{r['qid']} — {r['question']}")
        lines.append(f"- **Comportamento:** esperado=`{r['expected_behavior']}` / observado=`{r['behavior_observed']}`")
        lines.append(f"- **Referências:** {', '.join(r['references']) or '—'}")
        lines.append(f"- **Top-k recuperado:** {', '.join(r['retrieved_ids']) or '—'}")
        lines.append(f"- **Custo:** US${r['cost_usd']} | **Latência:** {r['latency_ms'].get('total_ms','?')} ms")
        lines.append(f"\n> {r['answer']}\n")

    (EVAL_DIR / "results_manual.md").write_text("\n".join(lines), encoding="utf-8")
    total_cost = sum(r["cost_usd"] for r in rows)
    print(f"OK: {len(rows)} perguntas. Custo total ~US${total_cost:.5f}.")
    print(f"  -> {EVAL_DIR/'results_manual.json'}")
    print(f"  -> {EVAL_DIR/'results_manual.md'} (preencha os rótulos manuais)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
