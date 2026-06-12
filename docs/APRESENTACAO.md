# 🎤 Roteiro de Apresentação — Assistente de Curadoria do Catálogo

> Banca: 2-3 Product Owners + 2 líderes técnicos · ~20 min de fala + ~25 min de perguntas.
> Regra de ouro da banca: **não decore**, adapte a profundidade ao interlocutor, tenha o código aberto,
> e prefira uma **demo simples que funcione** a uma elaborada que falhe. Dizer "não sei / não considerei" é OK.

---

## ✅ Checklist pré-demo (faça 10 min antes)
- [ ] `.env` com `GEMINI_API_KEY` válida (⚠️ rotacione a chave antes, e use uma nova).
      Com `OPENROUTER_API_KEY` preenchida, o chat roteia pelo OpenRouter (mostre no `/health`).
- [ ] Subir tudo com 1 comando: `powershell -File scripts\run_local.ps1` (ou `docker compose up`).
- [ ] **Pré-aquecer**: perguntar Q8, Q4 e Q10 UMA vez (expander "Perguntas-exemplo" na sidebar)
      → popula o cache (na demo saem instantâneas) E o `usage_log` (o B.I. mostra operação real).
- [ ] **Regenerar e abrir o B.I.**: `python scripts/build_dashboard.py` → aba em `GET /kpis`.
- [ ] Ligar o **Modo técnico** (toggle na sidebar) e deixar o **console (F12)** aberto numa aba —
      é onde o fluxo passo a passo de cada resposta aparece para a banca.
- [ ] Dar um 👍 numa resposta pré-aquecida (a Taxa de Aceitação aparece no B.I. — gancho do v2).
- [ ] Código aberto no editor em: `app/pipeline.py`, `app/retriever.py`, `eval/RESULTS.md`.
- [ ] **Plano B**: ter um screen-record das 3 demos caso a internet/API falhe ao vivo.
- [ ] `temperature=0` já está no `.env` (respostas determinísticas).

---

## 1. Abertura — pitch de 3 min (linguagem de PM, sem jargão)

> *"Imaginem a editora hoje: editorial, marketing, vendas e atendimento precisam o tempo todo
> consultar o catálogo — 'o que temos sobre tal tema?', 'monta uma lista pro Dia das Crianças',
> 'temos o livro X?'. Isso hoje é gente garimpando planilha.*
>
> *O que construí é um **assistente** que responde essas perguntas em português, conversando — como
> um colega que conhece o catálogo de cor. Três coisas o tornam confiável para uso interno: ele
> **sempre mostra as fontes** (os livros que usou), **não inventa** (se não temos, ele diz que não
> temos) e **sabe pedir contexto** quando a pergunta é vaga.*
>
> *Tecnicamente é um RAG — busca primeiro, responde depois, ancorado no que achou. Mas o pulo do gato
> é que descobri, analisando as 10 perguntas-exemplo, que **várias não são busca por tema**: 'livros
> dos últimos 3 anos' é um filtro de data; 'qual o mais antigo' é uma conta; 'tem o livro Y' é checar
> se existe. Um RAG ingênuo erra todas essas. Então o sistema **filtra por metadado, usa ferramentas
> determinísticas para contas, e só usa busca semântica onde ela realmente ajuda.** É isso que faz ele
> acertar as 10 — inclusive as 4 que são armadilhas."*

**Frase de efeito para fechar o pitch:** *"O sistema foi desenhado para o destino, não para o hoje:
200 livros é a amostra; a arquitetura aguenta 100 mil."*

---

## 2. Visão geral da arquitetura (1 minuto, mostrar o diagrama de `docs/architecture.md`)
Fluxo: **pergunta → planner (entende a intenção) → filtros de metadado (fonte da verdade) → recuperação
híbrida (semântico + palavra-chave) + ferramentas determinísticas (contas/agrupamento) → geração
ancorada (cita as fontes, abstém-se) → verificação de citações.**

Uma frase por bloco:
- **Planner**: o LLM transforma a pergunta em um "plano" (filtros, intenção); tem um fallback por regras se ele falhar.
- **Filtro de metadado primeiro**: ano/gênero/público são *consulta de banco*, não busca semântica.
- **Híbrido**: embeddings (significado) + BM25 (palavra exata, nomes próprios) fundidos por RRF.
- **Ferramentas determinísticas**: "mais antigo/recente" e "por categoria" são **calculados em Python** — nunca confio no LLM para conta.
- **Geração ancorada**: responde só pelos livros recuperados, cita os IDs, e o Python **verifica** que cada citação é um livro real.

