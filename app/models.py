"""Modelos Pydantic: contrato da API + plano de recuperação.

DECISÃO DE DESIGN CENTRAL — dois "planos" separados (separação de responsabilidades):
- ``PlannerLLMOutput``: SÓ o que o LLM preenche — intenção/filtros em campos simples, SEM
  aritmética nem decisões. É o limite de confiança no LLM.
- ``RetrievalPlan``: o plano RESOLVIDO em Python — datas calculadas (CURRENT_YEAR−N), enums
  validados contra o vocabulário REAL do catálogo, soft/hard decidido. É o que o retriever usa.

Por que separar: tudo que é determinístico/verificável (datas, validação, agregação) fica do
lado do Python; o LLM só faz o que LLM faz bem (entender linguagem). Isso é o que torna o
sistema testável e à prova de planos malformados do LLM.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class Aggregation(str, Enum):
    none = "none"
    min_year = "min_year"  # livro mais antigo
    max_year = "max_year"  # livro mais recente


class GroupBy(str, Enum):
    none = "none"
    genero = "genero"


class Behavior(str, Enum):
    """Como a resposta deve se comportar — também usado na avaliação."""
    answer = "answer"
    abstain = "abstain"                        # Q10: livro fora do catálogo
    clarify = "clarify"                         # Q9: pergunta ambígua
    acknowledge_limitation = "acknowledge_limitation"  # Q2: dado não suporta o pedido


# ---------------------------------------------------------------------------
# Saída do planner LLM (schema enviado ao Gemini como response_schema)
# ---------------------------------------------------------------------------
class PlannerLLMOutput(BaseModel):
    """Filtros estruturados extraídos da pergunta. O LLM NÃO calcula datas:
    devolve ``years_back`` e o Python computa o ano de corte."""
    semantic_queries: list[str] = Field(
        default_factory=list,
        description="Consultas semânticas curtas (1 por conceito). Para perguntas com 'ou' use várias.",
    )
    generos: list[str] = Field(default_factory=list, description="Gêneros pedidos explicitamente.")
    publico_alvo: list[str] = Field(default_factory=list, description="Público-alvo pedido (ex.: infantil).")
    idioma_contains: Optional[str] = Field(
        default=None, description="Trecho de idioma/origem, ex.: 'japonês' para 'autor japonês'."
    )
    years_back: Optional[int] = Field(
        default=None, description="Se a pergunta diz 'últimos N anos', informe N. Não calcule o ano."
    )
    ano_min: Optional[int] = Field(default=None, description="Ano mínimo absoluto, se explícito.")
    ano_max: Optional[int] = Field(default=None, description="Ano máximo absoluto, se explícito.")
    aggregation: Aggregation = Field(default=Aggregation.none, description="min_year=mais antigo, max_year=mais recente.")
    group_by: GroupBy = Field(default=GroupBy.none, description="genero se a pergunta pede 'por categoria'.")
    diversity: bool = Field(default=False, description="True se pede itens variados/diferentes entre si.")
    title_lookup: Optional[str] = Field(
        default=None, description="Título específico que o usuário pergunta se existe (ex.: Q10)."
    )
    author_lookup: Optional[str] = Field(default=None, description="Autor específico citado, se houver.")
    is_ambiguous: bool = Field(default=False, description="True se a pergunta é vaga e pede esclarecimento.")
    is_categorical: bool = Field(
        default=False,
        description="True se o filtro de gênero/público é uma exigência dura (ex.: 'livros didáticos'), não só um tema.",
    )


# ---------------------------------------------------------------------------
# Plano resolvido (interno)
# ---------------------------------------------------------------------------
class RetrievalPlan(BaseModel):
    semantic_queries: list[str] = Field(default_factory=list)
    generos: list[str] = Field(default_factory=list)
    publico_alvo: list[str] = Field(default_factory=list)
    idioma_contains: Optional[str] = None
    ano_min: Optional[int] = None
    ano_max: Optional[int] = None
    aggregation: Aggregation = Aggregation.none  # compat/debug (primeiro extremo)
    aggregations: list[Aggregation] = Field(default_factory=list)  # extremos pedidos (min e/ou max)
    group_by: GroupBy = GroupBy.none
    diversity: bool = False
    title_lookup: Optional[str] = None
    author_lookup: Optional[str] = None
    is_ambiguous: bool = False
    hard_genre_filter: bool = False  # True => filtro duro; False => boost (soft)
    source: str = "llm"              # "llm" | "fallback"


# ---------------------------------------------------------------------------
# Contrato HTTP
# ---------------------------------------------------------------------------
class AskRequest(BaseModel):
    # max_length=2000: limita o tamanho da entrada (anti-DoS / controle de custo de tokens).
    question: str = Field(..., min_length=2, max_length=2000)

    @field_validator("question")
    @classmethod
    def _sanitize(cls, v: str) -> str:
        # Sanitização de entrada: remove caracteres de CONTROLE (exceto \n e \t) — neutraliza
        # tentativas de poluir o prompt/logs com bytes de controle — e apara espaços nas bordas.
        cleaned = "".join(ch for ch in v if ch in ("\n", "\t") or ord(ch) >= 32)
        return cleaned.strip()


class AnswerOut(BaseModel):
    """Saída estruturada da geração ancorada (response_schema do Gemini — sem json.loads manual)."""
    answer: str = Field(..., description="Resposta em português, ancorada nos livros fornecidos.")
    cited_ids: list[str] = Field(default_factory=list, description="IDs dos livros citados (ex.: BK0001).")


class BookRef(BaseModel):
    id: str
    titulo: str
    autores: list[str]
    generos: list[str]
    publico_alvo: str
    ano_publicacao: int
    idioma: str
    isbn: str
    score: Optional[float] = None


class RetrievalDebug(BaseModel):
    plan: dict
    behavior: Behavior
    retrieved_ids: list[str]
    context_ids: list[str] = Field(default_factory=list)  # livros que o gerador realmente viu
    candidate_count: int
    top_cosine: Optional[float] = None
    latency_ms: dict = Field(default_factory=dict)
    tokens: dict = Field(default_factory=dict)
    estimated_cost_usd: float = 0.0
    from_cache: bool = False
    notes: list[str] = Field(default_factory=list)


class AskResponse(BaseModel):
    answer: str
    references: list[BookRef] = Field(default_factory=list)
    retrieval_debug: RetrievalDebug
