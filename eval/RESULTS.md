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
| **Híbrido (sem.+BM25+RRF)** | **1.00** | **0.96** | **0.76** | **0.87** | **0.97** | **0.90** |

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

## 2. Classificação manual das 10 perguntas — **9 CORRETA, 1 PARCIAL**

Comportamento observado bateu com o esperado em **10/10** (incl. as 4 armadilhas). Detalhes e
respostas completas em [`results_manual.md`](results_manual.md).

| Q | Tipo | Comportamento | Rótulo | Observação |
|---|------|---------------|--------|-----------|
| 1 | semantic | answer | CORRETA | Distribuídos (BK0064/0014) + IA; cita público. |
| 2 | filter+diversity | acknowledge_limitation | CORRETA | Sugere 5 e explicita que só há 1 faixa etária (não inventa subfaixas). |
| 3 | semantic | answer | CORRETA | Reconhece ausência de cidades pequenas; oferece romances brasileiros de memória. |
| 4 | filter | answer | **PARCIAL** | Lista os 5 didáticos certos, mas as **matérias vêm da sinopse, que conflita com o título** (dado sintético). |
| 5 | semantic+filter | answer | CORRETA | Trata títulos enganosos ("apesar do título, a sinopse trata do cérebro"). |
| 6 | filter+group | answer | CORRETA | 26 livros ≥2023, agrupados por categoria. |
| 7 | semantic | answer | CORRETA | 6 livros de liderança em incerteza. |
| 8 | aggregation | answer | CORRETA | Mais antigo único (1986) + **sinaliza o empate de 13 em 2024**. |
| 9 | ambiguous | clarify | CORRETA | Lista os 2 candidatos JP, nota que nenhum é "sobre cidades", pede contexto. |
| 10 | out_of_catalog | abstain | CORRETA | Abstém-se sem inventar edição/ISBN. |

## 3. LLM-as-judge (bônus)
- **Calibração: 4/4** respostas propositalmente ruins (alucinação de título, citação de id
  inexistente, falha em abster, resposta irrelevante) foram **reprovadas** → juiz **CONFIÁVEL**.
- Vereditos: **8 CORRETA, 2 PARCIAL** (Q5, Q10). Notas 0-3 por dimensão em [`results_judge.json`](results_judge.json).
- **Concordância com o humano:** acordo bruto **7/10 = 70%**, mas **κ de Cohen = −0,15** —
  *negativo por artefato de prevalência* (quase todos os itens são CORRETA, então o acaso esperado
  é altíssimo e κ fica instável). As 3 divergências são todas **CORRETA↔PARCIAL** de fronteira
  (Q4, Q5, Q10), nenhuma catastrófica. **Lição:** com 10 itens e distribuição desbalanceada, κ não
  é a métrica certa; eu usaria acordo bruto + revisão das divergências e um conjunto maior.
- **Limitação descoberta:** no Q10 o juiz deu `behavior_match=0` porque a abstenção é por
  **curto-circuito** (contexto vazio) — o juiz, cego ao catálogo, não tem como validar "não consta".
  Correção: passar ao juiz a evidência de que o título foi checado contra o catálogo inteiro.

## 4. Custo e latência reais (medidos nas 10 perguntas)
- **Custo médio: US$0,0015 / requisição** (bate com a estimativa do README). Total das 10 ≈ US$0,015.
  - Q10 (abstenção, curto-circuito): **US$0,00008** — só o planner, sem geração nem embedding.
  - Q6 (lista 26 livros): US$0,0041 — mais saída de tokens.
- **Latência:** média ~6,7 s, máx ~9,8 s; a **geração** domina (~3,5–7,4 s). Q10 responde em ~0,8 s.
  Para a demo, `temperature=0` + cache de resposta tornam repetições instantâneas. Reduzir latência
  (streaming, planner+geração concorrentes onde possível) é trabalho futuro.

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

## 6. Conclusão
O comportamento das 10 perguntas (incl. as 4 armadilhas) está correto (10/10), com recuperação
forte no modo híbrido (macro recall@8 = 0,87; MRR = 1,0; nDCG@8 = 0,96) e geração ancorada com
citações verificadas. O juiz confiável aponta 8/10 CORRETA; a única falha real de conteúdo (Q4) é
herdada de uma **inconsistência do dado**, não do RAG. Custo ~US$0,0015/req e latência ~7 s, com
abstenção barata e instantânea via curto-circuito.
