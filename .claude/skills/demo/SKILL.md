---
name: demo
description: Prepara a demo da banca de ponta a ponta - sobe API+UI, pré-aquece Q8/Q4/Q10 (cache quente), regenera o B.I. e entrega os links verificados. Use antes de apresentar ou para validar o ambiente completo.
---

# Preparar a demo

Execute da RAIZ do projeto, com a venv local (`.venv\Scripts\python.exe`). Siga a ordem —
cada passo valida o anterior; qualquer desvio do esperado é problema a REPORTAR, não a ignorar.

1. **Serviços no ar?** Verifique `http://127.0.0.1:8000/health` e `http://localhost:8501`.
   Se algum não responder:
   `powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1 -NoBrowser`
   e aguarde o health responder (até ~30 s).

2. **Modo real do backend:** no `/health`, confira `catalog_size=200`, `semantic_ready=true`
   e `llm_available=true`. Reporte o `llm_backend` ativo (gemini direto ou roteado via
   openrouter). Se `llm_available=false`, AVISE: a demo sairá degradada (sem chave no `.env`).

3. **Pré-aquecer o cache** (cliques instantâneos na banca). POST `/ask` com **bytes UTF-8**
   (PowerShell 5.1 corrompe acentos em string — pegadinha documentada no CLAUDE.md) para as
   3 perguntas EXATAS do roteiro, validando o comportamento de cada uma:
   - `Qual é o livro mais antigo do nosso catálogo? E qual é o mais recente?`
     → espera: `answer`, 14 referências, nota `tier=light` (economia de ~70%)
   - `Quais livros didáticos do ensino médio temos atualmente, e quais matérias eles cobrem?`
     → espera: `answer`, 5 referências (didáticos, com conflito título×sinopse sinalizado)
   - `Você tem em catálogo o livro "Memórias Póstumas de Brás Cubas" de Machado de Assis? Se sim, em qual edição?`
     → espera: `abstain`, 0 referências, custo ~US$ 0,00008 (curto-circuito sem LLM)

4. **B.I. atualizado:** `.venv\Scripts\python.exe scripts\build_dashboard.py` e confirme que
   `GET /kpis` responde 200 contendo "Operação real".

5. **Entrega final:** liste os links (UI `http://localhost:8501` · B.I.
   `http://127.0.0.1:8000/kpis`) e os lembretes do dia: ligar o **Modo técnico** na sidebar,
   abrir o **console F12**, dar **um 👍** numa resposta (popula a Taxa de Aceitação no B.I.),
   rotacionar a `GEMINI_API_KEY`, ter o screen-record (plano B) e — opcional — colar a
   `OPENROUTER_API_KEY` para mostrar o roteamento multi-provedor ao vivo.

Roteiro completo da apresentação (pitch, beats, perguntas difíceis): `docs/APRESENTACAO.md`.