---

## 3. Demo ao vivo — **Q8 → Q4 → Q10** (ordem importa: do seguro ao showstopper)

### 🔹 Q8 — "Qual é o livro mais antigo do catálogo? E o mais recente?"
- **O que dizer:** *"Repare que isso é uma conta, não uma busca. Eu NÃO deixo o LLM responder isso —
  o sistema calcula o mín/máx sobre o catálogo e o LLM só narra o resultado já pronto."*
- **O que mostrar:** a resposta traz o mais antigo (1986) e **sinaliza o empate de 13 livros em 2024**
  (um RAG ingênuo cravaria um só). É instantâneo e impossível de alucinar. **Abre estabelecendo confiança.**

### 🔹 Q4 — "Quais livros didáticos do ensino médio temos, e quais matérias cobrem?"
- **O que dizer:** *"Aqui o planner extrai um filtro (gênero=didático + público=ensino médio) e a resposta
  vem ancorada, com as fontes."*
- **O momento de ouro:** a resposta **sinaliza uma contradição do próprio dado** — "o título indica Física,
  mas a sinopse descreve Literatura". *"O dado de exemplo é sintético e tem inconsistências; em vez de
  escolher um lado em silêncio, o sistema expõe a divergência. Fidelidade ao dado inclui mostrar suas falhas."*
  Isso demonstra honestidade de grounding — exatamente o que uma ferramenta de curadoria precisa.

### 🔹 Q10 — "Vocês têm 'Memórias Póstumas de Brás Cubas', de Machado de Assis?" (**o showstopper**)
- **O que dizer:** *"Esse livro NÃO está no catálogo. A pior coisa que um assistente de curadoria pode
  fazer é inventar uma edição que não existe."*
- **O que mostrar:** ele responde **"não consta no catálogo"**, sem referências, **sem chamar o LLM**
  (curto-circuito determinístico). Custa ~US$0,00008 e é instantâneo. *"Anti-alucinação não é um prompt
  pedindo 'por favor não minta' — é arquitetura: eu checo o título contra o catálogo e nem deixo o
  gerador entrar em cena."*

> **Mostre o painel de debug** (Modo técnico na sidebar): o plano extraído, os IDs recuperados, a
> latência por etapa, o custo REAL e o **tier do roteamento**. *"Mesmo quando a resposta não é
> perfeita, ela é auditável."*
>
> Q9 (ambígua) e Q2 (faixas etárias) são as capacidades mais legais, mas as **mais frágeis ao vivo** —
> descreva-as ("ele pede contexto" / "ele admite que o dado só tem uma faixa") e mostre por uma gravação,
> não arrisque ao vivo.

### 🔹 Tour de 90 segundos pós-demo (os diferenciais novos — escolha 2 ou 3)
1. **Roteamento inteligente (na Q8, com Modo técnico ligado):** *"reparem na nota
   `tier=light`: como a resposta é só narrar um fato já computado, o sistema roteia para o
   modelo barato — essa pergunta custou ~70% menos, sem perder nada. A decisão é Python
   puro, testável; nunca pergunto ao LLM qual LLM usar."*
2. **Fluxo auditável no navegador (F12):** expanda o grupo `[curadoria]` — *"cada resposta
   loga o caminho inteiro: planner → filtros → recuperação → tier → geração → verificação
   de citações, com latência e custo de cada etapa. Auditoria sem acesso ao servidor."*
3. **Feedback fechando o loop (clique 👍):** *"cada voto grava o par
   pergunta+resposta+plano+ids — é o gold-set VIVO nascendo. No v2, isso substitui as 10
   perguntas de exemplo por avaliação com dados reais."* Abra o B.I. e mostre a Taxa de Aceitação.
4. **B.I. (`/kpis`):** qualidade (10/10, recall, juiz) + **operação real** (custo médio, p50/p95,
   mix de tiers, cache hit) + aceitação — *"o painel já lê a telemetria de produção."*
5. **Troca de provedor sem deploy (se a chave OpenRouter estiver ativa):** mostre
   `llm_backend` no `/health` — *"o juiz roda em OUTRA família (Claude) para não se
   auto-avaliar, e se um modelo cair no meio da demo, o roteador tenta o fallback sozinho."*
