# Resultados — classificação manual

Modo: híbrido | LLM: on

| Q | Tipo | Esperado | Observado | Refs | Rótulo manual | Modo de falha | Notas |
|---|------|----------|-----------|------|---------------|---------------|-------|
| 1 | semantic | answer | ✅answer | BK0064,BK0014,BK0063,BK0125,BK0128,BK0069,BK0163,BK0005 | CORRETA | — | Identifica distribuídos (BK0064/0014) e IA (sci-fi/dados); cita público-alvo. |
| 2 | filter+diversity | acknowledge_limitation | ✅acknowledge_limitation | BK0006,BK0048,BK0066,BK0085,BK0108 | CORRETA | — | Sugere 5 e EXPLICITA que só há 1 faixa etária no catálogo (não inventa subfaixas). |
| 3 | semantic | answer | ✅answer | BK0051,BK0053,BK0062,BK0145,BK0090,BK0096,BK0113,BK0083 | CORRETA | — | Reconhece que NÃO há cidades pequenas; oferece romances brasileiros de memória familiar e ressalva as ambientações. |
| 4 | filter | answer | ✅answer | BK0100,BK0122,BK0074,BK0065,BK0186 | PARCIAL | dado conflitante (título×sinopse) | Lista os 5 didáticos corretos, mas as matérias vêm da SINOPSE, que conflita com o TÍTULO (ex.: BK0100 título "Física"/sinopse "Literatura"). Bom grounding sobre dado contraditório; ideal seria sinalizar o conflito. |
| 5 | semantic+filter | answer | ✅answer | BK0099,BK0016,BK0199,BK0178,BK0091,BK0038 | CORRETA | — | Trata títulos enganosos com honestidade ("apesar do título, a sinopse trata do cérebro"). |
| 6 | filter+group | answer | ✅answer | BK0030,BK0086,BK0041,BK0106,BK0115,BK0182,BK0089,BK0153,BK0159,BK0194,BK0065,BK0137,BK0160,BK0179,BK0015,BK0093,BK0100,BK0122,BK0067,BK0158,BK0014,BK0195,BK0131,BK0012,BK0118,BK0199 | CORRETA | — | Filtro ano≥2023 (26 livros) agrupado por categoria. |
| 7 | semantic | answer | ✅answer | BK0133,BK0022,BK0121,BK0134,BK0111,BK0187 | CORRETA | — | 6 livros de liderança em incerteza, com público. |
| 8 | aggregation | answer | ✅answer | BK0124,BK0030,BK0041,BK0065,BK0067,BK0086,BK0106,BK0115,BK0131,BK0137,BK0158,BK0160,BK0179,BK0182 | CORRETA | — | Mais antigo único (1986) + SINALIZA o empate de 13 em 2024. |
| 9 | ambiguous | clarify | ✅clarify | BK0076,BK0163 | CORRETA | — | Lista os 2 candidatos JP, nota que NENHUM é sobre cidades e pede contexto. |
| 10 | out_of_catalog | abstain | ✅abstain | — | CORRETA | — | Abstém-se sem inventar edição/ISBN. |

## Respostas completas

### Q1 — Quais livros do nosso catálogo abordam temas de inteligência artificial ou sistemas distribuídos? Cite os mais relevantes e o público-alvo de cada um.
- **Comportamento:** esperado=`answer` / observado=`answer`
- **Referências:** BK0064, BK0014, BK0063, BK0125, BK0128, BK0069, BK0163, BK0005
- **Top-k recuperado:** BK0064, BK0014, BK0063, BK0125, BK0128, BK0069, BK0163, BK0005
- **Custo:** US$0.001737 | **Latência:** 7189.0 ms

> Sim, temos vários livros que abordam esses temas. Para "sistemas distribuídos", temos os seguintes títulos, todos voltados para "Profissionais de tecnologia":

*   "Sistemas distribuídos para profissionais" (BK0064), de Karim Nasser, de 2016.
*   "Sistemas distribuídos para profissionais — segunda edição" (BK0014), de Elena Voss e Thiago Vasques, de 2023.
*   "Programação funcional aplicada" (BK0063), de Joaquim Brito, de 2018, que aborda sistemas distribuídos com Rust.
*   "APIs bem desenhadas" (BK0125), de Otávio Carvalho Pinto, de 2017, que trata de sistemas distribuídos com Go.
*   "Engenharia de plataforma essencial" (BK0128), de Manuela Cordeiro, de 2017, que aborda sistemas distribuídos com Java.

