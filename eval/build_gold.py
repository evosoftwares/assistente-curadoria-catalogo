"""Gera o gold-set (eval/gold.json) de forma DOCUMENTADA e anti-circular.

Método de rotulagem (recomendado pelo red-team):
1. Os candidatos NÃO vêm do planner de produção (evita avaliação circular). Para as
   perguntas semânticas, os ids relevantes foram curados À MÃO lendo título+sinopse+
   metadados dos 200 livros, com nota graduada 2/1/0:
     2 = claramente satisfaz a pergunta
     1 = aceitável/marginal (tema certo, mas com ressalva)
     0 = distrator difícil (parece relevante mas não é) — testa precisão
2. As perguntas determinísticas (filtro/agregação) têm o conjunto-verdade COMPUTADO
   diretamente dos dados (ano>=2023, infantil, mín/máx de ano), não eyeballado.
3. Há um campo expected_behavior para as armadilhas (abstain/clarify/acknowledge_limitation).
4. Métricas de recuperação são computadas POR CLUSTER de edição (ver app/catalog.py).

Observação sobre os dados: o catálogo é sintético e fortemente TEMPLADO (87 sinopses
distintas para 200 livros). Por isso muitos "conjuntos relevantes" são clusters de
sinopse, e várias perguntas são armadilhas (Q3 não tem cidades pequenas; Q9 nenhum
livro japonês é sobre cidades; Q10 está fora do catálogo).

Uso:  python eval/build_gold.py
"""
from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.catalog import get_catalog  # noqa: E402


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def main() -> int:
    cat = get_catalog()
    books = cat.books

    def syn(b):
        return _norm(b.get("sinopse", ""))

    # --- conjuntos determinísticos (computados dos dados) ---
    children = [b["id"] for b in books if "crianc" in _norm(b["publico_alvo"])]
    last3 = sorted(b["id"] for b in books if b["ano_publicacao"] >= 2023)
    brain = [b["id"] for b in books if "cerebro humano" in syn(b)]
    selfhelp = [b["id"] for b in books if "reorganizacao interna" in syn(b)]
    anos = [b["ano_publicacao"] for b in books]
    ymin, ymax = min(anos), max(anos)
    oldest = [b["id"] for b in books if b["ano_publicacao"] == ymin]
    newest = sorted(b["id"] for b in books if b["ano_publicacao"] == ymax)
    didatico_em = sorted(b["id"] for b in books
                         if "Didático" in b["generos"] and "ensino médio" in b["publico_alvo"])

    def graded(ids2=(), ids1=(), ids0=()):
        out = [{"id": i, "grade": 2} for i in ids2]
        out += [{"id": i, "grade": 1} for i in ids1]
        out += [{"id": i, "grade": 0} for i in ids0]
        return out

    gold = [
        {
            "qid": 1,
            "question": "Quais livros do nosso catálogo abordam temas de inteligência artificial ou sistemas distribuídos? Cite os mais relevantes e o público-alvo de cada um.",
            "type": "semantic",
            "expected_behavior": "answer",
            "relevant_ids": graded(
                ids2=["BK0014", "BK0064", "BK0001"],
                ids1=["BK0063", "BK0125", "BK0128", "BK0040", "BK0069", "BK0126", "BK0013", "BK0158", "BK0181"],
            ),
            "notes": "Distribuídos = BK0014/BK0064. IA/dados = modelagem preditiva/estatística (BK0001/BK0013...). Sci-fi de tema IA = grau 1. Pede público-alvo de cada um.",
        },
        {
            "qid": 2,
            "question": "Estou montando uma lista de leitura para o Dia das Crianças. Sugira 5 livros do nosso catálogo, considerando faixas etárias diferentes dentro do público infantil.",
            "type": "filter+diversity",
            "expected_behavior": "acknowledge_limitation",
            "relevant_ids": graded(ids2=children),
            "notes": "ARMADILHA: os 10 infantis estão todos em UMA faixa ('Crianças de 4 a 10 anos'). 'Faixas diferentes' não é suportado pelos dados → boa resposta sugere até 5 títulos E explicita a limitação, sem inventar subfaixas.",
        },
        {
            "qid": 3,
            "question": "Tenho um cliente que adorou romances literários ambientados em pequenas cidades brasileiras, com narrativa lenta e foco em memória familiar. Que livros do nosso catálogo eu recomendaria?",
            "type": "semantic",
            "expected_behavior": "answer",
            "relevant_ids": graded(
                ids1=["BK0051", "BK0053", "BK0062", "BK0090", "BK0096", "BK0145", "BK0164"],
                ids0=["BK0046", "BK0083", "BK0110", "BK0113", "BK0168"],
            ),
            "notes": "ARMADILHA sutil: NÃO há romances em 'pequenas cidades'. Os de literatura brasileira se passam em cidades GRANDES (Floripa/Curitiba/Salvador/Porto Alegre, grau 1) ou no EXTERIOR (Tóquio/Istambul/Estocolmo/Cidade do Cabo, grau 0). Boa resposta recomenda os brasileiros de memória familiar E ressalva que não são cidades pequenas.",
        },
        {
            "qid": 4,
            "question": "Quais livros didáticos do ensino médio temos atualmente, e quais matérias eles cobrem?",
            "type": "filter",
            "expected_behavior": "answer",
            "relevant_ids": graded(ids2=didatico_em),
            "expected_fields": ["matérias: Física, História do Brasil, Biologia"],
            "notes": "Filtro duro gênero=Didático + público=ensino médio. Deve listar as matérias.",
        },
        {
            "qid": 5,
            "question": "Um leitor está procurando um livro de não-ficção sobre o cérebro humano, escrito de forma acessível. O que temos disponível?",
            "type": "semantic+filter",
            "expected_behavior": "answer",
            "relevant_ids": graded(ids2=brain, ids0=selfhelp),
            "notes": "A sinopse sobre 'cérebro humano' é compartilhada por 6 livros, alguns com TÍTULO enganoso (ex.: 'A vida secreta das florestas'). Título sozinho falha; a sinopse carrega o tema. Distrator grau 0: cluster de autoajuda 'reorganização interna'.",
        },
        {
            "qid": 6,
            "question": "Quero montar uma campanha de lançamento focada em livros publicados nos últimos 3 anos. Quais livros do catálogo se encaixam? Liste por categoria.",
            "type": "filter+group",
            "expected_behavior": "answer",
            "relevant_ids": graded(ids2=last3),
            "expected_value": {"ano_min": 2023, "convencao": "ultimos 3 anos == ano >= CURRENT_YEAR(2026)-3 == 2023"},
            "notes": "Filtro de ano relativo (computado em Python, não pelo LLM) + agrupar por categoria. Conjunto-verdade = todos com ano>=2023.",
        },
        {
            "qid": 7,
            "question": "Temos algum livro sobre liderança de equipes em ambientes de incerteza?",
            "type": "semantic",
            "expected_behavior": "answer",
            "relevant_ids": graded(ids2=["BK0022", "BK0111", "BK0121", "BK0133", "BK0134", "BK0187"]),
            "notes": "6 livros compartilham a sinopse 'liderar equipes em ambientes de incerteza'. BK0133 ('Liderança em tempos incertos') é o mais direto.",
        },
        {
            "qid": 8,
            "question": "Qual é o livro mais antigo do nosso catálogo? E qual é o mais recente?",
            "type": "aggregation",
            "expected_behavior": "answer",
            "relevant_ids": graded(ids2=oldest + newest),
            "expected_value": {"min_year": ymin, "max_year": ymax, "oldest_ids": oldest, "newest_ids": newest},
            "notes": f"Mais antigo é ÚNICO ({oldest} em {ymin}). Mais recente é um EMPATE de {len(newest)} livros em {ymax}. CORRETA exige sinalizar o empate (ou 'vários de {ymax}'). Excluída de precision/recall (não é problema de recuperação).",
        },
        {
            "qid": 9,
            "question": 'Recebi um pedido de um cliente que quer "aquele livro do autor japonês sobre cidades". Você consegue identificar de qual livro ele provavelmente está falando?',
            "type": "ambiguous",
            "expected_behavior": "clarify",
            "relevant_ids": graded(ids1=["BK0076", "BK0163"]),
            "notes": "ARMADILHA: os 2 livros traduzidos do japonês NÃO são sobre cidades. CORRETA = pede contexto OU lista candidatos como incertos, SEM cravar um único confiante.",
        },
        {
            "qid": 10,
            "question": 'Você tem em catálogo o livro "Memórias Póstumas de Brás Cubas" de Machado de Assis? Se sim, em qual edição?',
            "type": "out_of_catalog",
            "expected_behavior": "abstain",
            "relevant_ids": [],
            "notes": "FORA do catálogo. CORRETA = afirma que não consta, SEM inventar edição/ISBN.",
        },
    ]

    out_path = Path(__file__).resolve().parent / "gold.json"
    out_path.write_text(json.dumps(gold, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"gold.json escrito com {len(gold)} perguntas em {out_path}")
    print(f"  Q4 didáticos EM: {didatico_em}")
    print(f"  Q6 (>=2023): {len(last3)} livros")
    print(f"  Q8 oldest={oldest}({ymin})  newest={len(newest)} em {ymax}")
    print(f"  Q5 cérebro: {brain}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