6. **O assistente como ferramenta de agentes (MCP):** abra `mcp_server.py` — *"além da UI e
   da API, o catálogo é consumível por agentes de IA via MCP: 3 ferramentas (perguntar,
   dar feedback, ler KPIs), protocolo implementado em ~100 linhas sem SDK — o feedback de
   um agente cai no MESMO dataset do humano. É o v4 do roadmap nascendo."*

---

## 4. Decisões técnicas: o que escolhi, o que descartei e por quê

| Decisão | Por quê | Alternativa descartada |
|---|---|---|
| Filtro de metadado **antes** do ranqueio | Q4/Q6/Q8 são consulta, não semântica | RAG vetorial puro (erra essas) |
| Híbrido semântico + BM25 + RRF | sinopses curtas/templadas; nomes próprios precisam de lexical | só embeddings / só BM25 |
| Ferramentas **determinísticas** p/ conta | nunca confiar no LLM para min/máx/contagem | pedir ao LLM "qual o mais antigo" (alucina) |
| LLM **não calcula data** | "últimos 3 anos" resolvido em Python | LLM fazendo aritmética (instável) |
| Verificação de citações em Python | toda referência é um livro real recuperado | confiar no texto livre do modelo |
| Abstenção por curto-circuito (Q10) | remove a superfície de alucinação | deixar o gerador decidir com resultado fuzzy |

**O que descartei de propósito (e o gatilho para ligar) — isto impressiona os líderes técnicos:**
- **Reranking / ColBERT / GraphRAG / vetor DB (pgvector)**: *"a 200 livros, o recall já é 0,89 e a busca
  é exata e sub-milissegundo. Essas técnicas resolvem escala/recall em corpus grande, multimodal ou
  multi-hop — problemas que eu não tenho ainda. Adicioná-las agora seria complexidade e custo sem ganho.
  Documentei o gatilho de cada uma: reranker quando crescer 10-50×; pgvector acima de ~50 mil livros;
  GraphRAG se entrar texto integral com muitas entidades."*
- **A frase-chave:** *"O que separa sênior de pleno não é saber a técnica — é saber **quando não usá-la**."*

**Técnicas avançadas que EU coloquei** (porque davam ROI nesta escala): Contextual Retrieval (cartões de
contexto por livro → recall@8 0,87→0,89), Structured Outputs na resposta, e cache semântico de paráfrases.

---

## 5. Avaliação e autocrítica (o diferencial — 15% da nota)
*"Não basta 'parece que funciona'. Montei 3 camadas:"*
1. **Classificação manual** das 10 (correta/parcial/errada) → **10/10 corretas** (comportamento).
2. **Métricas de recuperação** (recall@k, MRR, nDCG) com gold-set **anti-circular** → macro recall@8 **0,85**, MRR **1,0**, nDCG@8 **0,95**.
3. **LLM-as-judge cross-família** (`claude-haiku-4.5`, calibração 4/4) → **7/10 corretas**.

**Honestidade intelectual (diga isto, ganha pontos):**
- *"Troquei o juiz para OUTRA família de modelo (Claude avaliando Gemini) justamente para não me
  auto-avaliar. Ele ficou mais severo — caiu de 9/10 para 7/10 — e isso é exatamente o ponto: o
  juiz anterior, Gemini avaliando Gemini, era otimista. Prefiro o 7/10 mais honesto."*
- *"As 3 não-CORRETA não são alucinação: Q10 é limitação do PRÓPRIO juiz (a abstenção é por
  curto-circuito, o contexto chega vazio e ele, cego ao catálogo, não valida 'não consta'); Q2 e Q9
  são pedidos insatisfazíveis pelos dados (uma faixa etária só / pergunta ambígua), onde o
  comportamento do sistema está certo (behavior_match=3) mas o juiz penaliza a relevância."*
- *"O acordo juiz×humano é 70%, e o κ deu 0 — caso degenerado, meus rótulos humanos são todos
  'correto' (sem variância). Reporto o acordo bruto e trato o juiz como sinal cético secundário,
  em vez de fingir um número bonito."*
- *"E passei o código por uma auditoria adversarial que achou 15 pontos de melhoria — todos corrigidos,
  com 15 testes automatizados para não regredir."*

---

