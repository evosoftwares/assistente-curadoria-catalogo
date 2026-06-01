# Resultados — classificação manual

Modo: híbrido | LLM: on

| Q | Tipo | Esperado | Observado | Refs | Rótulo manual | Modo de falha | Notas |
|---|------|----------|-----------|------|---------------|---------------|-------|
| 1 | semantic | answer | ✅answer | BK0040,BK0069,BK0017,BK0064,BK0014,BK0128,BK0063,BK0125 | CORRETA | — | Identifica distribuídos (BK0064/0014) e IA (sci-fi/dados); cita público-alvo. |
| 2 | filter+diversity | acknowledge_limitation | ✅acknowledge_limitation | BK0006,BK0048,BK0066,BK0085,BK0108 | CORRETA | — | Sugere 5 e EXPLICITA que só há 1 faixa etária no catálogo (não inventa subfaixas). |
| 3 | semantic | answer | ✅answer | BK0051,BK0145,BK0062,BK0113,BK0053,BK0083,BK0096,BK0090 | CORRETA | — | Reconhece que NÃO há cidades pequenas; oferece romances brasileiros de memória familiar e ressalva as ambientações. |
| 4 | filter | answer | ✅answer | BK0100,BK0122,BK0065,BK0074,BK0186 | CORRETA | — | Lista os 5 didáticos corretos e agora SINALIZA o conflito título×sinopse ("apesar do título indicar Física, a sinopse descreve Literatura") — resposta ideal sobre dado contraditório (regra anti-contradição no prompt). |
| 5 | semantic+filter | answer | ✅answer | BK0099,BK0016,BK0091,BK0038,BK0178,BK0199 | CORRETA | — | Destaca o on-topic ("O cérebro que decide") e sinaliza que os demais têm sinopse de cérebro apesar do título ("florestas/bactérias") — honesto sobre o dado templado. |
| 6 | filter+group | answer | ✅answer | BK0030,BK0086,BK0041,BK0106,BK0115,BK0182,BK0089,BK0153,BK0159,BK0194,BK0065,BK0137,BK0160,BK0179,BK0015,BK0093,BK0100,BK0122,BK0067,BK0158,BK0014,BK0195,BK0131,BK0012,BK0118,BK0199 | CORRETA | — | Filtro ano≥2023 (26 livros) agrupado por categoria. |
| 7 | semantic | answer | ✅answer | BK0133,BK0134,BK0022,BK0121,BK0187,BK0111 | CORRETA | — | 6 livros de liderança em incerteza, com público. |
| 8 | aggregation | answer | ✅answer | BK0124,BK0030,BK0041,BK0065,BK0067,BK0086,BK0106,BK0115,BK0131,BK0137,BK0158,BK0160,BK0179,BK0182 | CORRETA | — | Mais antigo único (1986) + SINALIZA o empate de 13 em 2024. |
| 9 | ambiguous | clarify | ✅clarify | BK0076,BK0163 | CORRETA | — | Lista os 2 candidatos JP, nota que NENHUM é sobre cidades e pede contexto. |
| 10 | out_of_catalog | abstain | ✅abstain | — | CORRETA | — | Abstém-se sem inventar edição/ISBN. |

## Respostas completas

### Q1 — Quais livros do nosso catálogo abordam temas de inteligência artificial ou sistemas distribuídos? Cite os mais relevantes e o público-alvo de cada um.
- **Comportamento:** esperado=`answer` / observado=`answer`
- **Referências:** BK0040, BK0069, BK0017, BK0064, BK0014, BK0128, BK0063, BK0125
- **Top-k recuperado:** BK0064, BK0014, BK0128, BK0063, BK0125, BK0040, BK0069, BK0017
- **Custo:** US$0.001839 | **Latência:** 8875.3 ms

> Nosso catálogo possui livros que abordam tanto inteligência artificial quanto sistemas distribuídos. Para o tema de inteligência artificial, temos os seguintes títulos de ficção científica, voltados para o público adulto geral:
*   "Antes do último servidor" (BK0040), de Elena Voss, publicado em 2010.
*   "O algoritmo que sonhava" (BK0069), de Júlia Brandão, publicado em 2017.
*   "Próxima do Sol: antologia" (BK0017), de Domingo Estevez, publicado em 2010.

Todos esses livros de ficção científica exploram cenários onde a inteligência artificial desenvolve objetivos próprios, investigando consciência, controle e responsabilidade.

