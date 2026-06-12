"""Auditoria de QUALIDADE DO DADO do catálogo (data/books.json).

Por quê isto existe: a análise de gold standard concluiu que **o dado é o teto** — nenhuma
esperteza de RAG conserta sinopse contraditória ou templada. Este script torna o problema
VISÍVEL e QUANTIFICADO: roda na ingestão, aponta exatamente onde o catálogo falha e dá uma
nota de qualidade. É o primeiro passo da "limpeza na ingestão" que o RESULTS.md aponta como
a correção definitiva dos conflitos título×sinopse (Q4/Q5).

100% DETERMINÍSTICO (sem LLM, sem rede): roda offline, no CI, e é testável — mesmo ethos do
resto do núcleo (o que pode ser verificado por regra não se delega ao modelo).

Checagens:
1. Integridade de schema  — campos ausentes/vazios, ids/ISBNs duplicados, ano fora de faixa.
2. Conflito título×matéria — o achado Q4/Q5: título diz "Física", sinopse diz "currículo de Literatura".
3. Sinopses duplicadas    — dado templado (várias obras compartilham a MESMA sinopse).
4. Clusters de edição      — variantes da mesma obra (reusa catalog.cluster_of).
5. Outliers de vocabulário — gênero/público que aparece 1x só (possível typo/inconsistência).

Saída: data/quality_report.json (consumido pelo B.I.) + resumo no console com a NOTA.
Uso:  python scripts/audit_catalog.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402
from app.catalog import Catalog, get_catalog, normalize  # noqa: E402

REQUIRED_FIELDS = ["id", "titulo", "autores", "sinopse", "generos", "publico_alvo",
                   "ano_publicacao", "idioma", "isbn"]

# "cobrindo o currículo de <MATÉRIA>," — a matéria que a SINOPSE realmente descreve.
# Non-greedy até vírgula/conector: captura "Literatura", "Química", "História do Brasil".
_CURRICULO_RE = re.compile(r"curr[íi]culo de ([A-Za-zÀ-ú][\wÀ-ú ]+?)(?:,| com| para|\.|$)",
                           re.IGNORECASE)


def _subject_from_title(titulo: str) -> str | None:
    """Matéria declarada no TÍTULO de um didático: tudo antes de 'ensino médio/fundamental'.
    'Física ensino médio — 1ª série' -> 'fisica'; 'História do Brasil ensino...' -> 'historia do brasil'.
    None se não é um título didático no formato esperado."""
    n = normalize(titulo)
    m = re.split(r"\s+ensino\s+(?:medio|fundamental)", n)
    if len(m) >= 2 and m[0].strip():
        return m[0].strip()
    return None


def _subject_from_synopsis(sinopse: str) -> str | None:
    """Matéria que a SINOPSE descreve ('cobrindo o currículo de X'). None se não houver."""
    m = _CURRICULO_RE.search(sinopse or "")
    return normalize(m.group(1)) if m else None


def _check_schema(books: list[dict]) -> list[dict]:
    """Erros DUROS de integridade — cada um quebra a confiança no dado de forma objetiva."""
    achados: list[dict] = []
    ids = Counter(b.get("id") for b in books)
    isbns = Counter(b.get("isbn") for b in books if b.get("isbn"))
    for b in books:
        bid = b.get("id", "<sem id>")
        for f in REQUIRED_FIELDS:
            v = b.get(f)
            if v is None or (isinstance(v, (str, list)) and len(v) == 0):
                achados.append({"id": bid, "tipo": "campo_ausente_ou_vazio", "detalhe": f})
        if ids.get(b.get("id"), 0) > 1:
            achados.append({"id": bid, "tipo": "id_duplicado", "detalhe": b.get("id")})
        if b.get("isbn") and isbns.get(b["isbn"], 0) > 1:
            achados.append({"id": bid, "tipo": "isbn_duplicado", "detalhe": b["isbn"]})
        ano = b.get("ano_publicacao")
        if isinstance(ano, int) and not (1900 <= ano <= config.CURRENT_YEAR):
            achados.append({"id": bid, "tipo": "ano_fora_de_faixa", "detalhe": ano})
        isbn = str(b.get("isbn", ""))
        if isbn and not re.fullmatch(r"\d{13}", isbn):    # ISBN-13 é 13 dígitos
            achados.append({"id": bid, "tipo": "isbn_malformado", "detalhe": isbn})
    return achados


def _check_titulo_materia(books: list[dict]) -> list[dict]:
    """O achado-assinatura (Q4/Q5): para livros cuja SINOPSE declara um currículo, a matéria
    do título deve bater com a da sinopse. Divergência = contradição interna do dado."""
    achados: list[dict] = []
    for b in books:
        materia_sin = _subject_from_synopsis(b.get("sinopse", ""))
        materia_tit = _subject_from_title(b.get("titulo", ""))
        if materia_sin and materia_tit and materia_sin != materia_tit:
            achados.append({
                "id": b["id"], "titulo": b["titulo"],
                "materia_no_titulo": materia_tit, "materia_na_sinopse": materia_sin,
            })
    return achados


def _check_sinopses_duplicadas(books: list[dict]) -> dict:
    """Dado templado: quantas obras compartilham a MESMA sinopse (normalizada)."""
    grupos: dict[str, list[str]] = defaultdict(list)
    for b in books:
        grupos[normalize(b.get("sinopse", ""))].append(b["id"])
    repetidas = {s: ids for s, ids in grupos.items() if len(ids) > 1}
    livros_afetados = sum(len(ids) for ids in repetidas.values())
    distintas = len(grupos)
    return {
        "sinopses_distintas": distintas,
        "total_livros": len(books),
        "distintas_pct": round(100 * distintas / len(books), 1) if books else 0,
        "grupos_repetidos": len(repetidas),
        "livros_com_sinopse_repetida": livros_afetados,
        "maior_grupo": max((len(ids) for ids in repetidas.values()), default=0),
    }


def _check_clusters_edicao(catalog: Catalog) -> list[dict]:
    """Variantes de edição da mesma obra (reusa o cluster_of do catálogo)."""
    grupos: dict[str, list[str]] = defaultdict(list)
    for b in catalog.books:
        grupos[catalog.cluster_of(b["id"])].append(b["id"])
    return [{"cluster": c, "ids": ids} for c, ids in grupos.items() if len(ids) > 1]


def _check_vocab_outliers(catalog: Catalog) -> dict:
    """Gênero/público que aparece UMA vez só — candidato a typo/inconsistência de rotulagem."""
    gen = Counter(g for b in catalog.books for g in b.get("generos", []))
    pub = Counter(b.get("publico_alvo", "") for b in catalog.books if b.get("publico_alvo"))
    return {
        "generos_frequencia_1": sorted([g for g, n in gen.items() if n == 1]),
        "publico_frequencia_1": sorted([p for p, n in pub.items() if n == 1]),
    }


def audit(catalog: Catalog | None = None) -> dict:
    """Roda todas as checagens e devolve o relatório + uma NOTA de qualidade transparente.
    Função pura (testável): não escreve em disco nem imprime."""
    catalog = catalog or get_catalog()
    books = catalog.books
    schema = _check_schema(books)
    contradicoes = _check_titulo_materia(books)
    dup = _check_sinopses_duplicadas(books)
    clusters = _check_clusters_edicao(catalog)
    vocab = _check_vocab_outliers(catalog)

    # NOTA de qualidade (0-100) — composição TRANSPARENTE e documentada (não um número mágico):
    #  • erro de schema é o mais grave (quebra a confiança objetivamente): -4 cada
    #  • contradição título×matéria é risco de correção direto: -3 cada
    #  • templagem penaliza pela fração de sinopses NÃO distintas (até -25)
    #  • outlier de vocabulário é leve: -0,5 cada
    pen_schema = 4 * len(schema)
    pen_contra = 3 * len(contradicoes)
    pen_templ = (1 - dup["distintas_pct"] / 100) * 25
    pen_vocab = 0.5 * (len(vocab["generos_frequencia_1"]) + len(vocab["publico_frequencia_1"]))
    nota = max(0.0, round(100 - pen_schema - pen_contra - pen_templ - pen_vocab, 1))

    return {
        "total_livros": len(books),
        "nota_qualidade": nota,
        "penalidades": {"schema": round(pen_schema, 1), "contradicoes": round(pen_contra, 1),
                        "templagem": round(pen_templ, 1), "vocab": round(pen_vocab, 1)},
        "resumo": {
            "erros_schema": len(schema),
            "contradicoes_titulo_materia": len(contradicoes),
            "sinopses_distintas_pct": dup["distintas_pct"],
            "clusters_de_edicao": len(clusters),
        },
        "achados": {
            "schema": schema,
            "conflito_titulo_materia": contradicoes,
            "sinopses_duplicadas": dup,
            "clusters_edicao": clusters,
            "vocab_outliers": vocab,
        },
    }


def main() -> int:
    rep = audit()
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = config.DATA_DIR / "quality_report.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")

    r = rep["resumo"]
    print(f"== Auditoria de qualidade do catálogo ({rep['total_livros']} livros) ==")
    print(f"  NOTA DE QUALIDADE: {rep['nota_qualidade']}/100")
    print(f"  - erros de schema: {r['erros_schema']}")
    print(f"  - contradições título×matéria: {r['contradicoes_titulo_materia']}")
    print(f"  - sinopses distintas: {r['sinopses_distintas_pct']}% (dado templado abaixo de ~100%)")
    print(f"  - clusters de edição (obras com variantes): {r['clusters_de_edicao']}")
    for c in rep["achados"]["conflito_titulo_materia"][:10]:
        print(f"    ⚠️ {c['id']} \"{c['titulo']}\": título={c['materia_no_titulo']} "
              f"× sinopse={c['materia_na_sinopse']}")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