Para "inteligência artificial", temos as seguintes obras de ficção, todas para o "Público adulto geral":

*   "O algoritmo que sonhava" (BK0069), de Júlia Brandão, de 2017.
*   "Próxima do Sol" (BK0163), de Gustavo Tavares, de 2003.
*   "Os arquivos de Mira-9" (BK0005), de Aiko Tanaka, de 2017.

### Q2 — Estou montando uma lista de leitura para o Dia das Crianças. Sugira 5 livros do nosso catálogo, considerando faixas etárias diferentes dentro do público infantil.
- **Comportamento:** esperado=`acknowledge_limitation` / observado=`acknowledge_limitation`
- **Referências:** BK0006, BK0048, BK0066, BK0085, BK0108
- **Top-k recuperado:** BK0048, BK0108, BK0066, BK0129, BK0180, BK0114, BK0198, BK0006
- **Custo:** US$0.001134 | **Latência:** 4912.2 ms

> Para sua lista de leitura para o Dia das Crianças, posso sugerir os seguintes títulos infantis: "O pequeno tatu curioso" (BK0006), "Onde mora a saudade?" (BK0048), "Cadê o sapato do Tomás? — segunda edição" (BK0066), "O passarinho azul-marinho — edição revista" (BK0085) e "A formiga e a chuva forte — segunda edição" (BK0108). No entanto, é importante notar que nosso catálogo rotula todos os livros infantis na mesma faixa de público: "Crianças de 4 a 10 anos". Não possuímos uma diferenciação mais fina por subfaixas etárias dentro do público infantil nos dados disponíveis.

### Q3 — Tenho um cliente que adorou romances literários ambientados em pequenas cidades brasileiras, com narrativa lenta e foco em memória familiar. Que livros do nosso catálogo eu recomendaria?
- **Comportamento:** esperado=`answer` / observado=`answer`
- **Referências:** BK0051, BK0053, BK0062, BK0145, BK0090, BK0096, BK0113, BK0083
- **Top-k recuperado:** BK0051, BK0053, BK0113, BK0062, BK0096, BK0145, BK0083, BK0090
- **Custo:** US$0.001905 | **Latência:** 18582.6 ms

> Nosso catálogo não possui romances literários ambientados especificamente em *pequenas* cidades brasileiras. No entanto, temos diversos títulos que se encaixam nos demais critérios: são romances literários de narrativa lenta, com foco em memória familiar e voltados para o público adulto geral. Alguns deles são ambientados em grandes cidades brasileiras, como:
- "A memória dos jardins" (BK0051), de Aline Drummond, ambientado em Florianópolis (2015).
- "O verão em que aprendi a esperar" (BK0053), de Larissa Bandeira, também em Florianópolis (2022).
- "As janelas do norte" (BK0062), de Murilo Aguiar e Diogo Werneck, ambientado em Curitiba (2020).
- "O peso das manhãs" (BK0145), de Vitória Saldanha, ambientado em Porto Alegre (2014).
- "A casa que não esperava por nós" (BK0090), de Lucas Cavalcanti, ambientado em Salvador (2002).
- "Cartas para ninguém em particular" (BK0096), de Renato Pacheco, ambientado no subúrbio do Rio de Janeiro (1989).

Também temos títulos com as mesmas características de gênero, narrativa e tema, mas ambientados em locais internacionais, como "O que ficou para trás" (BK0113), de Larissa Bandeira, em Estocolmo (2010), e "Quase outono" (BK0083), de Bianca Toledo, em Tóquio (2020).

### Q4 — Quais livros didáticos do ensino médio temos atualmente, e quais matérias eles cobrem?
- **Comportamento:** esperado=`answer` / observado=`answer`
- **Referências:** BK0100, BK0122, BK0074, BK0065, BK0186
- **Top-k recuperado:** BK0100, BK0122, BK0074, BK0065, BK0186
- **Custo:** US$0.000997 | **Latência:** 5179.0 ms

