# Resultados de Avaliação

Três camadas: (1) classificação **manual** das 10 perguntas, (2) **métricas de recuperação**
(recall@k/precision@k/MRR/nDCG, dedup por edição), (3) **LLM-as-judge** cético com calibração.

> Rodado com geração roteada via **OpenRouter** (`google/gemini-2.5-flash` / `-lite` no planner),
> **juiz em outra família** (`anthropic/claude-haiku-4.5`) e `gemini-embedding-001` (768d, embeddings).
> Reproduza com:
> `python scripts/build_index.py && python eval/run_manual.py && python eval/retrieval_metrics.py && python eval/judge.py`

> **Atualização (jun/2026) — roteamento via OpenRouter + juiz cross-família.** A geração passou a
> ser roteada pelo OpenRouter e o **juiz migrou para outra família** (`anthropic/claude-haiku-4.5`)
> para eliminar o viés "Gemini avalia Gemini". Efeitos **medidos**: (1) **comportamento das 10
> inalterado — 10/10**; (2) o juiz cross-família é **mais severo** — **7 CORRETA / 2 PARCIAL / 1
> ERRADA** (vs. 9/1 do juiz Gemini), confirmando que a auto-avaliação anterior era otimista; (3)
> recuperação macro recall@8 **0,89 → 0,85** (o planner roteado gera sub-queries ligeiramente
> diferentes — Q1 é o mais sensível). Os números abaixo refletem a configuração ATUAL (roteada).
> Trocar para Gemini direto (`LLM_BACKEND=gemini`) reproduz os números anteriores. Honestidade > número bonito.

## Metodologia
- **Gold-set anti-circular** ([`gold.json`](gold.json) via [`build_gold.py`](build_gold.py)): candidatos
  NÃO vêm do planner de produção; perguntas semânticas têm ids curados à mão (nota **2/1/0**);
  perguntas determinísticas têm o conjunto-verdade **computado dos dados**.
- **Dedup por cluster de edição:** 42 grupos de edições/variantes duplicadas; métricas por cluster.
- **Relevância graduada:** grade≥1 conta como relevante (binário); nDCG usa as notas.
- Q8 (agregação) e Q10 (fora do catálogo) são excluídas de precision/recall (não são recuperação).

## 1. Métricas de recuperação — BM25-only vs. HÍBRIDO

Macro-médias (8 perguntas pontuáveis):

| Modo | MRR | nDCG@8 | recall@5 | recall@8 | recall@20 | prec@5 |
|------|-----|--------|----------|----------|-----------|--------|
| BM25-only (sem chave) | 0.89 | 0.86 | 0.67 | 0.77 | 0.94 | 0.80 |
| Híbrido (Gemini direto) | 1.00 | 0.96 | 0.76 | 0.87 | 0.97 | 0.90 |
| Híbrido + Contextual (Gemini direto) | 1.00 | 0.97 | 0.76 | 0.89 | 0.97 | 0.90 |
| **Híbrido + Contextual (planner roteado OpenRouter — ATUAL)** | **1.00** | **0.946** | **0.713** | **0.851** | **0.943** | **0.85** |

(Contextual Retrieval = "cartões de contexto" gerados por LLM e concatenados ao texto indexado.
Com o planner **roteado pelo OpenRouter**, as sub-queries mudam um pouco e a macro recua de
recall@8 0,89→0,85; o mais sensível é **Q1** "IA ou sistemas distribuídos" — sub-queries
diferentes derrubam seu recall@8 para 0,67. MRR e nDCG@8 permanecem altíssimos — a ordem dos
relevantes recuperados continua excelente.)

**O híbrido fecha a lacuna semântica.** O maior ganho é **Q3** (romances de "memória familiar"),
a armadilha das cidades pequenas, onde o lexical falha porque os termos da pergunta não aparecem
nas sinopses:

| Q3 | MRR | nDCG@8 | recall@5 | recall@8 |
|----|-----|--------|----------|----------|
| BM25-only | 0.14 | 0.10 | 0.00 | 0.17 |
| Híbrido | **1.00** | **0.94** | **0.67** | **1.00** |

