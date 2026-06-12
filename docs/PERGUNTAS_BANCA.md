# 🎯 Perguntas da banca — guia completo de respostas

Banca: **2–3 Product Owners + 2 líderes técnicos**, ~25 min de discussão. As perguntas vêm de
ângulos diferentes (produto vs. engenharia). Este guia cobre o que é **provável** e o que é
**difícil**, com respostas curtas e ancoradas nos números REAIS do projeto.

> **Regras de ouro na hora:** não decore; adapte a profundidade ao interlocutor (clareza com PO,
> detalhe com líder técnico); tenha o código aberto; **dizer "não considerei isso" é OK** — vale
> mais que inventar. Prefira número a opinião.

**Números-âncora (estado atual, jun/2026, chat roteado via OpenRouter):**
- Catálogo: **200 livros**, 1986–2024, **43,5%** de sinopses distintas (dado sintético/templado).
- Comportamento das 10 perguntas: **10/10** correto (incl. as 4 armadilhas).
- Recuperação (híbrido): **MRR 1,0 · nDCG@8 0,95 · recall@8 0,85**.
- Juiz **cross-família** (Claude Haiku 4.5): **7 CORRETA / 2 PARCIAL / 1 ERRADA**, calibração 4/4, faithfulness 1,0.
- Custo: **~US$ 0,001/requisição** (medido); abstenção (Q10) ~US$ 0,00008.
- Qualidade do dado (auditoria): **76,9/100**, 0 erros de schema, 3 conflitos título×sinopse.
- **59 testes**, gate de CI verde, segurança OWASP LLM Top 10.

---

## A. Produto (Product Owners)

**1. Quem é o usuário e qual a dor?**
Equipes internas da editora — editorial, marketing, vendas, atendimento. Hoje consultam o
catálogo garimpando planilha. A dor é tempo e confiança: respostas lentas e sem fonte. O
assistente transforma o catálogo num "colega consultável" que responde em segundos **com as
fontes** e **sem inventar**.

**2. Como você sabe que está bom? Qual a métrica de sucesso?**
Métrica de produto-norte: **taxa de aceitação** das respostas (meta > 80%), que eu já coleto
via 👍/👎 na UI. Suportada por métricas técnicas: groundedness (toda afirmação com fonte),
abstenção correta (não inventa), e tempo de resposta. Não é "parece que funciona" — é medido.

**3. Qual risco te assusta mais?**
Uma recomendação **confiante e errada** — destrói a confiança do curador para sempre. Por isso
grounding + abstenção + verificação de citação são **pilares de arquitetura**, não features: o
sistema prefere dizer "não temos" ou "preciso de contexto" a arriscar.

**4. Priorização / roadmap?**
v1 (hoje) Q&A ancorado → **v2** produção interna + loop de feedback (já tenho o coletor E o
consumidor que vira gold-set vivo) → **v3** curadoria ativa (gerar listas/campanhas) → **v4**
sinais de negócio (vendas/estoque). Cada salto tem **gatilho medido**, não data (ver `ROADMAP.md`).

**5. Como isso vira dinheiro / valor para a editora?**
Tempo de equipe (consulta de minutos → segundos), decisões melhores de campanha/curadoria, e
no v3+ geração de listas temáticas e textos de marketing ancorados. O custo é desprezível
(~US$ 0,001/pergunta), então o ROI é essencialmente o tempo das equipes.

**6. Por que confiar num LLM se ele alucina?**
Porque eu **não confio** no LLM para o que ele erra: datas, contagens e "existe no catálogo?"
são resolvidos em Python (determinístico). O LLM só faz o que faz bem — entender linguagem e
redigir — e mesmo aí cada citação é **verificada** contra os livros recuperados. Alucinação de
citação é descartada por código, não por "pedir para o modelo não mentir".

**7. E se a pergunta for ambígua ou o livro não existir?**
São 2 das 4 armadilhas que tratei explicitamente: ambígua (Q9) → o sistema **pede contexto** e
lista candidatos; livro fora do catálogo (Q10) → **abstém** ("não consta"), sem inventar edição,
e nem chama o LLM (custo ~US$ 0,00008). Demonstro as duas ao vivo.