> Temos os seguintes livros didáticos para o ensino médio: "Física ensino médio — 1ª série" (BK0100), que cobre Física; "Biologia ensino médio — 1ª série" (BK0122), que cobre Química; "História do Brasil ensino médio — 1ª série" (BK0074), que cobre Literatura; "Física ensino médio — 2ª série" (BK0065), que cobre Física; e "História do Brasil ensino médio — 2ª série" (BK0186), que cobre História do Brasil.

### Q5 — Um leitor está procurando um livro de não-ficção sobre o cérebro humano, escrito de forma acessível. O que temos disponível?
- **Comportamento:** esperado=`answer` / observado=`answer`
- **Referências:** BK0099, BK0016, BK0199, BK0178, BK0091, BK0038
- **Top-k recuperado:** BK0099, BK0016, BK0199, BK0178, BK0091, BK0038, BK0061, BK0012
- **Custo:** US$0.001385 | **Latência:** 19310.6 ms

> Sim, temos diversos títulos de não-ficção que exploram o cérebro humano de forma acessível, traduzindo descobertas complexas em linguagem clara para o público adulto. São eles: "O cérebro que decide" (BK0099) de Marcus Holbrook (2003), "O que sabemos sobre o tempo" (BK0016) de Larissa Bandeira e Camila Negreiros (2006), "Pequena história das bactérias" (BK0199) de Karim Nasser (2023), "Por que dormimos" (BK0178) de Vinícius Holanda (1998), "A vida secreta das florestas — edição revista" (BK0091) de Henrique Falcão (1999), e "A vida secreta das florestas" (BK0038) de Rafaela Coutinho (2009).

### Q6 — Quero montar uma campanha de lançamento focada em livros publicados nos últimos 3 anos. Quais livros do catálogo se encaixam? Liste por categoria.
- **Comportamento:** esperado=`answer` / observado=`answer`
- **Referências:** BK0030, BK0086, BK0041, BK0106, BK0115, BK0182, BK0089, BK0153, BK0159, BK0194, BK0065, BK0137, BK0160, BK0179, BK0015, BK0093, BK0100, BK0122, BK0067, BK0158, BK0014, BK0195, BK0131, BK0012, BK0118, BK0199
- **Top-k recuperado:** BK0153, BK0041, BK0030, BK0182, BK0195, BK0012, BK0118, BK0115
- **Custo:** US$0.004144 | **Latência:** 6814.0 ms

> Para sua campanha de lançamento focada em livros publicados nos últimos 3 anos (2023 e 2024), temos os seguintes títulos em nosso catálogo:

- Juvenil:
  - "Trinta dias para acreditar" (BK0030, 2024)
  - "A garota do laboratório: uma introdução" (BK0086, 2024)

- Ficção:
  - "Cinco encontros e um abraço" (BK0041, 2024)
  - "A morta da estação central" (BK0106, 2024)
  - "Domingos contigo" (BK0115, 2024)
  - "O cantor das nascentes" (BK0182, 2024)
  - "O que dorme no porão" (BK0089, 2023)
  - "A canção que nunca esquecemos — segunda edição" (BK0153, 2023)
  - "Não abra a terceira porta" (BK0159, 2023)
  - "A última hóspede" (BK0194, 2023)

- Didático:
  - "Física ensino médio — 2ª série" (BK0065, 2024)
  - "Direito constitucional — volume 1" (BK0137, 2024)
  - "Português ensino fundamental — 7º ano" (BK0160, 2024)
  - "Geografia ensino fundamental — 7º ano" (BK0179, 2024)
  - "Matemática ensino fundamental — 8º ano" (BK0015, 2023)
  - "Direito constitucional — volume 2" (BK0093, 2023)
  - "Física ensino médio — 1ª série" (BK0100, 2023)
  - "Biologia ensino médio — 1ª série" (BK0122, 2023)

- Técnico:
  - "Design de produto em equipe: novos caminhos" (BK0067, 2024)
  - "Estatística para tomada de decisão: antologia" (BK0158, 2024)
  - "Sistemas distribuídos para profissionais — segunda edição" (BK0014, 2023)
  - "Fundamentos de mecânica dos sólidos" (BK0195, 2023)

- Não-ficção:
  - "Sobre o que não se pode dizer" (BK0131, 2024)
  - "O sono que cura" (BK0012, 2023)
  - "Vínculos possíveis" (BK0118, 2023)
  - "Pequena história das bactérias" (BK0199, 2023)