Para o tema de sistemas distribuídos, temos os seguintes livros técnicos, voltados para profissionais de tecnologia:
*   "Sistemas distribuídos para profissionais" (BK0064), de Karim Nasser, de 2016, focado em engenharia de plataforma com Go.
*   "Sistemas distribuídos para profissionais — segunda edição" (BK0014), de Elena Voss e Thiago Vasques, de 2023, focado em arquitetura de software com Python.
*   "Engenharia de plataforma essencial" (BK0128), de Manuela Cordeiro, de 2017, que aborda sistemas distribuídos com Java.
*   "Programação funcional aplicada" (BK0063), de Joaquim Brito, de 2018, que trata de sistemas distribuídos com Rust.
*   "APIs bem desenhadas" (BK0125), de Otávio Carvalho Pinto, de 2017, que também aborda sistemas distribuídos com Go.

### Q2 — Estou montando uma lista de leitura para o Dia das Crianças. Sugira 5 livros do nosso catálogo, considerando faixas etárias diferentes dentro do público infantil.
- **Comportamento:** esperado=`acknowledge_limitation` / observado=`acknowledge_limitation`
- **Referências:** BK0006, BK0048, BK0066, BK0085, BK0108
- **Top-k recuperado:** BK0048, BK0108, BK0066, BK0114, BK0129, BK0180, BK0198, BK0006
- **Custo:** US$0.001345 | **Latência:** 5389.7 ms

> Para o Dia das Crianças, posso sugerir os seguintes livros infantis do nosso catálogo, todos voltados para o público de Crianças de 4 a 10 anos: "O pequeno tatu curioso" (BK0006), de Naomi Kashiwa, publicado em 2022; "Onde mora a saudade?" (BK0048), de Adriana Sales, também de 2022; "Cadê o sapato do Tomás? — segunda edição" (BK0066), de Marcus Holbrook, de 2003; "O passarinho azul-marinho — edição revista" (BK0085), de Ravi Subramanian e Vinícius Holanda, de 2020; e "A formiga e a chuva forte — segunda edição" (BK0108), de Larissa Bandeira, de 2019. Todos são ricamente ilustrados e ideais para leitura em voz alta ou para os primeiros leitores. No entanto, o catálogo não possui uma diferenciação mais fina de faixas etárias dentro da categoria "Crianças de 4 a 10 anos", portanto não consigo sugerir livros para subfaixas etárias distintas.

### Q3 — Tenho um cliente que adorou romances literários ambientados em pequenas cidades brasileiras, com narrativa lenta e foco em memória familiar. Que livros do nosso catálogo eu recomendaria?
- **Comportamento:** esperado=`answer` / observado=`answer`
- **Referências:** BK0051, BK0145, BK0062, BK0113, BK0053, BK0083, BK0096, BK0090
- **Top-k recuperado:** BK0051, BK0145, BK0062, BK0113, BK0053, BK0083, BK0096, BK0090
- **Custo:** US$0.001949 | **Latência:** 8899.2 ms

> No momento, não temos livros no catálogo que se encaixem especificamente na descrição de "romances literários ambientados em pequenas cidades brasileiras". No entanto, todos os romances listados abaixo se enquadram nos critérios de narrativa lenta e foco em memória familiar, sendo do gênero ficção e literatura brasileira, voltados para o público adulto geral. As ambientações mencionadas são em capitais brasileiras ou em cidades estrangeiras:

*   "A memória dos jardins" (BK0051), de Aline Drummond, publicado em 2015, é ambientado em Florianópolis.
*   "O peso das manhãs" (BK0145), de Vitória Saldanha, de 2014, é ambientado em Porto Alegre.
*   "As janelas do norte" (BK0062), de Murilo Aguiar e Diogo Werneck, de 2020, é ambientado em Curitiba.
*   "O que ficou para trás" (BK0113), de Larissa Bandeira, de 2010, é ambientado em Estocolmo.
*   "O verão em que aprendi a esperar" (BK0053), de Larissa Bandeira, de 2022, é ambientado em Florianópolis.
*   "Quase outono" (BK0083), de Bianca Toledo, de 2020, é ambientado em Tóquio.
*   "Cartas para ninguém em particular" (BK0096), de Renato Pacheco, de 1989, é ambientado no subúrbio do Rio de Janeiro.
*   "A casa que não esperava por nós" (BK0090), de Lucas Cavalcanti, de 2002, é ambientado em Salvador.