**8. Quanto custa operar isso em escala?**
~US$ 0,001 por pergunta medido. A ~100 mil perguntas/dia, ~US$ 100–200/dia, e os caches +
roteamento por tier cortam isso 3–4×. **Custo é conversa de escala e abuso**, não de preço
unitário — por isso já tenho rate limit, teto de custo diário e caches.

**9. O que o diferencia de jogar tudo num ChatGPT/assistente genérico?**
Um genérico não conhece o catálogo, inventa edições e não cita fonte. Aqui a resposta é
**ancorada** no acervo real, com referências verificáveis e abstenção — requisitos de uma
ferramenta de curadoria, não de um chatbot de conversa.

**10. E multi-idioma / catálogo maior / outra editora?**
A arquitetura é agnóstica: o catálogo é dado de entrada, os filtros são por metadado e a busca
é híbrida. Escalar de 200 para 100 mil livros muda só a camada de armazenamento (→ pgvector).
Multi-idioma exigiria embeddings multilíngues (o backend já suporta troca por config).

**11. Qual a maior limitação hoje, honestamente?**
O **dado**. É sintético e templado (só 43,5% de sinopses distintas) e tem contradições internas
(título "Física", sinopse "Literatura"). Construí uma auditoria que mede isso (nota 76,9/100) e
o sistema **expõe** as contradições em vez de escondê-las — mas a correção real é limpeza na
ingestão, que num catálogo real seria o primeiro passo.

**12. Como mediria adoção / sucesso no primeiro mês?**
Perguntas/semana por equipe (uso), taxa de aceitação > 80% (qualidade percebida), % de abstenções
corretas (confiança), e tempo até resposta. Tudo já instrumentado: logs estruturados + B.I. + feedback.

---

## B. Engenharia (líderes técnicos)

**13. Por que RAG híbrido (semântico + BM25 + RRF) e não vetorial puro?**
Porque várias das 10 perguntas **não são semânticas**: Q4/Q6 são filtros, Q8 é agregação, Q10 é
pertencimento. Vetorial puro erra essas. E as sinopses são curtas/templadas em PT — nomes
próprios (Q9/Q10) precisam de match **lexical**. O BM25 pega o exato, os embeddings pegam a
paráfrase, e o RRF funde os dois rankings. Medi: o híbrido leva Q3 de recall@8 0,17 → 1,0.

**14. Por que filtrar por metadado ANTES de ranquear?**
Porque ano/gênero/público são **consulta de banco**, não busca por similaridade. Filtrar antes
reduz 200 → subconjunto e garante que "didáticos do ensino médio" não traga ficção por proximidade
semântica. A relevância só decide a ordem DENTRO do que já é factualmente válido.

**15. Por que não usou um vector DB (pgvector, Pinecone)?**
A 200 livros, a matriz de embeddings cabe em memória e a busca é produto interno
sub-milissegundo, exata. pgvector resolve escala/ANN que eu **não tenho ainda**. Documentei o
**gatilho**: > ~50–100k livros ou p95 de retrieval > 100 ms. Adicionar agora seria complexidade
sem ganho — e saber *quando não usar* uma técnica é parte da resposta.

**16. Por que não reranking / cross-encoder / ColBERT / GraphRAG?**
Avaliados e **adiados** com gatilho. As métricas já estão no teto (MRR 1,0): não há espaço para
um reranker melhorar, e ele adicionaria latência + a dependência do torch (~2,5 GB) que evitei
de propósito. Gatilho para ligar: MRR < ~0,9 com corpus crescido. GraphRAG só com texto integral
multi-entidade — não é o caso.

**17. Como o planner funciona e o que acontece se o LLM falhar?**
O planner (LLM barato, structured output) transforma a pergunta em um `RetrievalPlan` (filtros +
intenção). Se ele falhar/timeout/JSON inválido **ou não houver chave**, cai num **fallback
determinístico por regex** — o sistema nunca quebra por causa do planner. E o LLM **nunca calcula
datas**: devolve `years_back=N` e o Python faz `CURRENT_YEAR − N` (testável).

