"""Consumidor do FEEDBACK → gold-set VIVO (fecha o loop do roadmap v2).

O coletor (POST /feedback + tool MCP) acumula votos 👍/👎 reais em data/feedback.jsonl.
Este script os AGREGA num gold-set vivo, complementar ao gold.json estático (10 perguntas
curadas à mão). É o passo que o ROADMAP marcava como "resta o consumidor".

Princípio (herdado do build_gold.py): rótulos NÃO vêm do planner de produção — vêm do
HUMANO. Aqui:
- 👍 numa resposta = sinal POSITIVO fraco: os livros mostrados (reference_ids) foram aceitos
  como bons -> viram candidatos a "relevantes" (grade 2).
- 👎 (com comentário) = o dado mais valioso: vai para uma FILA DE REVISÃO com o motivo.
- Várias ocorrências da mesma pergunta -> agregadas (taxa de aceitação por pergunta).

Saída: eval/gold_live.json — schema COMPATÍVEL com gold.json (qid, question, expected_behavior,
relevant_ids:[{id,grade}]) para que, maduro, possa alimentar retrieval_metrics.py diretamente.
100% determinístico (sem LLM/rede), testável. Uso:  python eval/build_gold_from_feedback.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: E402
from app.catalog import normalize  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
# Abaixo deste nº de votos por pergunta, a métrica é ruidosa demais p/ confiar — sinalizamos.
MIN_VOTOS_CONFIAVEL = 5


def _load_feedback() -> list[dict]:
    """Lê o JSONL de feedback defensivamente (linha corrompida é pulada; ausência = vazio)."""
    p = config.FEEDBACK_PATH
    if not p.exists():
        return []
    out = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def aggregate(events: list[dict]) -> dict:
    """Agrega eventos de feedback por pergunta (normalizada). Função PURA (testável):
    não lê disco nem imprime. Devolve {questions:[...], summary:{...}, review_queue:[...]}."""
    # Agrupa por pergunta normalizada (mesma pergunta com grafia/caixa diferente = 1 grupo).
    grupos: dict[str, list[dict]] = {}
    for e in events:
        q = (e.get("question") or "").strip()
        if not q:
            continue
        grupos.setdefault(normalize(q), []).append(e)

    questions, review_queue = [], []
    total_up = total_down = 0
    for nq, evs in sorted(grupos.items()):
        ups = [e for e in evs if e.get("verdict") == "up"]
        downs = [e for e in evs if e.get("verdict") == "down"]
        total_up += len(ups)
        total_down += len(downs)
        # candidatos a relevantes = união dos ids referenciados nos votos POSITIVOS
        rel_ids = []
        for e in ups:
            for rid in (e.get("reference_ids") or []):
                if rid not in rel_ids:
                    rel_ids.append(rid)
        # comportamento esperado = o mais frequente observado (sinal de qual ramo a pergunta exercita)
        beh = Counter(e.get("behavior") for e in evs if e.get("behavior")).most_common(1)
        n = len(ups) + len(downs)
        # pergunta "canônica" do grupo = a forma mais recente votada (preserva acentuação real)
        canonica = sorted(evs, key=lambda e: e.get("ts", 0))[-1].get("question", "").strip()
        questions.append({
            "qid": "live-" + hashlib.sha256(nq.encode("utf-8")).hexdigest()[:8],
            "question": canonica,
            "expected_behavior": beh[0][0] if beh else "answer",
            "relevant_ids": [{"id": i, "grade": 2} for i in rel_ids],   # 👍 = positivo forte
            "provenance": "feedback",                                   # NÃO é do planner (anti-circular)
            "n_up": len(ups), "n_down": len(downs),
            "acceptance": round(len(ups) / n, 3) if n else None,
            "confiavel": n >= MIN_VOTOS_CONFIAVEL,
            "review_comments": [e["comment"] for e in downs if e.get("comment")],
        })
        for e in downs:
            if e.get("comment"):
                review_queue.append({"question": e.get("question"), "comment": e["comment"],
                                     "behavior": e.get("behavior")})

    n_tot = total_up + total_down
    summary = {
        "eventos": len(events),
        "perguntas_distintas": len(questions),
        "votos_uteis": total_up,
        "votos_negativos": total_down,
        "aceitacao_global_pct": round(100 * total_up / n_tot, 1) if n_tot else None,
        "perguntas_confiaveis": sum(1 for q in questions if q["confiavel"]),
        "fila_de_revisao": len(review_queue),
        "min_votos_p_confiavel": MIN_VOTOS_CONFIAVEL,
    }
    return {"summary": summary, "questions": questions, "review_queue": review_queue}


def main() -> int:
    events = _load_feedback()
    result = aggregate(events)
    out = EVAL_DIR / "gold_live.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    s = result["summary"]
    print("== Gold-set vivo (a partir do feedback humano) ==")
    if not events:
        print("  Nenhum feedback ainda. Vote 👍/👎 na UI (ou via tool MCP) e rode de novo.")
        print(f"  -> {out} (vazio, mas válido)")
        return 0
    print(f"  eventos: {s['eventos']} | perguntas distintas: {s['perguntas_distintas']}")
    print(f"  aceitação global: {s['aceitacao_global_pct']}% ({s['votos_uteis']}👍 / {s['votos_negativos']}👎)")
    print(f"  perguntas com ≥{s['min_votos_p_confiavel']} votos (confiáveis): {s['perguntas_confiaveis']}")
    print(f"  fila de revisão (👎 com comentário): {s['fila_de_revisao']}")
    if s["perguntas_distintas"] and not s["perguntas_confiaveis"]:
        print("  NOTA: volume baixo — métricas por pergunta ainda ruidosas; use só como tendência.")
    print(f"  -> {out}  (schema compatível com gold.json; maduro, alimenta retrieval_metrics.py)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
