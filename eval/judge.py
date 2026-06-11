"""LLM-as-judge (bônus). Avalia as respostas de results_manual.json.

Controles anti-carimbo (recomendados pelo red-team):
1. O juiz exige CITAÇÃO VERBATIM do contexto ou marca "UNSUPPORTED".
2. Escala ANCORADA 0-3 (não 1-5 vago).
3. O juiz vê SOMENTE o contexto recuperado + a resposta (cego ao catálogo completo).
4. CONJUNTO DE CALIBRAÇÃO: 4 respostas propositalmente ruins; se o juiz não reprovar
   ≥3 delas, seus resultados são marcados como NÃO-CONFIÁVEIS.
5. Reporta concordância (Cohen's κ) entre o veredito do juiz e o rótulo manual humano,
   quando este existir em results_manual.md.

Requer uma chave de LLM (OPENROUTER_API_KEY ou GEMINI_API_KEY).  Uso:  python eval/judge.py
Com OpenRouter ativo, o juiz roda em OUTRA família de modelo (OPENROUTER_JUDGE_MODEL,
padrão anthropic/claude-haiku-4.5) — reduz o viés de "Gemini avaliando Gemini".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.catalog import get_catalog  # noqa: E402
from app.llm import get_client  # noqa: E402
from app.prompts import JUDGE_SYSTEM, build_judge_prompt  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent


def judge_one(client, cat, question, expected_behavior, context_ids, answer, cited_ids) -> dict:
    ctx_books = [cat.get(i) for i in context_ids if cat.get(i)]
    prompt = build_judge_prompt(question, expected_behavior, ctx_books, answer, cited_ids)
    # judge_model do backend ativo: roteado via OpenRouter, o juiz roda por padrão em OUTRA
    # família de modelo (anthropic/claude-haiku-4.5) — mitiga o viés de auto-avaliação.
    text, _ = client.generate_text(JUDGE_SYSTEM, prompt, model=client.judge_model, as_json=True)
    try:
        return json.loads(text)
    except Exception:
        return {"veredito": "ERRADA", "groundedness": 0, "parse_error": True, "raw": text[:300]}


def calibration_set(cat) -> list[dict]:
    """Respostas deliberadamente ruins; o juiz DEVE reprovar (veredito != CORRETA)."""
    some = cat.books[0]
    return [
        {"name": "alucinação de título",
         "question": "Temos algum livro sobre liderança?",
         "expected_behavior": "answer",
         "context_ids": [some["id"]],
         "answer": 'Sim, recomendo "O Príncipe" de Maquiavel (BK9999), um clássico sobre liderança.',
         "cited_ids": ["BK9999"]},
        {"name": "citação de id não recuperado",
         "question": "O que temos sobre o cérebro?",
         "expected_behavior": "answer",
         "context_ids": [some["id"]],
         "answer": f"Temos ótimas opções (BK0099, BK0178).",
         "cited_ids": ["BK0099", "BK0178"]},
        {"name": "falha em abster (Q10)",
         "question": 'Vocês têm "Dom Casmurro" de Machado de Assis?',
         "expected_behavior": "abstain",
         "context_ids": [some["id"]],
         "answer": 'Sim! Temos "Dom Casmurro" na 3ª edição, ISBN 9788599999999.',
         "cited_ids": []},
        {"name": "resposta irrelevante",
         "question": "Qual o livro mais antigo do catálogo?",
         "expected_behavior": "answer",
         "context_ids": [some["id"]],
         "answer": "Recomendo experimentar a culinária brasileira contemporânea!",
         "cited_ids": []},
    ]


def _faithfulness(verdict: dict) -> float | None:
    """FAITHFULNESS estilo RAGAS: fração das afirmações da resposta que têm uma CITAÇÃO de
    suporte no contexto (vs. 'UNSUPPORTED'). O juiz já decompõe a resposta em per_claim e
    extrai a citação verbatim ou marca UNSUPPORTED — então isto é uma verificação de
    *entailment por claim* (suporte da evidência), sem dependência pesada.
    Retorna None quando não há afirmações factuais (ex.: abstenção pura), p/ não distorcer a macro.
    (Alternativa offline mais robusta: um cross-encoder NLI multilíngue — ver README/RESULTS.)"""
    claims = verdict.get("per_claim") or []
    if not claims:
        return None
    supported = sum(1 for c in claims
                    if isinstance(c, dict) and str(c.get("supporting_quote", "")).strip().upper() != "UNSUPPORTED"
                    and str(c.get("supporting_quote", "")).strip())
    return round(supported / len(claims), 3)


def cohen_kappa(a: list[str], b: list[str]) -> float | None:
    labels = sorted(set(a) | set(b))
    if len(a) < 2 or len(labels) < 2:
        return None
    n = len(a)
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    pe = sum((a.count(l) / n) * (b.count(l) / n) for l in labels)
    return round((po - pe) / (1 - pe), 3) if pe != 1 else None


def parse_manual_labels() -> dict[int, str]:
    """Lê rótulos manuais de results_manual.md, se preenchidos (CORRETA/PARCIAL/ERRADA)."""
    md = EVAL_DIR / "results_manual.md"
    out: dict[int, str] = {}
    if not md.exists():
        return out
    import re
    for ln in md.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*(\d+)\s*\|.*\|\s*(CORRETA|PARCIAL|ERRADA)\s*\|", ln)
        if m:
            out[int(m.group(1))] = m.group(2)
    return out


def main() -> int:
    client = get_client()
    if not client.available:
        print("ERRO: judge.py requer uma chave de LLM (OPENROUTER_API_KEY ou GEMINI_API_KEY).")
        return 1
    cat = get_catalog()

    # 1) Calibração
    print("== Calibração do juiz (deve reprovar respostas ruins) ==")
    cal = calibration_set(cat)
    caught = 0
    for c in cal:
        v = judge_one(client, cat, c["question"], c["expected_behavior"],
                      c["context_ids"], c["answer"], c["cited_ids"])
        ver = v.get("veredito", "?")
        ok = ver != "CORRETA"
        caught += ok
        print(f"  [{'OK' if ok else 'FALHOU'}] {c['name']}: veredito={ver}")
    trustworthy = caught >= 3
    print(f"  -> juiz {'CONFIÁVEL' if trustworthy else 'NÃO-CONFIÁVEL'} ({caught}/4 reprovadas)\n")

    # 2) Avaliação das 10
    results_path = EVAL_DIR / "results_manual.json"
    if not results_path.exists():
        print("Rode primeiro: python eval/run_manual.py")
        return 1
    rows = json.loads(results_path.read_text(encoding="utf-8"))
    judged = []
    print("== Veredito do juiz por pergunta ==")
    for r in rows:
        v = judge_one(client, cat, r["question"], r["expected_behavior"],
                      r.get("context_ids") or r["retrieved_ids"], r["answer"], r["references"])
        v["qid"] = r["qid"]
        # Faithfulness não se aplica à ABSTENÇÃO ("não consta" não é afirmação factual a ancorar):
        # excluímos esses itens (None) para não distorcer a macro.
        v["faithfulness"] = None if r["expected_behavior"] == "abstain" else _faithfulness(v)
        judged.append(v)
        fth = v["faithfulness"]
        print(f"  Q{r['qid']}: {v.get('veredito','?')} | grounded={v.get('groundedness','?')} "
              f"cite={v.get('citation_faithfulness','?')} rel={v.get('answer_relevance','?')} "
              f"behavior={v.get('behavior_match','?')} | faithfulness={fth if fth is not None else '—'}")
    # Macro de faithfulness (ignora itens sem afirmações factuais, ex.: abstenção pura).
    fvals = [v["faithfulness"] for v in judged if v["faithfulness"] is not None]
    macro_faith = round(sum(fvals) / len(fvals), 3) if fvals else None
    print(f"\nFaithfulness macro (claims com suporte / total): {macro_faith if macro_faith is not None else '—'}")

    # 3) Concordância com rótulo manual humano
    manual = parse_manual_labels()
    kappa = None
    if manual:
        pairs = [(manual[v["qid"]], v.get("veredito", "ERRADA")) for v in judged if v["qid"] in manual]
        if pairs:
            kappa = cohen_kappa([p[0] for p in pairs], [p[1] for p in pairs])
    print(f"\nCohen's κ (juiz vs humano): {kappa if kappa is not None else 'sem rótulos manuais ainda'}")

    out = {"trustworthy": trustworthy, "calibration_caught": caught, "kappa": kappa,
           "faithfulness_macro": macro_faith, "verdicts": judged}
    (EVAL_DIR / "results_judge.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"-> {EVAL_DIR/'results_judge.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
