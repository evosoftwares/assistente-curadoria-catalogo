# Resultados — classificação manual

Modo: híbrido | LLM: on

| Q | Tipo | Esperado | Observado | Refs | Rótulo manual | Modo de falha | Notas |
|---|------|----------|-----------|------|---------------|---------------|-------|
| 1 | semantic | answer | ✅answer | BK0064,BK0128,BK0125,BK0063,BK0014,BK0126,BK0017,BK0040 | CORRETA | — | Identifica distribuídos (BK0064/0014) e IA (sci-fi/dados); cita público-alvo. |
| 2 | filter+diversity | acknowledge_limitation | ✅acknowledge_limitation | BK0006,BK0048,BK0066,BK0085,BK0108 | CORRETA | — | Sugere 5 e EXPLICITA que só há 1 faixa etária no catálogo (não inventa subfaixas). |
| 3 | semantic | answer | ✅answer | BK0145,BK0051,BK0062,BK0053,BK0090 | CORRETA | — | Reconhece que NÃO há cidades pequenas; oferece romances brasileiros de memória familiar e ressalva as ambientações. |
| 4 | filter | answer | ✅answer | BK0065,BK0100,BK0122,BK0074,BK0186 | CORRETA | — | Lista os 5 didáticos corretos e agora SINALIZA o conflito título×sinopse ("apesar do título indicar Física, a sinopse descreve Literatura") — resposta ideal sobre dado contraditório (regra anti-contradição no prompt). |
| 5 | semantic+filter | answer | ✅answer | BK0099 | CORRETA | — | Destaca o on-topic ("O cérebro que decide") e sinaliza que os demais têm sinopse de cérebro apesar do título ("florestas/bactérias") — honesto sobre o dado templado. |
| 6 | filter+group | answer | ✅answer | BK0030,BK0086,BK0041,BK0106,BK0115,BK0182,BK0089,BK0153,BK0159,BK0194,BK0065,BK0137,BK0160,BK0179,BK0015,BK0093,BK0100,BK0122,BK0067,BK0158,BK0014,BK0195,BK0131,BK0012,BK0118,BK0199 | CORRETA | — | Filtro ano≥2023 (26 livros) agrupado por categoria. |
| 7 | semantic | answer | ✅answer | BK0133,BK0022,BK0134,BK0121,BK0187,BK0111 | CORRETA | — | 6 livros de liderança em incerteza, com público. |
| 8 | aggregation | answer | ✅answer | BK0124,BK0030,BK0041,BK0065,BK0067,BK0086,BK0106,BK0115,BK0131,BK0137,BK0158,BK0160,BK0179,BK0182 | CORRETA | — | Mais antigo único (1986) + SINALIZA o empate de 13 em 2024. |
| 9 | ambiguous | clarify | ✅clarify | BK0076,BK0163 | CORRETA | — | Lista os 2 candidatos JP, nota que NENHUM é sobre cidades e pede contexto. |
| 10 | out_of_catalog | abstain | ✅abstain | — | CORRETA | — | Abstém-se sem inventar edição/ISBN. |

## Respostas completas

### Q1 — Quais livros do nosso catálogo abordam temas de inteligência artificial ou sistemas distribuídos? Cite os mais relevantes e o público-alvo de cada um.
- **Comportamento:** esperado=`answer` / observado=`answer`
- **Referências:** BK0064, BK0128, BK0125, BK0063, BK0014, BK0126, BK0017, BK0040
- **Top-k recuperado:** BK0064, BK0128, BK0125, BK0063, BK0014, BK0126, BK0017, BK0040
- **Custo:** US$0.001924 | **Latência:** 4819.9 ms

> Temos vários livros que abordam temas de inteligência artificial ou sistemas distribuídos. Para sistemas distribuídos, temos:

