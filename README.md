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

# 2) Chave(s) — qualquer uma das duas liga a geração:
cp .env.example .env          # Windows: copy .env.example .env
#   OPENROUTER_API_KEY=...  -> chat ROTEADO via OpenRouter (https://openrouter.ai/keys)
#   GEMINI_API_KEY=...      -> chat via Gemini direto E embeddings (https://aistudio.google.com/app/apikey)
#   (Embeddings sempre usam Gemini/local — p/ regenerar o índice é preciso a GEMINI_API_KEY;
#    o cache de embeddings commitado dispensa isso p/ rodar.)

# 3) Construir o índice de embeddings (cacheado; roda uma vez)
#    (Os "cartões de contexto" do Contextual Retrieval já vêm gerados e commitados em
#     data/context_cards.json. Para regenerá-los: python scripts/build_context_cards.py)
python scripts/build_index.py

# 4) Subir a API
uvicorn app.api:app --reload          # http://127.0.0.1:8000  (GET /health, POST /ask)

# 5) UI da demo (em outro terminal, com a API no ar)
streamlit run ui/streamlit_app.py     # http://localhost:8501

# 6) Dashboard de KPIs (página web autocontida) + testes
python scripts/build_dashboard.py     # gera dashboard/index.html (abra no navegador) — também em GET /kpis
python -m pytest -q                   # 53 testes (determinístico + segurança + roteamento/cache + feedback + MCP)
python eval/check_facts.py            # asserta a verdade determinística (Q4/Q6/Q8)
python scripts/ci_gate.py             # GATE de regressão (pytest + check_facts + piso de recall@8); sai !=0 se regredir

# 7) Atalhos de execução local (alternativas aos passos 4-5)
#    a) Windows sem Docker — usa a .venv, sobe API+UI minimizados e abre o navegador:
powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1        # (-Stop derruba)
#    b) Docker (qualquer SO) — 1 imagem, 2 serviços, sem tocar no Python da máquina:
docker compose up --build            # UI: http://localhost:8501 · API: http://localhost:8000
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

**Roteamento e economia:** o lado de chat (planner/geração/juiz) é servido por um cliente
**roteado** — `LLM_BACKEND=auto` usa o **OpenRouter** (troca de modelo/provedor por `.env`,
fallback automático entre modelos, juiz de outra família, custo real por chamada) quando há
`OPENROUTER_API_KEY`; senão, Gemini direto. Embeddings ficam sempre no Gemini/local (o OpenRouter
não embedda). Em cima disso, um **roteamento inteligente por solicitação** escolhe o peso do
modelo (light/standard/heavy) pela complexidade real do trabalho, e um **cache de chamadas LLM**
soma-se aos caches de resposta. Fluxo completo com fluxograma:
[`docs/economia_de_tokens.md`](docs/economia_de_tokens.md).

**Integração (MCP):** o assistente também é consumível como **ferramenta por agentes de IA** —
[`mcp_server.py`](mcp_server.py) expõe `perguntar_catalogo`, `enviar_feedback` e `kpis_resumo`
via MCP (JSON-RPC sobre stdio, implementado **sem SDK** — ~100 linhas auditáveis, sem dependência
nova). O [`.mcp.json`](.mcp.json) conecta automaticamente no Claude Code ao abrir a pasta; o
feedback enviado por agentes cai no **mesmo dataset** do loop v2. Para sessões de IA assistiva,
o repo traz [`CLAUDE.md`](CLAUDE.md) (convenções) e skills de projeto (`/demo`, `/eval` em
`.claude/skills/`).

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
| **`temperature=0`** | Determinismo p/ avaliação e demo ao vivo (e torna os caches seguros) | Amostragem (resposta instável) |
| **Roteamento de modelos (OpenRouter)** | Trocar modelo/provedor sem deploy; fallback automático; juiz de OUTRA família (anti-viés); custo real por chamada | Acoplar o código ao SDK de um único provedor |
| **Roteamento inteligente por solicitação** | Narrar fatos prontos/contexto mínimo não precisa do modelo caro (tier light ≈ −70% nessas perguntas); decisão em Python, testável | Um modelo único p/ tudo (paga flash p/ reformatar fatos) |
| **Cache de chamadas LLM** (além do de respostas) | Re-rodar eval/judge e repetições de sub-chamada custam US$ 0 (det. por `temperature=0`) | Pagar de novo por chamadas idênticas |