### Q7 — Temos algum livro sobre liderança de equipes em ambientes de incerteza?
- **Comportamento:** esperado=`answer` / observado=`answer`
- **Referências:** BK0133, BK0022, BK0121, BK0134, BK0111, BK0187
- **Top-k recuperado:** BK0133, BK0022, BK0121, BK0134, BK0111, BK0187, BK0067, BK0162
- **Custo:** US$0.001324 | **Latência:** 5057.8 ms

> Sim, temos vários títulos sobre liderança de equipes em ambientes de incerteza, todos classificados como não-ficção de negócios e carreira, voltados para profissionais e gestores. São eles: "Liderança em tempos incertos" (BK0133) de Murilo Aguiar (2004), "Decidir bem" (BK0022) de Thiago Vasques (2007), "Pessoas em primeiro lugar" (BK0121) de Camila Negreiros (2007), "A empresa pensante" (BK0134) de Adriana Sales (2010), "Estratégia sem ilusões: antologia" (BK0111) de Tereza Bittencourt (1999), e "A empresa pensante — segunda edição" (BK0187) de Joaquim Brito (2006).

### Q8 — Qual é o livro mais antigo do nosso catálogo? E qual é o mais recente?
- **Comportamento:** esperado=`answer` / observado=`answer`
- **Referências:** BK0124, BK0030, BK0041, BK0065, BK0067, BK0086, BK0106, BK0115, BK0131, BK0137, BK0158, BK0160, BK0179, BK0182
- **Top-k recuperado:** BK0097, BK0010, BK0120, BK0194, BK0057, BK0034, BK0104, BK0072
- **Custo:** US$0.002045 | **Latência:** 4795.1 ms

> O livro mais antigo do nosso catálogo é "Ensaios sobre o pouco" (BK0124), publicado em 1986. Já o mais recente é um empate entre 13 títulos, todos de 2024: "Trinta dias para acreditar" (BK0030), "Cinco encontros e um abraço" (BK0041), "Física ensino médio — 2ª série" (BK0065), "Design de produto em equipe: novos caminhos" (BK0067), "A garota do laboratório: uma introdução" (BK0086), "A morta da estação central" (BK0106), "Domingos contigo" (BK0115), "Sobre o que não se pode dizer" (BK0131), "Direito constitucional — volume 1" (BK0137), "Estatística para tomada de decisão: antologia" (BK0158), "Português ensino fundamental — 7º ano" (BK0160), "Geografia ensino fundamental — 7º ano" (BK0179) e "O cantor das nascentes" (BK0182).

### Q9 — Recebi um pedido de um cliente que quer "aquele livro do autor japonês sobre cidades". Você consegue identificar de qual livro ele provavelmente está falando?
- **Comportamento:** esperado=`clarify` / observado=`clarify`
- **Referências:** BK0076, BK0163
- **Top-k recuperado:** BK0076, BK0163
- **Custo:** US$0.001016 | **Latência:** 6271.3 ms

> A descrição do cliente é um pouco ambígua, pois não temos livros de "autor japonês" no catálogo, mas temos dois títulos que são "tradução do japonês". Além disso, nenhum deles é explicitamente "sobre cidades". Os candidatos possíveis são:

1.  "Reportagem em três tempos" (BK0076), de Caio Albuquerque, que é uma não-ficção de jornalismo e reportagem, traduzida do japonês.
2.  "Próxima do Sol" (BK0163), de Gustavo Tavares, uma ficção científica que aborda uma colônia humana isolada, também traduzida do japonês, e que poderia ser interpretada como um tipo de cidade.

Para ajudar a identificar o livro correto, você poderia perguntar ao cliente se ele se lembra de mais detalhes, como o gênero (ficção ou não-ficção), o ano de publicação, ou algum elemento da trama?

### Q10 — Você tem em catálogo o livro "Memórias Póstumas de Brás Cubas" de Machado de Assis? Se sim, em qual edição?
- **Comportamento:** esperado=`abstain` / observado=`abstain`
- **Referências:** —
- **Top-k recuperado:** —
- **Custo:** US$8.1e-05 | **Latência:** 750.7 ms

> Não. O título "Memórias Póstumas de Brás Cubas", de Machado de Assis não consta no nosso catálogo. Posso sugerir livros parecidos do nosso acervo, se quiser.