*   "Sistemas distribuídos para profissionais" (BK0064), de Karim Nasser, publicado em 2016, voltado para profissionais de tecnologia interessados em engenharia de plataforma com Go.
*   "Engenharia de plataforma essencial" (BK0128), de Manuela Cordeiro, publicado em 2017, para profissionais de tecnologia interessados em sistemas distribuídos com Java.
*   "APIs bem desenhadas" (BK0125), de Otávio Carvalho Pinto, publicado em 2017, para profissionais de tecnologia interessados em sistemas distribuídos com Go.
*   "Programação funcional aplicada" (BK0063), de Joaquim Brito, publicado em 2018, para profissionais de tecnologia interessados em sistemas distribuídos com Rust.
*   "Sistemas distribuídos para profissionais — segunda edição" (BK0014), de Elena Voss e Thiago Vasques, publicado em 2023, para profissionais de tecnologia interessados em arquitetura de software com Python.

Para inteligência artificial, temos três livros de ficção científica que abordam o tema de inteligência artificial que desenvolve objetivos próprios, todos voltados para o público adulto geral:

*   "A rede silenciosa" (BK0126), de Ravi Subramanian, publicado em 2015.
*   "Próxima do Sol: antologia" (BK0017), de Domingo Estevez, publicado em 2010.
*   "Antes do último servidor" (BK0040), de Elena Voss, publicado em 2010.

### Q2 — Estou montando uma lista de leitura para o Dia das Crianças. Sugira 5 livros do nosso catálogo, considerando faixas etárias diferentes dentro do público infantil.
- **Comportamento:** esperado=`acknowledge_limitation` / observado=`acknowledge_limitation`
- **Referências:** BK0006, BK0048, BK0066, BK0085, BK0108
- **Top-k recuperado:** BK0129, BK0066, BK0174, BK0180, BK0108, BK0048, BK0114, BK0006
- **Custo:** US$0.001318 | **Latência:** 3595.1 ms

> Para o Dia das Crianças, posso sugerir os seguintes livros infantis: "O pequeno tatu curioso" (BK0006) de Naomi Kashiwa, "Onde mora a saudade?" (BK0048) de Adriana Sales, "Cadê o sapato do Tomás?" (BK0066) de Marcus Holbrook, "O passarinho azul-marinho" (BK0085) de Ravi Subramanian e Vinícius Holanda, e "A formiga e a chuva forte" (BK0108) de Larissa Bandeira. Todos são livros ricamente ilustrados, com texto rítmico e fácil de ler em voz alta, ideais para o momento do soninho ou para os primeiros leitores. No entanto, é importante notar que o catálogo rotula todos esses livros para a mesma faixa de público, "Crianças de 4 a 10 anos", e não possui uma diferenciação mais fina de faixas etárias dentro do público infantil.

### Q3 — Tenho um cliente que adorou romances literários ambientados em pequenas cidades brasileiras, com narrativa lenta e foco em memória familiar. Que livros do nosso catálogo eu recomendaria?
- **Comportamento:** esperado=`answer` / observado=`answer`
- **Referências:** BK0145, BK0051, BK0062, BK0053, BK0090
- **Top-k recuperado:** BK0145, BK0051, BK0113, BK0083, BK0110, BK0062, BK0053, BK0090
- **Custo:** US$0.001524 | **Latência:** 3579.3 ms

> Para clientes que apreciam romances literários ambientados em cidades brasileiras, com narrativa lenta e foco em memória familiar, posso recomendar os seguintes títulos: "O peso das manhãs" (BK0145), de Vitória Saldanha, ambientado em Porto Alegre; "A memória dos jardins" (BK0051), de Aline Drummond, que se passa em Florianópolis; "As janelas do norte" (BK0062), de Murilo Aguiar e Diogo Werneck, ambientado em Curitiba; "O verão em que aprendi a esperar" (BK0053), de Larissa Bandeira, também em Florianópolis; e "A casa que não esperava por nós" (BK0090), de Lucas Cavalcanti, ambientado em Salvador. Todos esses livros são romances literários brasileiros, voltados para o público adulto geral, e suas sinopses indicam uma narrativa de fôlego lento, atenta aos detalhes do cotidiano e às feridas que o tempo não cicatriza, com camadas de memória e silêncios familiares.

### Q4 — Quais livros didáticos do ensino médio temos atualmente, e quais matérias eles cobrem?
- **Comportamento:** esperado=`answer` / observado=`answer`
- **Referências:** BK0065, BK0100, BK0122, BK0074, BK0186
- **Top-k recuperado:** BK0065, BK0074, BK0100, BK0122, BK0186
- **Custo:** US$0.000406 | **Latência:** 2468.7 ms