## 6. Custo, escala e produção
- **Custo:** ~**US$0,0015 por requisição** (verifiquei contando tokens). *"É efetivamente de graça por
  chamada — a conversa de custo é de **escala e abuso**, não de preço unitário. A ~100 mil req/dia dá
  ~US$200/dia, e cache + planner no modelo barato cortam isso ~3×."*
- **Escala (200 → 100k):** *"O retriever em memória vira pgvector com índice ANN; o planner, o RRF e a
  geração não mudam — só a camada de armazenamento."*
- **Observabilidade:** logs estruturados por requisição (latência por etapa, tokens, custo, IDs, abstenção);
  em produção iriam para um dashboard (Langfuse/Phoenix).
- **Segurança:** dados do catálogo entram como **texto não-confiável delimitado e escapado** (anti-injeção);
  referências validadas contra IDs recuperados; CORS restrito; chave só no servidor.

---

## 7. Limitações e roadmap (com mais tempo)
- **Limitações:** dado sintético/templado (87 sinopses p/ 200 livros, com conflitos título×sinopse);
  gold de 10 perguntas tem variância; juiz é Gemini-avalia-Gemini (mitigado por calibração).
- **Roadmap:** v1 (hoje) Q&A ancorado → v2 multi-turno + feedback do usuário fechando o loop de avaliação
  + pgvector multi-tenant → v3 gerar listas temáticas e textos de campanha → v4 sinais de venda/estoque.
  Detalhado com gatilhos medidos e métricas por estágio em [`ROADMAP.md`](ROADMAP.md) — se a banca
  puxar "priorização/roadmap", abra esse arquivo.

---

## 8. Perguntas difíceis da banca — respostas curtas (ensaie estas)

**Product Owners:**
- *"Quem é o usuário e qual a dor?"* → Curador/editorial/marketing/vendas; transformar um catálogo de
  planilha em um "colega consultável", com fontes, em segundos.
- *"Como sabe que está bom? Qual métrica?"* → Métrica de produto: **taxa de aceitação** da resposta (>80%);
  suportada por **groundedness** (>95% das afirmações com fonte), **abstenção correta** e **tempo de resposta**.
- *"Qual risco te assusta mais?"* → Uma recomendação **confiante e errada** — destrói a confiança do curador.
  Por isso grounding + abstenção + verificação de citação são pilares, não features.
- *"Priorização/roadmap?"* → Ver §7. v2 foca em fechar o loop com feedback real de uso.

**Líderes técnicos:**
- *"Por que um planner com LLM para 200 linhas?"* → É dimensionado para 100k multi-tenant; extrair filtros
  de linguagem natural é o problema que escala. E tem **fallback determinístico** se o LLM falhar.
- *"200 → 100k, o que muda?"* → Só o armazenamento do retriever (→ pgvector + ANN); planner/RRF/geração iguais.
- *"Como confio na sua avaliação (LLM julgando LLM)?"* → Gold-set humano anti-circular como verdade;
  recall@k/MRR como métrica objetiva; juiz como sinal secundário **com calibração** e ressalva de viés.
- *"Injeção de prompt?"* → Conteúdo do catálogo é DADO delimitado/escapado + regra explícita de ignorar
  instruções no conteúdo + verificação de citações (não cita livro não-recuperado). Testei injeção na pergunta → abstém.
- *"Latência?"* → ~7 s (a geração domina); temperature=0 + cache; streaming é o próximo passo de UX.
- *"Por que tanta coisa além do escopo (roteamento, MCP, B.I.)?"* → *"O essencial foi entregue
  e auditado primeiro — o histórico de commits mostra a ordem. Os extras são bônus incrementais
  feitos com IA assistiva (que o desafio pede para documentar): cada um amarrado a um critério
  da rubrica ou a um passo do roadmap, todos testados (53/53) e removíveis sem tocar o núcleo.
  A regra 'não comece pelo bônus' foi respeitada — e o gate de CI prova que nada regrediu."*

**Se travar:** *"Não considerei isso a fundo — minha hipótese seria X, mas precisaria medir."* (a banca valoriza honestidade.)

---

## 9. Encerramento (30 s)
*"Resumindo: um assistente de catálogo que responde com fontes, não inventa, e foi medido e auditado de
verdade. As decisões foram guiadas por uma pergunta: 'o que essa ferramenta precisa para um curador
**confiar** nela?' — e a resposta foi confiabilidade acima de fluência. Obrigado; perguntas?"*