**Técnicas avançadas (2026) incluídas:** **Contextual Retrieval** (cartões de contexto por livro
concatenados ao texto indexado — +recall, ataca o dado templado); **Structured Outputs** na geração
(`response_schema`, JSON garantido); **cache semântico** (reusa resposta de paráfrases, cos ≥0,92) além
do exact-match. Reranking/ColBERT/GraphRAG/pgvector foram avaliados e **adiados** como overkill para 200
livros (gatilhos de migração documentados).

**Modelos (jun/2026, centralizados em `.env`):** geração `gemini-2.5-flash`; planner/tier-light
`gemini-2.5-flash-lite`; embeddings `gemini-embedding-001` (768d). Roteado via OpenRouter, os slugs
equivalentes são `google/gemini-2.5-flash(-lite)`, com fallback e juiz em `anthropic/claude-haiku-4.5`
(outra família). ⚠️ `text-embedding-004` (desligado 14/jan/2026) e `gemini-2.0-flash`
(desligado ~01/jun/2026) **não** são usados.

## 5. Avaliação
Detalhes e tabelas em [`eval/RESULTS.md`](eval/RESULTS.md). Três camadas:
1. **Classificação manual** das 10 (CORRETA/PARCIAL/ERRADA) — `python eval/run_manual.py`.
2. **Métricas de recuperação** (recall@k, precision@k, MRR, nDCG, dedup por edição) — `python eval/retrieval_metrics.py`.
3. **LLM-as-judge** cético, com conjunto de calibração e κ de Cohen vs. humano — `python eval/judge.py`.

O gold-set ([`eval/gold.json`](eval/gold.json)) é curado de forma **anti-circular** (independente do
planner de produção) — método documentado em [`eval/build_gold.py`](eval/build_gold.py).
A UI também coleta **feedback humano por resposta** (👍/👎 + comentário) via `POST /feedback` →
`data/feedback.jsonl` (1 linha JSON por evento, com pergunta+resposta+plano+ids+custo) — o início
do **gold-set vivo** do roadmap v2.
Há ainda **53 testes** (`pytest`, em [`tests/`](tests/)) dos invariantes determinísticos + segurança + roteamento/cache + feedback + protocolo MCP, e
[`eval/check_facts.py`](eval/check_facts.py) que **assere programaticamente** a verdade determinística
(Q4/Q6/Q8) contra o que o sistema computa. O juiz também reporta **faithfulness** (estilo RAGAS, ~0,93)
— fração de afirmações com suporte no contexto. Um **gate de regressão** ([`scripts/ci_gate.py`](scripts/ci_gate.py),
também em [`.github/workflows/ci.yml`](.github/workflows/ci.yml)) roda pytest + check_facts + piso de recall@8 e falha o build se algo regredir. Todos os indicadores são consolidados num **dashboard web**
([`scripts/build_dashboard.py`](scripts/build_dashboard.py) → `dashboard/index.html`, também em `GET /kpis`).

> **Nota:** o código passou por uma **auditoria adversarial multiagente** (4,45/5), que apontou
> defeitos reais de fusão/agregação/rigor de avaliação — todos corrigidos (ver [`eval/RESULTS.md`](eval/RESULTS.md) §3b).

## 6. Custo aproximado por requisição
Por `/ask` ≈ 1 chamada de planner + 1 de geração + 1 embedding de consulta (~3k tokens entrada +
~450 saída):

`3000/1e6 × US$0,30 + 450/1e6 × US$2,50 ≈ **US$0,002 por requisição** (~R$0,011).`