**18. Como evita alucinação? Injeção de prompt?**
Três camadas: (a) geração **ancorada** (só os livros do contexto, proibido conhecimento externo);
(b) **verificação de citação** em Python — `cited_ids ∩ context_ids`, referência fora disso é
descartada; (c) anti-injeção **estrutural** — o conteúdo do catálogo entra escapado/delimitado e
caracteres que forjariam campos/instruções são neutralizados. Testei injeção na pergunta → abstém.

**19. 200 → 100k livros, o que muda na arquitetura?**
Só o **armazenamento do retriever** (matriz em memória → pgvector + índice ANN). Planner, RRF,
ferramentas determinísticas e geração ficam iguais. A indexação já é cacheada e invalidada por
hash do conteúdo. É uma troca de camada, não um redesign.

**20. Latência? Como melhoraria?**
~7 s típico, a **geração domina**. `temperature=0` + 3 camadas de cache tornam repetições
instantâneas. Próximos passos: **streaming** (corta a latência percebida para ~1 s até o 1º
token) e rodar planner+embedding concorrentes. A abstenção (Q10) já responde em ~1,4 s.

**21. Observabilidade?**
Log estruturado JSON por requisição (latência por etapa, tokens, custo real, ids, comportamento,
plano), espelhado em arquivo e consolidado num **B.I.** (`/kpis`). Em produção, esses eventos
iriam para Langfuse/Phoenix. A UI ainda loga o **fluxo passo a passo no console do navegador**.

**22. Explique o roteamento de modelos (OpenRouter) — e o risco.**
`LLM_BACKEND=auto` roteia o chat pelo OpenRouter: troca de modelo/provedor por `.env`, **fallback
automático** entre modelos, e **custo real** por chamada. Ganho concreto: o juiz roda em **outra
família** (Claude), eliminando o viés de auto-avaliação. Risco: dependência de um intermediário —
mitigado porque o `LLM_BACKEND=gemini` volta ao SDK direto sem mexer em código, e os embeddings
nunca dependem do OpenRouter (ficam no Gemini/local).

**23. O que é o "roteamento inteligente por tier"?**
Decisão **em Python** (não pergunto ao LLM qual LLM usar): quando a resposta é só **narrar um fato
já computado** (Q8 mín/máx, Q6 grupos) ou o contexto é mínimo, uso o modelo barato (tier light) —
medi ~70% de economia na Q8 sem perda. Síntese longa → tier heavy. `clarify`/limitação nunca caem
no light (nuance vale mais que centavos).

**24. Cache — não há risco de servir resposta errada?**
Sim, e tratei: o **cache semântico** (paráfrases por cosseno) é **desligado** para perguntas com
número/negação/comparação ("após 2015" vs "após 2020" têm embeddings quase idênticos mas exigem
filtros opostos). Cache exato (sha256) e cache de chamadas LLM são seguros porque `temperature=0`
torna a chamada determinística. Todos têm tamanho limitado (anti-DoS) e mutação sob lock.

**25. Concorrência — o `/ask` é síncrono?**
Sim, roda no threadpool do FastAPI; requisições concorrentes tocam estado compartilhado (caches,
contador de custo, rate limit). Por isso há **locks** serializando as mutações — foi um achado da
auditoria (SEC-02) que corrigi, com teste de regressão.

**26. Por que não fine-tuning?**
Prompt + ferramentas determinísticas + RAG resolvem, com custo de manutenção menor e troca de
modelo trivial (que o roteamento dá de graça). Fine-tuning exigiria dados rotulados que eu ainda
não tenho — o loop de feedback (v2) é justamente o que os produziria. Treinaria primeiro o
componente **menor** (um classificador de intenção), e só quando o dado justificasse.

**27. Qualidade de código / sustentabilidade?**
Separação de responsabilidades clara (catalog/planner/retriever/tools/pipeline/llm/api), o mesmo
no frontend (api_client/state/theme/components). Tudo configurável por `.env`. Comentários
explicam o **porquê** de cada decisão. 59 testes + gate de CI. Passou por **auditoria adversarial
multiagente** (4,45/5, 15 achados reais, todos corrigidos).