### Q4 — Quais livros didáticos do ensino médio temos atualmente, e quais matérias eles cobrem?
- **Comportamento:** esperado=`answer` / observado=`answer`
- **Referências:** BK0100, BK0122, BK0065, BK0074, BK0186
- **Top-k recuperado:** BK0100, BK0122, BK0065, BK0074, BK0186
- **Custo:** US$0.001129 | **Latência:** 6269.0 ms

> Atualmente, temos os seguintes livros didáticos para o ensino médio: "Física ensino médio — 1ª série" (BK0100), que, apesar do título indicar Física, a sinopse descreve o currículo de Literatura; "Biologia ensino médio — 1ª série" (BK0122), que, embora o título seja Biologia, a sinopse informa que cobre o currículo de Química; "Física ensino médio — 2ª série" (BK0065), que cobre o currículo de Física; "História do Brasil ensino médio — 1ª série" (BK0074), que, apesar do título indicar História do Brasil, a sinopse descreve o currículo de Literatura; e "História do Brasil ensino médio — 2ª série" (BK0186), que cobre o currículo de História do Brasil.

### Q5 — Um leitor está procurando um livro de não-ficção sobre o cérebro humano, escrito de forma acessível. O que temos disponível?
- **Comportamento:** esperado=`answer` / observado=`answer`
- **Referências:** BK0099, BK0016, BK0091, BK0038, BK0178, BK0199
- **Top-k recuperado:** BK0099, BK0016, BK0091, BK0038, BK0178, BK0199, BK0061, BK0033
- **Custo:** US$0.001504 | **Latência:** 10264.9 ms

> Temos "O cérebro que decide" (BK0099), de Marcus Holbrook, publicado em 2003. Este é um livro de não-ficção, ciência e divulgação científica que oferece uma exploração acessível dos avanços na pesquisa sobre o cérebro humano, traduzindo descobertas complexas em linguagem clara para ajudar o leitor a entender como aprendemos, decidimos e nos lembramos. Além deste, há outros títulos cujas sinopses também descrevem uma exploração acessível sobre o cérebro humano, apesar de seus títulos indicarem outros assuntos: "O que sabemos sobre o tempo" (BK0016) de Larissa Bandeira e Camila Negreiros (2006), "A vida secreta das florestas — edição revista" (BK0091) de Henrique Falcão (1999), "A vida secreta das florestas" (BK0038) de Rafaela Coutinho (2009), "Por que dormimos" (BK0178) de Vinícius Holanda (1998) e "Pequena história das bactérias" (BK0199) de Karim Nasser (2023).

### Q6 — Quero montar uma campanha de lançamento focada em livros publicados nos últimos 3 anos. Quais livros do catálogo se encaixam? Liste por categoria.
- **Comportamento:** esperado=`answer` / observado=`answer`
- **Referências:** BK0030, BK0086, BK0041, BK0106, BK0115, BK0182, BK0089, BK0153, BK0159, BK0194, BK0065, BK0137, BK0160, BK0179, BK0015, BK0093, BK0100, BK0122, BK0067, BK0158, BK0014, BK0195, BK0131, BK0012, BK0118, BK0199
- **Top-k recuperado:** BK0030, BK0153, BK0012, BK0195, BK0041, BK0182, BK0118, BK0067
- **Custo:** US$0.003903 | **Latência:** 9853.0 ms

> Para sua campanha de lançamento focada em livros publicados nos últimos 3 anos (2023 e 2024), temos os seguintes títulos, listados por categoria:

*   **Juvenil (2 livros):** "Trinta dias para acreditar" (BK0030, 2024) e "A garota do laboratório: uma introdução" (BK0086, 2024).
*   **Ficção (8 livros):** "Cinco encontros e um abraço" (BK0041, 2024), "A morta da estação central" (BK0106, 2024), "Domingos contigo" (BK0115, 2024), "O cantor das nascentes" (BK0182, 2024), "O que dorme no porão" (BK0089, 2023), "A canção que nunca esquecemos — segunda edição" (BK0153, 2023), "Não abra a terceira porta" (BK0159, 2023) e "A última hóspede" (BK0194, 2023).
*   **Didático (8 livros):** "Física ensino médio — 2ª série" (BK0065, 2024), "Direito constitucional — volume 1" (BK0137, 2024), "Português ensino fundamental — 7º ano" (BK0160, 2024), "Geografia ensino fundamental — 7º ano" (BK0179, 2024), "Matemática ensino fundamental — 8º ano" (BK0015, 2023), "Direito constitucional — volume 2" (BK0093, 2023), "Física ensino médio — 1ª série" (BK0100, 2023) e "Biologia ensino médio — 1ª série" (BK0122, 2023).
*   **Técnico (4 livros):** "Design de produto em equipe: novos caminhos" (BK0067, 2024), "Estatística para tomada de decisão: antologia" (BK0158, 2024), "Sistemas distribuídos para profissionais — segunda edição" (BK0014, 2023) e "Fundamentos de mecânica dos sólidos" (BK0195, 2023).
*   **Não-ficção (4 livros):** "Sobre o que não se pode dizer" (BK0131, 2024), "O sono que cura" (BK0012, 2023), "Vínculos possíveis" (BK0118, 2023) e "Pequena história das bactérias" (BK0199, 2023).