Indexação (uma vez, cacheada): ~24k tokens × US$0,15/Mtok ≈ **US$0,005**. Repetições são grátis
(caches de resposta exato/semântico + cache de chamadas LLM + cache de embeddings). Com o
**roteamento inteligente**, perguntas de fatos prontos (Q6/Q8) caem ao tier light: ~US$0,002–0,004 →
**~US$0,0006–0,001** (≈ −70%). Via OpenRouter o custo deixa de ser estimado: cada resposta traz o
**custo real** (`usage.cost`) no `retrieval_debug`. **Em escala:** ~100k req/dia ≈ ~US$200/dia no
Flash; planner no Flash-Lite + caches + tier light cortam ~3–4×. Fluxo completo de economia (com
fluxograma): [`docs/economia_de_tokens.md`](docs/economia_de_tokens.md). Custo é conversa de
**escala/abuso**, não de preço por chamada.

## 6b. Segurança (cibersegurança)
Modelo de ameaças completo (mapeado ao **OWASP LLM Top 10**) em [`SECURITY.md`](SECURITY.md). Em resumo:
defesa anti-injeção estrutural (dados do catálogo **escapados/delimitados** + verificação de citação);
**rate limit por IP** e **teto de custo** no `/ask`; **caches limitados** (anti-DoS de memória);
**handler global de exceção** (não vaza stack trace); **sanitização de entrada**; log de pergunta
**configurável** (LGPD); CORS restrito; chave só no servidor (gitignored). Configs em `.env` (ver `SECURITY.md`).

## 7. Limitações conhecidas & o que eu faria com mais tempo
- **Dados sintéticos/templados:** 87 sinopses distintas p/ 200 livros; algumas perguntas são
  insatisfazíveis pelos dados (Q2 só tem 1 faixa etária; Q3 não tem "cidades pequenas"; nenhum livro
  japonês é "sobre cidades"). O sistema **reconhece** isso (limitação/clarify) em vez de inventar.
- **Gold-set de 10 perguntas** é pequeno → métricas têm variância; em produção, usar feedback real.
- **LLM-as-judge** era Gemini avaliando Gemini (viés) → mitigado por calibração + κ; com o
  roteamento via OpenRouter o juiz roda por padrão em **outra família** (`anthropic/claude-haiku-4.5`)
  — resta complementar com amostragem humana.
- **Com mais tempo:** multi-turno; streaming; pgvector quando o corpus passar de ~50–100k; filtros
  combináveis na UI; reranqueador cross-encoder; sanitização de injeção na ingestão.
  **Plano de evolução consolidado** (versões v1→v4, gatilhos medidos, métricas por estágio e o que
  fica de fora com o porquê): [`docs/ROADMAP.md`](docs/ROADMAP.md).

## 8. Como usei IA assistiva
Construído com **Claude Code**. A IA gerou e refatorou código sob arquitetura definida por mim; um
**red-team multiagente** estressou o desenho e pegou erros factuais de modelo (modelos do Gemini
descontinuados). Todas as decisões de RAG/avaliação foram revisadas e validadas manualmente contra os dados.

## 9. O que NÃO foi feito (escopo)
Sem autenticação nem deploy em produção (fora do escopo do desafio) — como conveniência há um
gate de CI (GitHub Actions) e execução local empacotada (Docker Compose / `scripts/run_local.ps1`).
UI é funcional, não bonita. Sem fine-tuning. Multi-turno e streaming ficaram como evolução
(plano completo por gatilhos em [`docs/ROADMAP.md`](docs/ROADMAP.md)).

### O que foi feito ALÉM do pedido (e por quê)
O **essencial foi entregue e auditado primeiro** — o histórico de commits mostra a ordem
(núcleo → auditoria adversarial → avaliação → só então os bônus), respeitando a regra do
enunciado de "não começar pelo bônus". Os itens além do escopo — roteamento de modelos
(OpenRouter) + tiers por solicitação, coletor de feedback, B.I. de operação e integração
MCP — são **bônus incrementais** construídos com IA assistiva (cujo uso o desafio pede para
documentar, ver §8): cada um está amarrado a um critério da rubrica (custo/produto/autocrítica)
ou a um passo do [`ROADMAP`](docs/ROADMAP.md), todos cobertos pelos 53 testes, e **removíveis
sem tocar o núcleo**. Qualidade do essencial > quantidade de extras — e a avaliação contínua
(gate de CI) garante que nenhum extra regrediu o comportamento 10/10.