**28. Como o sistema degrada sem chave de API?**
Graciosamente e em camadas: sem chave, o planner vira regex, a recuperação vira BM25-only (o cache
de embeddings é commitado → busca semântica do corpus funciona offline) e a geração vira um template
factual. O app **sobe e responde** mesmo sem nenhuma credencial — e os casos determinísticos
(Q4/Q6/Q8/Q10) ficam corretos sem LLM nenhum.

**29. O que é o servidor MCP?**
Expõe o assistente como **ferramenta para agentes de IA** (perguntar/dar feedback/ler KPIs), via
JSON-RPC sobre stdio. Implementei **sem o SDK** (~100 linhas) porque o pacote `mcp` conflita com o
FastAPI pinado — coerente com a regra do desafio de não esconder a lógica. É um bônus que aponta
para o v4 (integração); removível sem tocar o núcleo.

**30. Testes — o que eles cobrem e por que offline?**
59 testes 100% offline (sem rede/chave): invariantes determinísticos (datas, agregação, citação),
camada de segurança (rate limit, injeção, sanitização), roteamento/cache (com mock de HTTP),
feedback, MCP e qualidade de dado. Offline porque o que travo são **invariantes**, não o
comportamento do LLM — e assim o gate de CI roda sem segredos.

---

## C. Avaliação e IA

**31. Como você avaliou a qualidade — e por que devo confiar?**
Três camadas: (1) **classificação manual** das 10 (10/10 comportamento); (2) **métricas de
recuperação** com gold-set **anti-circular** (recall@8 0,85, MRR 1,0); (3) **LLM-as-judge** com
conjunto de **calibração** (4 respostas ruins que ele tem de reprovar — e reprova 4/4). O gold-set
humano é a verdade; o juiz é sinal secundário e cético.

**32. LLM-as-judge não é "IA avaliando IA"? Viés?**
Era — e por isso **troquei o juiz para outra família** (Claude avaliando Gemini). Ele ficou mais
severo (de 9/10 para **7/10**), confirmando que a auto-avaliação anterior era otimista. Prefiro o
7/10 mais honesto. É a mitigação do viés, medida.

**33. Por que o juiz reprova 3 e você diz que o sistema está certo?**
Porque as 3 não-CORRETA não são alucinação: **Q10** é limitação do **próprio juiz** (a abstenção
é por curto-circuito, o contexto chega vazio e ele, cego ao catálogo, não valida "não consta");
**Q2/Q9** são pedidos insatisfazíveis/ambíguos onde o comportamento está certo (`behavior_match=3`)
mas o juiz penaliza relevância/grounding. Documentei cada um no `RESULTS.md` §3.

**34. O κ de Cohen deu 0 — isso não é péssimo?**
É um caso **degenerado**, não um sinal ruim: meus rótulos humanos são todos CORRETA (sem variância),
então o κ colapsa por construção mesmo com 70% de acordo bruto. Reporto o **acordo bruto** como
métrica primária e explico a limitação — em vez de fingir um número bonito. (Com mais variância
de rótulos, o κ volta a fazer sentido.)

**35. O gold-set de 10 perguntas não é pequeno demais?**
É — e tem variância alta, eu admito. Por isso construí o **loop de feedback**: o coletor (👍/👎)
+ o consumidor que agrega em **gold-set vivo** a partir de uso real. Em produção, as 10 perguntas
sintéticas dão lugar a centenas de queries reais rotuladas pelos próprios usuários.

**36. O que é faithfulness e por que 1,0?**
Estilo RAGAS: a fração das afirmações da resposta que têm citação de suporte no contexto. 1,0
significa que toda afirmação factual foi ancorada — coerente com a verificação de citação. Mais
robusto seria um cross-encoder NLI multilíngue (trabalho futuro).

**37. Explique gradiente descendente / por que não treina nada.**
É o algoritmo que minimiza o erro de um modelo ajustando os pesos na direção oposta ao gradiente.
Aqui eu **uso** modelos já treinados por ele (no provedor) e decidi **não treinar** — o problema
se resolve com RAG + ferramentas. Treinar exigiria dados rotulados que o loop de feedback ainda
vai produzir; o primeiro candidato seria um classificador de intenção, não o gerador.