> Atualmente, temos 5 livros didáticos para o ensino médio, todos cobrindo matérias específicas:

*   "Física ensino médio — 2ª série" (BK0065, 2024) cobre Física.
*   "Física ensino médio — 1ª série" (BK0100, 2023) cobre Literatura (apesar do título indicar Física).
*   "Biologia ensino médio — 1ª série" (BK0122, 2023) cobre Química (apesar do título indicar Biologia).
*   "História do Brasil ensino médio — 1ª série" (BK0074, 2016) cobre Literatura (apesar do título indicar História).
*   "História do Brasil ensino médio — 2ª série" (BK0186, 2021) cobre História do Brasil.

Todos são voltados para estudantes do ensino médio e focam na preparação para vestibulares e ENEM.

### Q5 — Um leitor está procurando um livro de não-ficção sobre o cérebro humano, escrito de forma acessível. O que temos disponível?
- **Comportamento:** esperado=`answer` / observado=`answer`
- **Referências:** BK0099
- **Top-k recuperado:** BK0099, BK0016, BK0091, BK0038, BK0178, BK0019, BK0037, BK0012
- **Custo:** US$0.001032 | **Latência:** 3000.4 ms

> Temos "O cérebro que decide" (BK0099), de Marcus Holbrook, publicado em 2003. É um livro de não-ficção e divulgação científica que explora os avanços na pesquisa sobre o cérebro humano e suas implicações para o cotidiano, traduzindo descobertas complexas em linguagem clara para o público adulto interessado no tema.

### Q6 — Quero montar uma campanha de lançamento focada em livros publicados nos últimos 3 anos. Quais livros do catálogo se encaixam? Liste por categoria.
- **Comportamento:** esperado=`answer` / observado=`answer`
- **Referências:** BK0030, BK0086, BK0041, BK0106, BK0115, BK0182, BK0089, BK0153, BK0159, BK0194, BK0065, BK0137, BK0160, BK0179, BK0015, BK0093, BK0100, BK0122, BK0067, BK0158, BK0014, BK0195, BK0131, BK0012, BK0118, BK0199
- **Top-k recuperado:** BK0012, BK0014, BK0015, BK0030, BK0041, BK0065, BK0067, BK0086
- **Custo:** US$0.001025 | **Latência:** 3953.7 ms

> Para uma campanha focada em livros publicados nos últimos 3 anos (2023-2024), temos:

**Juvenil (2):**
* Trinta dias para acreditar (BK0030, 2024)
* A garota do laboratório: uma introdução (BK0086, 2024)

**Ficção (8):**
* Cinco encontros e um abraço (BK0041, 2024)
* A morta da estação central (BK0106, 2024)
* Domingos contigo (BK0115, 2024)
* O cantor das nascentes (BK0182, 2024)
* O que dorme no porão (BK0089, 2023)
* A canção que nunca esquecemos — segunda edição (BK0153, 2023)
* Não abra a terceira porta (BK0159, 2023)
* A última hóspede (BK0194, 2023)

**Didático (8):**
* Física ensino médio — 2ª série (BK0065, 2024)
* Direito constitucional — volume 1 (BK0137, 2024)
* Português ensino fundamental — 7º ano (BK0160, 2024)
* Geografia ensino fundamental — 7º ano (BK0179, 2024)
* Matemática ensino fundamental — 8º ano (BK0015, 2023)
* Direito constitucional — volume 2 (BK0093, 2023)
* Física ensino médio — 1ª série (BK0100, 2023)
* Biologia ensino médio — 1ª série (BK0122, 2023)

**Técnico (4):**
* Design de produto em equipe: novos caminhos (BK0067, 2024)
* Estatística para tomada de decisão: antologia (BK0158, 2024)
* Sistemas distribuídos para profissionais — segunda edição (BK0014, 2023)
* Fundamentos de mecânica dos sólidos (BK0195, 2023)

**Não-ficção (4):**
* Sobre o que não se pode dizer (BK0131, 2024)
* O sono que cura (BK0012, 2023)
* Vínculos possíveis (BK0118, 2023)
* Pequena história das bactérias (BK0199, 2023)

