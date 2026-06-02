"""Gate de regressão (CI) — barra mudanças que quebrem o sistema. Roda SEM chave (determinístico):

  1) pytest            — 24 testes (núcleo determinístico + camada de segurança)
  2) eval/check_facts  — verdade determinística do gold (Q4/Q6/Q8) bate com o sistema
  3) retrieval_metrics — macro recall@8 não pode cair abaixo de um piso (CI_MIN_RECALL8)

Sai com código != 0 se QUALQUER etapa falhar — é o que um job de CI (GitHub Actions) executa.
Uso:  python scripts/ci_gate.py     (piso ajustável: CI_MIN_RECALL8, default 0,70 = BM25-only)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
MIN_RECALL8 = float(os.getenv("CI_MIN_RECALL8", "0.70"))  # piso keyless (BM25-only ~0,77; híbrido ~0,89)


def _run(label: str, args: list[str]) -> bool:
    print(f"\n=== {label} ===")
    rc = subprocess.run([PY, *args], cwd=ROOT).returncode
    ok = rc == 0
    print(f"-> {label}: {'OK' if ok else 'FALHOU (rc=' + str(rc) + ')'}")
    return ok


def main() -> int:
    fails: list[str] = []

    if not _run("pytest", ["-m", "pytest", "-q"]):
        fails.append("pytest")
    if not _run("check_facts", ["eval/check_facts.py"]):
        fails.append("check_facts")

    # Métricas de recuperação + piso de recall@8 (não deixa o RAG regredir silenciosamente).
    if not _run("retrieval_metrics", ["eval/retrieval_metrics.py"]):
        fails.append("retrieval_metrics(run)")
    else:
        data = json.loads((ROOT / "eval" / "results_retrieval.json").read_text(encoding="utf-8"))
        r8 = data.get("macro", {}).get("recall@8", 0.0)
        print(f"  macro recall@8 = {r8} (piso = {MIN_RECALL8}) | modo: {data.get('mode')}")
        if r8 < MIN_RECALL8:
            fails.append(f"recall@8 {r8} < piso {MIN_RECALL8}")

    print("\n" + "=" * 50)
    if fails:
        print(f"GATE DE CI: FALHOU -> {fails}")
        return 1
    print("GATE DE CI: PASSOU (pytest + check_facts + recall@8 acima do piso)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