**38. Como mediu o custo? É confiável?**
Conto tokens de cada chamada (entrada/saída) e aplico a tabela de preços; com o OpenRouter, uso o
**custo real** que vem na resposta (`usage.cost`). Cada `/ask` expõe isso no `retrieval_debug` — é
medido por requisição, não estimado de cabeça.

---

## D. Processo, escopo e IA assistiva

**39. Como você usou IA para construir isso? (o desafio pede para documentar)**
Construí com Claude Code: a IA gerou e refatorou código **sob arquitetura definida por mim**. Um
red-team multiagente estressou o desenho e pegou erros (incl. modelos do Gemini descontinuados).
Todas as decisões de RAG/avaliação foram revisadas e validadas manualmente contra os dados. O que
avaliam é como decidi/integrei/validei — não a digitação (o próprio enunciado diz isso).

**40. Tem muita coisa além do escopo (roteamento, MCP, B.I., auditoria). Por quê?**
O **essencial foi entregue e auditado primeiro** — o histórico de commits mostra a ordem (núcleo →
auditoria → avaliação → só então bônus), respeitando "não comece pelo bônus". Os extras são
incrementais, cada um amarrado a um critério da rubrica (custo/produto/autocrítica) ou ao roadmap,
todos testados (59/59) e **removíveis sem tocar o núcleo**. Qualidade do essencial > quantidade.

**41. O tempo sugerido era ~8h e isso tem bem mais...**
Uso de IA assistiva é esperado e o enunciado pede para documentar. O trabalho está na **direção e
validação**, não no volume de digitação: cada decisão tem o porquê, cada extra tem teste e gate de
regressão garantindo que nada do essencial quebrou (comportamento segue 10/10).

**42. O que faria diferente com mais tempo?**
Dado real com limpeza na ingestão (o maior lever — já tenho o validador que mostra onde falha);
multi-turno; streaming; e amadurecer o gold-set vivo com volume real de feedback para substituir
as 10 perguntas sintéticas. Nada disso é arquitetura nova — é evolução com gatilho.

**43. O que você NÃO sabe ou não considerou?**
(Responda com honestidade no momento — exemplos válidos:) avaliação com usuários reais em campo;
comportamento sob carga real (só testei concorrência em unidade); custo/latência de um reranker
no corpus grande (estimei, não medi); acessibilidade da UI. *"Minha hipótese é X, mas precisaria medir."*

**44. Se desse problema na demo ao vivo, o que faz?**
Tenho um screen-record das 3 perguntas como plano B, e o sistema roda **degradado sem chave**
(determinístico). Prefiro uma demo simples que funciona — exatamente o que o enunciado recomenda.

---

## E. Curveballs (perguntas-armadilha curtas)

- *"E se dois livros empatam como mais recente?"* → A Q8 trata: a agregação é em Python e **sinaliza
  o empate** (13 livros em 2024); um RAG ingênuo cravaria um só.
- *"E se eu pedir um livro que existe com título quase igual a um que não existe?"* → O match de
  título penaliza diferença de comprimento (token_sort), evitando que um fragmento afirme posse de
  obra maior; no limite, abstém.
- *"Por que `temperature=0`?"* → Determinismo para avaliação reproduzível, demo estável e para os
  caches renderem (mesma entrada → mesma saída).
- *"E LGPD / privacidade?"* → A pergunta crua só é logada se `LOG_QUESTIONS=true`; em produção, off
  (ou com redação de PII). CORS restrito, chave só no servidor.
- *"E se o catálogo mudar?"* → O cache de embeddings é invalidado por **hash do conteúdo** — muda o
  catálogo, reembedda só o necessário. A auditoria de qualidade rodaria na ingestão.
- *"Qual a única coisa que você mais quer que a gente note?"* → Que o sistema foi desenhado para
  **confiabilidade**, não fluência: ele sabe a hora de dizer "não sei" — e isso é arquitetura, não sorte.

---

> **Fechamento (30 s):** *"Um assistente de catálogo que responde com fontes, não inventa, e foi
> medido e auditado de verdade. Cada decisão respondeu a uma pergunta: o que essa ferramenta precisa
> para um curador CONFIAR nela? A resposta foi confiabilidade acima de fluência."*
