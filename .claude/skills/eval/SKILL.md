---
name: eval
description: Roda a avaliação completa do assistente (manual das 10 perguntas, juiz LLM calibrado, métricas de retrieval, asserções determinísticas, gate de CI), regenera o B.I. e resume os números. Use após mudanças de comportamento ou antes de atualizar o RESULTS.md.
---

# Rodar a avaliação completa

Pré-requisito: chave de LLM no `.env` (`GEMINI_API_KEY` e/ou `OPENROUTER_API_KEY`) — sem ela
roda em modo degradado e os números NÃO valem como RESULTS. Custo típico da rodada:
~US$ 0,02–0,04; re-rodadas saem quase grátis com `LLM_CACHE_PERSIST=true` no `.env`.

Da RAIZ, com a venv (`.venv\Scripts\python.exe`), NESTA ordem:

1. `-m pytest -q` — a suíte precisa estar VERDE antes (não se avalia código quebrado).
2. `eval\run_manual.py` — roda as 10 perguntas pelo pipeline; preserva os rótulos humanos
   já preenchidos no `results_manual.md`.
3. `eval\judge.py` — **a calibração 4/4 é obrigatória**: se o juiz não reprovar as 4
   respostas propositalmente ruins, os vereditos NÃO são confiáveis — pare e reporte.
4. `eval\retrieval_metrics.py` — recall@k / precision@k / MRR / nDCG por pergunta.
5. `eval\check_facts.py` — asserções da verdade determinística (Q4/Q6/Q8).
6. `scripts\ci_gate.py` — o gate consolidado deve PASSAR (exit 0).
7. `scripts\build_dashboard.py` — atualiza o B.I. (`GET /kpis`).

Ao final, resuma em UMA tabela: comportamentos corretos (X/10) · vereditos do juiz (C·P·E)
· faithfulness macro · macro recall@8 (vs piso 0,7) · custo total da rodada · **o que mudou**
vs os números registrados em `eval/RESULTS.md`.

Se algo REGREDIU: não atualize o RESULTS.md — investigue a causa primeiro (o histórico de
auditoria do projeto vale mais que um número bonito).