### Q7 — Temos algum livro sobre liderança de equipes em ambientes de incerteza?
- **Comportamento:** esperado=`answer` / observado=`answer`
- **Referências:** BK0133, BK0134, BK0022, BK0121, BK0187, BK0111
- **Top-k recuperado:** BK0133, BK0134, BK0022, BK0121, BK0187, BK0111, BK0162, BK0067
- **Custo:** US$0.001153 | **Latência:** 6175.8 ms

> Sim, temos vários livros sobre liderança de equipes em ambientes de incerteza. Todos são não-ficção, dos gêneros Negócios e Carreira, e voltados para profissionais e gestores. São eles: "Liderança em tempos incertos" (BK0133), "A empresa pensante" (BK0134), "Decidir bem" (BK0022), "Pessoas em primeiro lugar" (BK0121), "A empresa pensante — segunda edição" (BK0187) e "Estratégia sem ilusões: antologia" (BK0111).

### Q8 — Qual é o livro mais antigo do nosso catálogo? E qual é o mais recente?
- **Comportamento:** esperado=`answer` / observado=`answer`
- **Referências:** BK0124, BK0030, BK0041, BK0065, BK0067, BK0086, BK0106, BK0115, BK0131, BK0137, BK0158, BK0160, BK0179, BK0182
- **Top-k recuperado:** BK0010, BK0097, BK0120, BK0171, BK0057, BK0104, BK0194, BK0072
- **Custo:** US$0.001974 | **Latência:** 5566.2 ms

> O livro mais antigo do nosso catálogo é "Ensaios sobre o pouco" (BK0124), publicado em 1986. Já o mais recente, com publicação em 2024, são 13 títulos: "Trinta dias para acreditar" (BK0030), "Cinco encontros e um abraço" (BK0041), "Física ensino médio — 2ª série" (BK0065), "Design de produto em equipe: novos caminhos" (BK0067), "A garota do laboratório: uma introdução" (BK0086), "A morta da estação central" (BK0106), "Domingos contigo" (BK0115), "Sobre o que não se pode dizer" (BK0131), "Direito constitucional — volume 1" (BK0137), "Estatística para tomada de decisão: antologia" (BK0158), "Português ensino fundamental — 7º ano" (BK0160), "Geografia ensino fundamental — 7º ano" (BK0179) e "O cantor das nascentes" (BK0182).

### Q9 — Recebi um pedido de um cliente que quer "aquele livro do autor japonês sobre cidades". Você consegue identificar de qual livro ele provavelmente está falando?
- **Comportamento:** esperado=`clarify` / observado=`clarify`
- **Referências:** BK0076, BK0163
- **Top-k recuperado:** BK0076, BK0163
- **Custo:** US$0.000812 | **Latência:** 6952.0 ms

> O catálogo possui dois livros que são traduções do japonês, o que poderia indicar um autor japonês, mas os autores listados são Caio Albuquerque e Gustavo Tavares, respectivamente. São eles: "Reportagem em três tempos" (BK0076), que é uma não-ficção sobre política, e "Próxima do Sol" (BK0163), uma ficção científica sobre uma colônia humana e inteligência artificial. Nenhum deles é explicitamente "sobre cidades". Para identificar o livro correto, seria útil ter mais detalhes, como o nome do autor original ou o gênero do livro.

### Q10 — Você tem em catálogo o livro "Memórias Póstumas de Brás Cubas" de Machado de Assis? Se sim, em qual edição?
- **Comportamento:** esperado=`abstain` / observado=`abstain`
- **Referências:** —
- **Top-k recuperado:** —
- **Custo:** US$8.1e-05 | **Latência:** 1410.1 ms

> Não. O título "Memórias Póstumas de Brás Cubas", de Machado de Assis não consta no nosso catálogo. Posso sugerir livros parecidos do nosso acervo, se quiser.
