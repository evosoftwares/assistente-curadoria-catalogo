"""Testes do consumidor de feedback -> gold-set vivo (eval/build_gold_from_feedback.py).

Travam a agregação por pergunta: união de ids relevantes a partir dos 👍, taxa de aceitação,
fila de revisão dos 👎 com comentário, e o gating de confiabilidade por volume. Determinístico.
Rode com:  python -m pytest -q
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "build_gold_from_feedback", ROOT / "eval" / "build_gold_from_feedback.py")
bgff = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bgff)


def _ev(q, verdict, refs=None, comment=None, behavior="answer", ts=0.0):
    return {"question": q, "verdict": verdict, "reference_ids": refs or [],
            "comment": comment, "behavior": behavior, "ts": ts}


def test_vazio_e_valido():
    r = bgff.aggregate([])
    assert r["questions"] == [] and r["summary"]["eventos"] == 0
    assert r["summary"]["aceitacao_global_pct"] is None


def test_agrega_mesma_pergunta_e_une_ids_dos_ups():
    eventos = [
        _ev("Quais livros sobre IA?", "up", refs=["BK0040", "BK0069"], ts=1),
        _ev("quais livros sobre ia?", "up", refs=["BK0069", "BK0017"], ts=2),  # grafia difere -> mesmo grupo
        _ev("Quais livros sobre IA?", "down", comment="faltou o público-alvo", ts=3),
    ]
    r = bgff.aggregate(eventos)
    assert len(r["questions"]) == 1                     # normalização agrupa as 3
    q = r["questions"][0]
    assert q["n_up"] == 2 and q["n_down"] == 1
    assert q["acceptance"] == round(2 / 3, 3)
    ids = {x["id"] for x in q["relevant_ids"]}
    assert ids == {"BK0040", "BK0069", "BK0017"}        # união dos ids dos 👍
    assert all(x["grade"] == 2 for x in q["relevant_ids"])
    assert q["provenance"] == "feedback"                # anti-circular: veio do humano, não do planner
    assert q["question"] == "Quais livros sobre IA?"    # canônica = a mais recente (ts maior entre as iguais)


def test_fila_de_revisao_captura_comentarios_dos_downs():
    r = bgff.aggregate([
        _ev("X?", "down", comment="resposta genérica demais"),
        _ev("Y?", "down"),  # sem comentário -> não entra na fila
    ])
    assert r["summary"]["fila_de_revisao"] == 1
    assert r["review_queue"][0]["comment"] == "resposta genérica demais"


def test_gating_de_confiabilidade_por_volume():
    poucos = [_ev("Z?", "up", ts=i) for i in range(3)]            # 3 < MIN
    assert bgff.aggregate(poucos)["questions"][0]["confiavel"] is False
    muitos = [_ev("Z?", "up", ts=i) for i in range(bgff.MIN_VOTOS_CONFIAVEL)]
    assert bgff.aggregate(muitos)["questions"][0]["confiavel"] is True


def test_aceitacao_global():
    r = bgff.aggregate([_ev("A?", "up"), _ev("B?", "up"), _ev("C?", "down")])
    assert r["summary"]["aceitacao_global_pct"] == round(100 * 2 / 3, 1)