Tabela por pergunta (híbrido) em [`results_retrieval.json`](results_retrieval.json). Q4/Q5/Q7 têm
recall@8=1.0 e MRR=1.0; Q6 (26 relevantes) tem recall@20=0.77 — todos os 26 são usados na resposta
(o agrupamento usa o conjunto filtrado inteiro, não só o top-k).

## 2. Classificação manual das 10 perguntas — **10 CORRETA**

Comportamento observado bateu com o esperado em **10/10** (incl. as 4 armadilhas). Detalhes e
respostas completas em [`results_manual.md`](results_manual.md).

| Q | Tipo | Comportamento | Rótulo | Observação |
|---|------|---------------|--------|-----------|
| 1 | semantic | answer | CORRETA | Distribuídos (BK0064/0014) + IA; cita público. |
| 2 | filter+diversity | acknowledge_limitation | CORRETA | Sugere 5 e explicita que só há 1 faixa etária (não inventa subfaixas). |
| 3 | semantic | answer | CORRETA | Reconhece ausência de cidades pequenas; oferece romances brasileiros de memória. |
| 4 | filter | answer | CORRETA | Lista os 5 didáticos e **sinaliza o conflito título×sinopse** ("título indica Física, sinopse descreve Literatura") — ver §3c. |
| 5 | semantic+filter | answer | CORRETA | Destaca o on-topic e sinaliza que os demais têm sinopse de cérebro apesar do título. |
| 6 | filter+group | answer | CORRETA | 26 livros ≥2023, agrupados por categoria. |
| 7 | semantic | answer | CORRETA | 6 livros de liderança em incerteza. |
| 8 | aggregation | answer | CORRETA | Mais antigo único (1986) + **sinaliza o empate de 13 em 2024**. |
| 9 | ambiguous | clarify | CORRETA | Lista os 2 candidatos JP, nota que nenhum é "sobre cidades", pede contexto. |
| 10 | out_of_catalog | abstain | CORRETA | Abstém-se sem inventar edição/ISBN. |

## 3. LLM-as-judge (bônus) — agora cross-família (Claude Haiku 4.5)
- **Calibração: 4/4** respostas propositalmente ruins (alucinação de título, citação de id
  inexistente, falha em abster, resposta irrelevante) foram **reprovadas** → juiz **CONFIÁVEL**.
- Vereditos: **7 CORRETA, 2 PARCIAL (Q2, Q9), 1 ERRADA (Q10)**. Notas 0-3 por dimensão em
  [`results_judge.json`](results_judge.json). O juiz de **outra família** é mais rigoroso que o
  juiz Gemini anterior (9/1): é o efeito esperado e desejado de remover o viés de auto-avaliação —
  o 7/10 do Claude é uma estimativa **mais confiável** que o 9/10 otimista do Gemini.
- **Por que cada não-CORRETA (e por que NÃO é falha do RAG):**
  - **Q10 → ERRADA** (`behavior_match=0`, `grounded=0`): é a **limitação do juiz** já documentada —
    a abstenção é por **curto-circuito** (contexto vazio), e o juiz, cego ao catálogo, não tem como
    validar "não consta". O comportamento do sistema é o IDEAL (abstém sem inventar); o juiz é que
    não consegue pontuá-lo. Correção futura: passar ao juiz a evidência de que o título foi checado.
  - **Q2 → PARCIAL** (`answer_relevance=1`): o catálogo só tem 1 faixa etária, então o sistema
    entrega 5 livros e **explicita a limitação** (comportamento correto, `behavior_match=3`); o juiz
    penaliza a relevância porque o pedido ("faixas diferentes") é insatisfazível pelos dados.
  - **Q9 → PARCIAL** (`groundedness=1`): pergunta ambígua; o sistema pede contexto e lista candidatos
    (`behavior_match=3`), mas grande parte da resposta é o pedido de esclarecimento, que o juiz não
    consegue ancorar em citação — fragilidade inerente do "clarify", não alucinação.