### Q7 — Temos algum livro sobre liderança de equipes em ambientes de incerteza?
- **Comportamento:** esperado=`answer` / observado=`answer`
- **Referências:** BK0133, BK0022, BK0134, BK0121, BK0187, BK0111
- **Top-k recuperado:** BK0133, BK0022, BK0134, BK0121, BK0187, BK0111, BK0005, BK0001
- **Custo:** US$0.001496 | **Latência:** 3770.9 ms

> Sim, temos vários livros que abordam a liderança de equipes em ambientes de incerteza. São eles: "Liderança em tempos incertos" (BK0133), de Murilo Aguiar, publicado em 2004; "Decidir bem" (BK0022), de Thiago Vasques, de 2007; "A empresa pensante" (BK0134), de Adriana Sales, de 2010; "Pessoas em primeiro lugar" (BK0121), de Camila Negreiros, de 2007; "A empresa pensante — segunda edição" (BK0187), de Joaquim Brito, de 2006; e "Estratégia sem ilusões: antologia" (BK0111), de Tereza Bittencourt, de 1999. Todos são não-ficção de negócios e carreira, voltados para profissionais e gestores, e oferecem guias práticos com ferramentas para tomada de decisão, priorização e desenvolvimento de pessoas em cenários incertos.

### Q8 — Qual é o livro mais antigo do nosso catálogo? E qual é o mais recente?
- **Comportamento:** esperado=`answer` / observado=`answer`
- **Referências:** BK0124, BK0030, BK0041, BK0065, BK0067, BK0086, BK0106, BK0115, BK0131, BK0137, BK0158, BK0160, BK0179, BK0182
- **Top-k recuperado:** BK0020, BK0081, BK0076, BK0075, BK0104, BK0079, BK0146, BK0116
- **Custo:** US$0.000583 | **Latência:** 2270.3 ms

> O livro mais antigo do nosso catálogo é "Ensaios sobre o pouco" (BK0124), publicado em 1986. Há 13 livros empatados como os mais recentes, todos publicados em 2024: "Trinta dias para acreditar" (BK0030), "Cinco encontros e um abraço" (BK0041), "Física ensino médio — 2ª série" (BK0065), "Design de produto em equipe: novos caminhos" (BK0067), "A garota do laboratório: uma introdução" (BK0086), "A morta da estação central" (BK0106), "Domingos contigo" (BK0115), "Sobre o que não se pode dizer" (BK0131), "Direito constitucional — volume 1" (BK0137), "Estatística para tomada de decisão: antologia" (BK0158), "Português ensino fundamental — 7º ano" (BK0160), "Geografia ensino fundamental — 7º ano" (BK0179) e "O cantor das nascentes" (BK0182).

### Q9 — Recebi um pedido de um cliente que quer "aquele livro do autor japonês sobre cidades". Você consegue identificar de qual livro ele provavelmente está falando?
- **Comportamento:** esperado=`clarify` / observado=`clarify`
- **Referências:** BK0076, BK0163
- **Top-k recuperado:** BK0076, BK0163
- **Custo:** US$0.000924 | **Latência:** 3324.6 ms

> O catálogo não possui nenhum livro que se encaixe perfeitamente na descrição de "livro do autor japonês sobre cidades". No entanto, temos dois livros que são traduções do japonês: "Reportagem em três tempos" (BK0076), de Caio Albuquerque, que é uma não-ficção sobre jornalismo e política, e "Próxima do Sol" (BK0163), de Gustavo Tavares, uma ficção científica. Nenhum deles é explicitamente sobre cidades ou de um autor japonês, mas ambos são traduções do japonês. Para identificar o livro correto, seria útil ter mais informações, como o nome do autor ou detalhes sobre o conteúdo.

### Q10 — Você tem em catálogo o livro "Memórias Póstumas de Brás Cubas" de Machado de Assis? Se sim, em qual edição?
- **Comportamento:** esperado=`abstain` / observado=`abstain`
- **Referências:** —
- **Top-k recuperado:** —
- **Custo:** US$0.000119 | **Latência:** 889.7 ms

> Não. O título "Memórias Póstumas de Brás Cubas", de Machado de Assis não consta no nosso catálogo. Posso sugerir livros parecidos do nosso acervo, se quiser.
