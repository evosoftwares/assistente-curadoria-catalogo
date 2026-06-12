# Assistente de Curadoria do Catálogo — guia para o Claude Code

MVP de RAG híbrido (FastAPI + Streamlit + Gemini/OpenRouter) que responde perguntas em
PT-BR sobre um catálogo de 200 livros, **sempre com referências verificadas**. É um desafio
técnico de Eng. de IA — a banca lê este repo: qualidade e honestidade valem mais que esperteza.

## Comandos essenciais (sempre da RAIZ, com a venv local)

```powershell
.venv\Scripts\python.exe -m pytest -q              # suíte completa (100% offline — nunca exige rede/chave)
.venv\Scripts\python.exe scripts\ci_gate.py        # gate: pytest + check_facts + piso de recall@8
powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1   # sobe API (:8000) + UI (:8501); -Stop derruba
.venv\Scripts\python.exe scripts\build_dashboard.py # regenera o B.I. (servido em GET /kpis)
docker compose up --build                          # alternativa containerizada (1 imagem, 2 serviços)
```

Skills do projeto: **`/demo`** (prepara a apresentação ponta a ponta) e **`/eval`**
(avaliação completa + B.I.) — em `.claude/skills/`.

## Arquitetura (mapa de 10 segundos)

- `app/pipeline.py` — orquestra o `/ask`: planner → filtros duros → ferramentas
  determinísticas (agregação/grupo/diversidade) → híbrido BM25+cosseno+RRF →
  **roteamento por tier** (light/standard/heavy) → geração ancorada → verificação de citações.
- `app/llm.py` — clientes de chat (`GeminiClient` + `OpenRouterClient`, escolhidos por
  `LLM_BACKEND=auto`), cache de chamadas, custo real. **`get_embedder()` é SEMPRE
  Gemini/local** — o OpenRouter não tem endpoint de embeddings.
- `ui/` — pacote espelhando o backend: `api_client` (HTTP) · `state` (session_state) ·
  `theme` (Carbon/IBM via CSS) · `components/` (sidebar, chat) · `browser_log` (logs F12).
- `mcp_server.py` + `.mcp.json` — o assistente como ferramenta MCP para agentes.
- Docs: `docs/architecture.md` · `docs/economia_de_tokens.md` (fluxogramas) ·
  `docs/ROADMAP.md` (evolução por gatilhos) · `docs/APRESENTACAO.md` (roteiro da banca).

## Convenções INEGOCIÁVEIS

1. **Comentários em PT-BR explicando o PORQUÊ** (não o quê) — todo código novo segue isso.
2. **Determinismo primeiro:** o LLM nunca calcula/decide o que Python pode (datas,
   agregação, validação de enums, verificação de citações).
3. **Degradação graciosa sem chave:** planner cai p/ regex, retrieval p/ BM25-only,
   geração p/ template — o app NUNCA quebra por falta de credencial.
4. **Testes novos não tocam rede nem os arquivos reais de `data/`** — use
   `tmp_path`/`monkeypatch` (o `tests/conftest.py` já desliga o usage_log na suíte).
5. Mexeu em comportamento → rode `pytest` + `ci_gate.py` ANTES de commitar.
6. **NUNCA commitar:** `.env`, `data/feedback.jsonl`, `data/usage_log.jsonl`, `data/llm_cache/`.
7. `data/embeddings.npy` **É commitado de propósito** (revisor roda offline) — não ignore.

## Pegadinhas conhecidas

- `pytest` só funciona **da raiz** (os testes importam o pacote `app`).
- PowerShell 5.1: `Invoke-RestMethod` corrompe acentos no body JSON — envie **bytes UTF-8**
  explícitos (ou use a UI/curl).
- Gemini 2.5: o *thinking* conta DENTRO de `max_output_tokens` — por isso o teto é 4096
  (1024 truncava o JSON e derrubava a geração).
- `CURRENT_YEAR` é fixado no `.env` (determinismo de "últimos N anos") — não trocar por `datetime`.
- Push: usar a conta gh **`evosoftwares`** (dona da org), não a pessoal —
  `gh auth switch --user evosoftwares` antes, e restaurar depois.