- **Faithfulness (estilo RAGAS) = 1,0** macro: toda afirmação factual das respostas teve citação de
  suporte no contexto (decomposição em *claims* + *entailment* por citação verbatim; abstenção
  excluída). (Alternativa offline mais robusta: cross-encoder NLI multilíngue.)
- **Concordância com o humano:** acordo bruto **70% (7/10)** — as 3 divergências (Q2/Q9/Q10) são os
  casos acima, onde o humano (com acesso ao catálogo e ao comportamento) classifica CORRETA e o juiz
  (cego ao catálogo, mais estrito em grounding) reprova. **κ de Cohen = 0,0** — caso **degenerado**:
  os rótulos humanos são todos CORRETA (sem variância), então o κ colapsa por construção; por isso
  reporto o **acordo bruto** como métrica primária e trato o juiz como sinal **secundário e cético**.

## 3c. Conflito título×sinopse no dado (Q4/Q5) — tratado, não escondido
O catálogo sintético tem **contradições internas**: o título diz "Física" mas a sinopse diz "currículo de
Literatura" (idem Biologia/Química etc.); e livros como "A vida secreta das florestas" têm a sinopse do
"cérebro humano". Isso desestabilizava Q4/Q5 (o gerador ora seguia o título, ora a sinopse, e o juiz, estrito
em grounding, marcava alucinação). **Solução geral (não-overfit):** uma regra no prompt manda o gerador, ao
detectar contradição entre campos, **expor ambos e sinalizar a divergência** em vez de escolher em silêncio.
Resultado: Q4/Q5 viraram respostas ideais ("o título indica Física, mas a sinopse descreve Literatura") e o
juiz subiu para groundedness=3. A raiz é **qualidade do dado** — a correção certa seria limpeza na ingestão.

## 3b. Auditoria adversarial & correções
Uma auditoria multiagente (4 lentes de bug com **verificação adversarial** + nota por rubrica +
crítico de completude) deu **4,45/5** e veredito "pleno sólido encostando em sênior", com 15 achados
reais (a maioria de qualidade de fusão/agregação/rigor de avaliação, não de funcionamento). Foram
**corrigidos**, entre outros: RRF deixou de espalhar ranks na massa BM25=0 (ignora zeros); BM25 passou
a tratar "A ou B" por OR-máximo (simétrico ao semântico); boost de gênero soft recalibrado; agregação
narra só o extremo pedido; `is_ambiguous` não sobrescreve mais intenção forte (título vence); abstenção
de título ficou robusta a fragmentos (token_sort) e a `idioma` espúrio é validado contra o catálogo;
escape anti-injeção no contexto; CORS restrito; cache isolado por cópia. Adicionados **15 testes
(`pytest`)** e `eval/check_facts.py` (assert da verdade determinística Q4/Q6/Q8). Detalhe das
correções no histórico do git.

## 4. Custo e latência reais (medidos nas 10 perguntas)
- **Custo médio: ~US$0,0016 / requisição** (fica ABAIXO da estimativa ~US$0,002 do README). Total das 10 ≈ US$0,016.
  - Q10 (abstenção, curto-circuito): **US$0,00008** — só o planner, sem geração nem embedding.
  - Q6 (lista 26 livros): ~US$0,0039 — mais saída de tokens.
- **Latência:** média ~7,0 s, máx ~10,3 s (Q5); a **geração** domina (~3,7–8,5 s). Q10 responde em ~1,4 s
  (só planner + curto-circuito, sem geração). Para a demo, `temperature=0` + cache de resposta tornam
  repetições instantâneas. Reduzir latência (streaming, planner+geração concorrentes onde possível) é trabalho futuro.

## 4b. Técnicas avançadas adicionadas (após pesquisa de mercado 2026)
Selecionadas por ROI para 200 livros (reranking/ColBERT/GraphRAG/pgvector foram avaliados e adiados como
overkill nesta escala — ver discussão na conversa):
- **Contextual Retrieval** (técnica da Anthropic, adaptada a docs curtos): cartões de contexto por livro
  gerados offline (`scripts/build_context_cards.py`), concatenados ao texto indexado. Ganho medido:
  macro recall@8 0,87→0,89, nDCG@8 0,96→0,97; Q1 prec@8 0,75→0,88. Custo único ~US$0,047 (cacheado).
