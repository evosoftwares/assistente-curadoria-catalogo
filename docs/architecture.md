# Arquitetura — Assistente de Curadoria do Catálogo

```
                         POST /ask {question}
                                  │
                                  ▼
                    ┌──────────────────────────┐
                    │  PLANNER (Gemini Flash-   │   structured output → PlannerLLMOutput
                    │  Lite, structured output) │   • semantic_queries[]  (OR p/ Q1)
                    │  + FALLBACK regex          │   • generos / publico / idioma_contains
                    └────────────┬──────────────┘   • years_back, aggregation, group_by,
                                 │                    diversity, title_lookup, is_ambiguous
            Python resolve datas (CURRENT_YEAR−N) e VALIDA enums vs vocabulário real
                                 │
                                 ▼
               ┌──────────────── RetrievalPlan ────────────────┐
               │                                                │
   title_lookup & !ambíguo?                          (demais perguntas)
               │                                                │
   ┌───────────▼───────────┐               ┌────────────────────▼─────────────────────┐
   │ Pertencimento (Q10)   │               │ FILTROS DUROS (fonte da verdade):         │
   │ rapidfuzz título+autor│               │ ano / idioma sempre; gênero/público duros │
   │  match? → responde    │               │ se categóricos. 200 → subconjunto.        │
   │  ausente? → ABSTÉM     │               └───────────────┬───────────────┬───────────┘
   │  (curto-circuito,      │                               │               │
   │   sem LLM)             │                  RANQUEIO HÍBRIDO        ATALHOS DETERMINÍSTICOS
   └───────────────────────┘                  cosine + BM25 → RRF     • Q8 mín/máx ano (+empate)
                                               (soft-boost de gênero    • Q6 group_by gênero
                                                quando não é filtro      • Q2 diversidade por faixa
                                                duro; top_cosine p/        (+ reconhece limitação)
                                                observabilidade)        • Q9 idioma + clarify
                                 │                               │
                                 └───────────────┬───────────────┘
                                                 ▼
                       GERAÇÃO ANCORADA (Gemini Flash)
                       • dados do catálogo como TEXTO não-confiável (anti-injeção)
                       • saída JSON {answer, cited_ids}
                       • degradação graciosa: sem LLM → resposta determinística (template)
                                                 ▼
                       VERIFICAÇÃO DE CITAÇÕES (Python)
                       cited_ids ∩ context_ids → references[] só com ids reais
                                                 ▼
                  { answer, references[], retrieval_debug{plan, ids, latência, tokens, custo} }
```

## Camadas e responsabilidades

| Módulo | Responsabilidade |
|---|---|
| `app/catalog.py` | Carrega livros, vocabulário controlado, clusters de edição, busca fuzzy de título |
| `app/embeddings.py` | `gemini-embedding-001` (768d) + cache em disco (hash do catálogo) + fallback local |
| `app/planner.py` | NL → `RetrievalPlan` (LLM structured + fallback regex; datas em Python) |
| `app/retriever.py` | Filtro duro + híbrido cosine/BM25/RRF + top_cosine (observabilidade) |
| `app/tools.py` | Agregação mín/máx, agrupamento por categoria, diversificação |
| `app/pipeline.py` | Orquestra tudo; abstenção/clarify/limitação; verificação de citações |
| `app/llm.py` | Wrapper Gemini + contabilidade de tokens/custo |
| `app/api.py` | FastAPI `POST /ask`, `GET /health`, logs estruturados |
| `ui/streamlit_app.py` | UI mínima para demo (resposta + referências + debug) |
| `eval/` | gold-set, métricas de recuperação, LLM-as-judge, classificação manual |

## Por que esta forma (e não RAG vetorial puro)
Várias das 10 perguntas **não são** semânticas: Q4/Q6 são filtros, Q8 é agregação, Q10 é
pertencimento, Q9 é ambiguidade. Embeddings sozinhos erram essas. Filtrar por metadado
**antes** de ranquear e usar **ferramentas determinísticas** para agregação/agrupamento é o
que torna o sistema correto e auditável.
