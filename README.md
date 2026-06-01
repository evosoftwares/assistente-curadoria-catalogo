# 📚 Assistente de Curadoria do Catálogo

MVP de um assistente que responde **perguntas em português** sobre um catálogo de ~200 livros,
usando **LLM + RAG híbrido**, sempre devolvendo a resposta **e as referências** (livros usados).

> Desafio técnico — Engenheiro(a) de IA Full-Stack. Backend Python/FastAPI + Google Gemini +
> UI Streamlit. Foco em **decisões, integração LLM/RAG, avaliação e trade-offs**.

---

## 1. Problema & usuário
Equipes internas de uma editora (editorial, marketing, vendas, atendimento) precisam consultar o
catálogo o tempo todo: *"o que temos sobre X?"*, *"monte uma lista temática"*, *"sugira parecidos"*,
*"temos o livro Y?"*. Hoje isso é busca manual em planilha. O assistente transforma o catálogo em
um **colega consultável** que responde em segundos — **com fontes** e **sem inventar**.

## 2. Como rodar localmente (passos exatos)

```bash
# 1) Ambiente
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
# Linux/Mac:           source .venv/bin/activate
pip install -r requirements.txt

# 2) Chave (a geração e os embeddings usam o Gemini)
cp .env.example .env          # Windows: copy .env.example .env
#   edite .env e preencha GEMINI_API_KEY=...   (https://aistudio.google.com/app/apikey)

# 3) Construir o índice de embeddings (cacheado; roda uma vez)
python scripts/build_index.py

# 4) Subir a API
uvicorn app.api:app --reload          # http://127.0.0.1:8000  (GET /health, POST /ask)

# 5) UI da demo (em outro terminal, com a API no ar)
streamlit run ui/streamlit_app.py     # http://localhost:8501

# 6) Dashboard de KPIs (página web autocontida) + testes
python scripts/build_dashboard.py     # gera dashboard/index.html (abra no navegador) — também em GET /kpis
python -m pytest -q                   # 15 testes dos componentes determinísticos
python eval/check_facts.py            # asserta a verdade determinística (Q4/Q6/Q8)
```

Exemplo de chamada direta:
```bash
curl -X POST http://127.0.0.1:8000/ask -H "Content-Type: application/json" \
  -d "{\"question\": \"Quais livros didáticos do ensino médio temos e quais matérias cobrem?\"}"
```

> **Roda sem chave?** Sim, em modo degradado: o cache de embeddings é **commitado**, então a
> recuperação semântica funciona offline; sem chave, a geração cai para uma resposta determinística
> (lista os livros recuperados) e o planner usa o fallback por regex. Os casos determinísticos
> (mais antigo/recente, fora do catálogo, didáticos, últimos 3 anos) respondem **sem LLM nenhum**.
> Para operação 100% offline também na recuperação: `EMBEDDINGS_BACKEND=local` + `pip install sentence-transformers`.

## 3. Visão geral da arquitetura
Diagrama completo em [`docs/architecture.md`](docs/architecture.md).

```
pergunta → PLANNER (Gemini structured + fallback regex) → FILTROS DUROS (metadado)
         → [híbrido cosine+BM25+RRF]  +  [ferramentas determinísticas: agregação/grupo/diversidade]
         → GERAÇÃO ANCORADA (cita ids; abstém; dados como texto não-confiável)
         → VERIFICAÇÃO de citações → { answer, references[], retrieval_debug }
```

**Insight central:** as 10 perguntas-exemplo foram desenhadas para **quebrar um RAG vetorial ingênuo**.
Várias não são semânticas — são consultas (filtro de ano/gênero/público), agregações (mín/máx),
abstenção (livro fora do catálogo) e ambiguidade. Por isso **filtramos por metadado antes de ranquear**
e usamos **ferramentas determinísticas** para o que o LLM erraria.

## 4. Principais decisões técnicas e trade-offs

| Decisão | Por quê | Alternativa descartada |
|---|---|---|
| **Filtro de metadado antes do ranqueio** | Q4/Q6/Q8 são consultas de banco, não busca semântica | RAG vetorial puro (erra Q6/Q8) |
| **Híbrido semântico + BM25 + RRF** | Sinopses curtas/templadas em PT; nomes próprios (Q9/Q10) precisam de lexical | Só embeddings (perde match exato) / só BM25 (perde paráfrase) |
| **Ferramentas determinísticas** (mín/máx, group_by, diversidade) | Nunca confiar no LLM para aritmética/agregação | Pedir ao LLM "qual o mais antigo" (alucina) |
| **Planner LLM + fallback regex** | NL→filtros é o que escala p/ 100k livros; fallback = tolerância a falha | Só LLM (ponto único de falha) / só regras (não generaliza) |
| **LLM não calcula datas** | "últimos 3 anos" resolvido em Python (`CURRENT_YEAR−N`) — testável | Deixar o LLM fazer aritmética (não-determinístico) |
| **`gemini-embedding-001` (não local)** | Sem dependência de `torch` (~2,5 GB no Windows do revisor); PT-BR forte; cacheado | sentence-transformers local — oferecido como **fallback opcional** |
| **Cache de embeddings commitado** | Revisor roda recuperação offline, sem re-embeddar | Re-embeddar sempre |
| **Verificação de `cited_ids`** | Toda referência é um livro real recuperado (citação não-alucinada) | Confiar no texto livre do modelo |
| **Abstenção por curto-circuito (Q10)** | Remove a superfície de alucinação em "vocês têm o livro X?" | Deixar o gerador decidir com resultados fuzzy |
| **`temperature=0`** | Determinismo p/ avaliação e demo ao vivo | Amostragem (resposta instável) |