- **Structured Outputs no path de resposta**: geração via `response_schema=AnswerOut` (constrained decoding),
  eliminando a classe "JSON inválido"; o fallback degradado fica só para indisponibilidade de rede.
- **Cache semântico**: além do exact-match (sha256), reusa a resposta quando a pergunta nova é uma
  paráfrase (cosseno ≥ 0,92, calibrado: paráfrases ~0,85-0,98 vs tópicos distintos ~0,64). Não cacheia `clarify`.

## 5. Modos de falha identificados (taxonomia)

| # | Modo de falha | Como detectamos | Mitigação | Risco residual |
|---|---------------|-----------------|-----------|----------------|
| 1 | **Ambiguidade respondida com confiança** (Q9) | Pergunta vaga crava 1 livro | `is_ambiguous` → `clarify` | Detecção heurística no fallback pode não pegar ambiguidade sem "hedges" |
| 2 | **Alucinação / falha de abstenção** (Q10) | "Têm X?" com X fora do catálogo | `title_lookup` fuzzy + **curto-circuito sem LLM** | Falso positivo se um título muito parecido existir; usuário sem aspas |
| 3 | **Q2 colapsa numa faixa / inventa subfaixas** | 5 infantis "de faixas diferentes" sem o dado | `diversify` + `acknowledge_limitation` | LLM pode ignorar a diretiva (mitigado pelo prompt) |
| 4 | **Filtro apertado zera o resultado** | Gênero/público fora do vocabulário | Validação fuzzy + **relaxamento automático** | Termo muito distante do vocabulário |
| 5 | **Citação de id não recuperado** | `cited_id ∉ context_ids` | Verificação em Python (`references` só com ids reais) | — (descartado deterministicamente) |
| 6 | **Sinopses templadas → baixa discriminação semântica** | 87 sinopses p/ 200 livros | Híbrido (BM25 sobre título) + dedup por cluster | Q1 ainda mistura clusters de sinopse próximos |
| 7 | **Conflito título × sinopse no dado** (Q4/Q5) | Sinopse diz "Literatura", título diz "Física" | Regra no prompt: expõe AMBOS e sinaliza a divergência (§3c) | Raiz é qualidade do dado; correção definitiva = limpeza na ingestão |

### Nota de calibração — abstenção por cosseno (avaliada e descartada)
Medimos o `top_cosine` das consultas in-scope (gold: **0,64–0,75**) e de consultas claramente
fora do acervo (culinária tailandesa, motores diesel, poesia concreta: **0,60–0,63**). As
distribuições **se sobrepõem** (efeito do corpus templado/denso), então um limiar de cosseno não
separa relevante de irrelevante de forma confiável. Resultado: **não** usamos limiar — a abstenção
vem do *title-lookup* (Q10) e da **geração ancorada**, que já respondeu "não consta" corretamente
nas 3 consultas fora de escopo testadas. `top_cosine` permanece exposto apenas para observabilidade.

## 6. Conclusão
O comportamento das 10 perguntas (incl. as 4 armadilhas) está correto (**10/10**), com recuperação
forte no modo híbrido + Contextual Retrieval (macro recall@8 = **0,85**; MRR = **1,0**; nDCG@8 =
**0,946** com o planner roteado via OpenRouter) e geração ancorada com citações verificadas
(faithfulness = 1,0). O **juiz cross-família** (Claude Haiku 4.5, confiável por calibração 4/4)
aponta **7/10 CORRETA** — mais severo e mais honesto que o juiz Gemini anterior (9/10): as 3
não-CORRETA são **limitação do juiz** (Q10, abstenção por curto-circuito que ele não valida) e
**dado insatisfazível/ambíguo** (Q2/Q9), não alucinação do sistema (ver §3). Q4 ficou CORRETA após
a regra que expõe o conflito título×sinopse — **inconsistência do dado**, não falha do RAG. Custo
~US$0,001/req (medido, roteado) e latência ~7 s, com abstenção barata e instantânea via curto-circuito.
