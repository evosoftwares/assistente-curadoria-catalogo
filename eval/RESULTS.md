# Resultados de Avaliação

Três camadas: (1) classificação **manual** das 10 perguntas, (2) **métricas de recuperação**
(recall@k/precision@k/MRR/nDCG, dedup por edição), (3) **LLM-as-judge** cético com calibração.

> Rodado com `gemini-2.5-flash` (geração/juiz), `gemini-2.5-flash-lite` (planner),
> `gemini-embedding-001` (768d). Reproduza com:
> `python scripts/build_index.py && python eval/run_manual.py && python eval/retrieval_metrics.py && python eval/judge.py`

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
| Híbrido (sem.+BM25+RRF) | 1.00 | 0.96 | 0.76 | 0.87 | 0.97 | 0.90 |
| **Híbrido + Contextual Retrieval** | **1.00** | **0.97** | **0.76** | **0.89** | **0.97** | **0.90** |

(Contextual Retrieval = "cartões de contexto" gerados por LLM e concatenados ao texto indexado;
maior ganho em Q1 "IA ou sistemas distribuídos": recall@8 0,67→0,78 e prec@8 0,75→0,88.)

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

## 3. LLM-as-judge (bônus)
- **Calibração: 4/4** respostas propositalmente ruins (alucinação de título, citação de id
  inexistente, falha em abster, resposta irrelevante) foram **reprovadas** → juiz **CONFIÁVEL**.
- Vereditos: **9 CORRETA, 1 PARCIAL** (Q10), com groundedness=3 em Q1-Q8 (Q9=2). Notas 0-3 por dimensão em [`results_judge.json`](results_judge.json).
- **Concordância com o humano:** acordo bruto **90% (9/10)** — a única divergência é Q10. **κ de Cohen = 0,0**,
  porém é um caso **degenerado**: como os rótulos humanos ficaram todos CORRETA (sem variância), o κ colapsa
  por construção mesmo com 90% de acordo. É exatamente a limitação do κ que documentamos — por isso reporto
  o **acordo bruto** como métrica primária. (Antes das melhorias de Q4/Q5 a distribuição era 7/3 e o κ dava 0,41.)
- **Limitação conhecida:** no Q10 o juiz dá `behavior_match=0` porque a abstenção é por
  **curto-circuito** (contexto vazio) — o juiz, cego ao catálogo, não tem como validar "não consta".
  Correção futura: passar ao juiz a evidência de que o título foi checado contra o catálogo inteiro.

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
- **Custo médio: ~US$0,0016 / requisição** (bate com a estimativa ~0,0015 do README). Total das 10 ≈ US$0,016.
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
| 7 | **Conflito título × sinopse no dado** (observado no Q4) | Sinopse diz "Literatura", título diz "Física" | Grounding fiel à sinopse; honestidade sobre a fonte | Resposta herda a inconsistência do dado; ideal seria sinalizar o conflito |

### Nota de calibração — abstenção por cosseno (avaliada e descartada)
Medimos o `top_cosine` das consultas in-scope (gold: **0,64–0,75**) e de consultas claramente
fora do acervo (culinária tailandesa, motores diesel, poesia concreta: **0,60–0,63**). As
distribuições **se sobrepõem** (efeito do corpus templado/denso), então um limiar de cosseno não
separa relevante de irrelevante de forma confiável. Resultado: **não** usamos limiar — a abstenção
vem do *title-lookup* (Q10) e da **geração ancorada**, que já respondeu "não consta" corretamente
nas 3 consultas fora de escopo testadas. `top_cosine` permanece exposto apenas para observabilidade.

## 6. Conclusão
O comportamento das 10 perguntas (incl. as 4 armadilhas) está correto (10/10), com recuperação
forte no modo híbrido + Contextual Retrieval (macro recall@8 = 0,89; MRR = 1,0; nDCG@8 = 0,97) e
geração ancorada com citações verificadas. O juiz confiável aponta 9/10 CORRETA; a única não-CORRETA
é Q10 (PARCIAL — a abstenção por curto-circuito não é validável pelo juiz, cego ao catálogo; ver §3).
Q4 ficou CORRETA (groundedness=3) após a regra que expõe o conflito título×sinopse — **inconsistência
do dado**, não falha do RAG. Custo ~US$0,0015/req e latência ~7 s, com abstenção barata e instantânea
via curto-circuito.
