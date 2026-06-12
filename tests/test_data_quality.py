"""Testes da auditoria de qualidade do catálogo (scripts/audit_catalog.py) — determinístico.

Travam o detector-assinatura (conflito título×matéria do Q4/Q5), as checagens de schema e
a contagem de templagem, além de validar que a auditoria roda no catálogo REAL e acha
exatamente as contradições conhecidas. Rode com:  python -m pytest -q
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# audit_catalog vive em scripts/ (não é um pacote) — importa por caminho.
_spec = importlib.util.spec_from_file_location("audit_catalog", ROOT / "scripts" / "audit_catalog.py")
audit_catalog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit_catalog)

from app.catalog import get_catalog


# ---------- extração de matéria (título e sinopse) ----------
def test_subject_from_title():
    assert audit_catalog._subject_from_title("Física ensino médio — 1ª série") == "fisica"
    assert audit_catalog._subject_from_title("História do Brasil ensino médio — 2ª série") == "historia do brasil"
    assert audit_catalog._subject_from_title("Romance qualquer sem matéria") is None  # não-didático


def test_subject_from_synopsis():
    assert audit_catalog._subject_from_synopsis(
        "Material didático para o ensino médio cobrindo o currículo de Literatura, com foco...") == "literatura"
    assert audit_catalog._subject_from_synopsis("Sinopse comum sem currículo.") is None


# ---------- conflito título×matéria (o achado Q4/Q5) ----------
def test_detecta_conflito_titulo_materia():
    books = [
        {"id": "X1", "titulo": "Física ensino médio — 1ª série",
         "sinopse": "Material cobrindo o currículo de Literatura, com foco no ENEM."},   # CONFLITO
        {"id": "X2", "titulo": "Física ensino médio — 2ª série",
         "sinopse": "Material cobrindo o currículo de Física, com foco no ENEM."},        # OK
    ]
    out = audit_catalog._check_titulo_materia(books)
    assert len(out) == 1 and out[0]["id"] == "X1"
    assert out[0]["materia_no_titulo"] == "fisica" and out[0]["materia_na_sinopse"] == "literatura"


# ---------- schema ----------
def test_schema_detecta_dup_e_campo_vazio_e_ano():
    books = [
        {"id": "A", "titulo": "T", "autores": [], "sinopse": "s", "generos": ["G"],
         "publico_alvo": "P", "ano_publicacao": 2099, "idioma": "pt-BR", "isbn": "1234567890123"},
        {"id": "A", "titulo": "T2", "autores": ["x"], "sinopse": "s2", "generos": ["G"],
         "publico_alvo": "P", "ano_publicacao": 2010, "idioma": "pt-BR", "isbn": "123"},
    ]
    tipos = {a["tipo"] for a in audit_catalog._check_schema(books)}
    assert "id_duplicado" in tipos          # id "A" repetido
    assert "campo_ausente_ou_vazio" in tipos  # autores=[] no 1º
    assert "ano_fora_de_faixa" in tipos     # 2099 > CURRENT_YEAR
    assert "isbn_malformado" in tipos       # "123" não tem 13 dígitos


# ---------- sinopses duplicadas (templagem) ----------
def test_conta_sinopses_duplicadas():
    books = [{"id": str(i), "sinopse": "mesma sinopse"} for i in range(3)] + \
            [{"id": "u", "sinopse": "única"}]
    d = audit_catalog._check_sinopses_duplicadas(books)
    assert d["sinopses_distintas"] == 2 and d["grupos_repetidos"] == 1
    assert d["livros_com_sinopse_repetida"] == 3 and d["maior_grupo"] == 3


# ---------- integração: catálogo REAL ----------
def test_audit_catalogo_real_acha_contradicoes_conhecidas():
    rep = audit_catalog.audit(get_catalog())
    assert rep["total_livros"] == 200
    assert 0 <= rep["nota_qualidade"] <= 100
    assert rep["resumo"]["erros_schema"] == 0                  # schema do catálogo está íntegro
    ids = {c["id"] for c in rep["achados"]["conflito_titulo_materia"]}
    assert {"BK0100", "BK0122", "BK0074"} <= ids               # as contradições conhecidas (Q4/Q5)
    assert rep["resumo"]["sinopses_distintas_pct"] < 100       # dado templado, quantificado