**Modelos (jun/2026, centralizados em `.env`):** geração `gemini-2.5-flash`; planner `gemini-2.5-flash-lite`;
embeddings `gemini-embedding-001` (768d). ⚠️ `text-embedding-004` (desligado 14/jan/2026) e
`gemini-2.0-flash` (desligado ~01/jun/2026) **não** são usados.

## 5. Avaliação
Detalhes e tabelas em [`eval/RESULTS.md`](eval/RESULTS.md). Três camadas:
1. **Classificação manual** das 10 (CORRETA/PARCIAL/ERRADA) — `python eval/run_manual.py`.
2. **Métricas de recuperação** (recall@k, precision@k, MRR, nDCG, dedup por edição) — `python eval/retrieval_metrics.py`.
3. **LLM-as-judge** cético, com conjunto de calibração e κ de Cohen vs. humano — `python eval/judge.py`.

O gold-set ([`eval/gold.json`](eval/gold.json)) é curado de forma **anti-circular** (independente do
planner de produção) — método documentado em [`eval/build_gold.py`](eval/build_gold.py).
Há ainda **15 testes** (`pytest`, em [`tests/`](tests/)) dos invariantes determinísticos e
[`eval/check_facts.py`](eval/check_facts.py) que **assere programaticamente** a verdade determinística
(Q4/Q6/Q8) contra o que o sistema computa. Todos os indicadores são consolidados num **dashboard web**
([`scripts/build_dashboard.py`](scripts/build_dashboard.py) → `dashboard/index.html`, também em `GET /kpis`).

> **Nota:** o código passou por uma **auditoria adversarial multiagente** (4,45/5), que apontou
> defeitos reais de fusão/agregação/rigor de avaliação — todos corrigidos (ver [`eval/RESULTS.md`](eval/RESULTS.md) §3b).

## 6. Custo aproximado por requisição
Por `/ask` ≈ 1 chamada de planner + 1 de geração + 1 embedding de consulta (~3k tokens entrada +
~450 saída):

`3000/1e6 × US$0,30 + 450/1e6 × US$2,50 ≈ **US$0,002 por requisição** (~R$0,011).`

Indexação (uma vez, cacheada): ~24k tokens × US$0,15/Mtok ≈ **US$0,005**. Repetições são grátis
(cache de resposta + de embeddings). **Em escala:** ~100k req/dia ≈ ~US$200/dia no Flash; planner no
Flash-Lite + cache de resposta cortam ~3×. Custo é conversa de **escala/abuso**, não de preço por chamada.

## 7. Limitações conhecidas & o que eu faria com mais tempo
- **Dados sintéticos/templados:** 87 sinopses distintas p/ 200 livros; algumas perguntas são
  insatisfazíveis pelos dados (Q2 só tem 1 faixa etária; Q3 não tem "cidades pequenas"; nenhum livro
  japonês é "sobre cidades"). O sistema **reconhece** isso (limitação/clarify) em vez de inventar.
- **Gold-set de 10 perguntas** é pequeno → métricas têm variância; em produção, usar feedback real.
- **LLM-as-judge** é Gemini avaliando Gemini (viés) → mitigado por calibração + κ, mas trocaria por
  outra família de modelo + amostragem humana.
- **Com mais tempo:** multi-turno; streaming; pgvector quando o corpus passar de ~50–100k; filtros
  combináveis na UI; reranqueador cross-encoder; sanitização de injeção na ingestão.

## 8. Como usei IA assistiva
Construído com **Claude Code**. A IA gerou e refatorou código sob arquitetura definida por mim; um
**red-team multiagente** estressou o desenho e pegou erros factuais de modelo (modelos do Gemini
descontinuados). Todas as decisões de RAG/avaliação foram revisadas e validadas manualmente contra os dados.

## 9. O que NÃO foi feito (escopo)
Sem autenticação, deploy, CI/CD ou cobertura total de testes (fora do escopo do desafio). UI é
funcional, não bonita. Sem fine-tuning. Multi-turno e streaming ficaram como evolução.
