"""Planner: pergunta em PT-BR -> RetrievalPlan estruturado.

Caminho primário: Gemini com structured output (response_schema).
Rede de segurança: fallback determinístico por regex/palavras-chave que roda quando
o LLM falha, dá timeout, devolve JSON inválido OU quando não há chave de API.

Invariantes de robustez (recomendados pelo red-team):
- O LLM NUNCA calcula datas: devolve years_back; o Python computa o ano de corte.
- Enums propostos pelo LLM são validados contra o vocabulário REAL do catálogo
  (evita filtro que zera o resultado por um gênero inexistente).
"""
from __future__ import annotations

import re
from typing import Optional

from . import config
from .catalog import Catalog, normalize
from .llm import GeminiClient, Usage, get_client
from .models import Aggregation, GroupBy, PlannerLLMOutput, RetrievalPlan
from .prompts import planner_system

_YEARS_BACK_RE = re.compile(r"ultim[oa]s?\s+(\d+)\s+anos?")
_QUOTED_RE = re.compile(r"[\"“”'']([^\"“”'']{3,})[\"“”'']")
_AUTHOR_RE = re.compile(
    r"\bde\s+([A-ZÀ-Ú][\wÀ-ú]+(?:\s+(?:de|da|do|dos|das)\s+[A-ZÀ-Ú][\wÀ-ú]+|\s+[A-ZÀ-Ú][\wÀ-ú]+){0,3})"
)

_PUBLICO_KEYWORDS = ["infantil", "crianç", "crianc", "jovens", "juvenil", "adolescente",
                     "ensino médio", "ensino medio", "ensino fundamental", "universitário", "universitario"]


def resolve_year_bounds(years_back: Optional[int], ano_min: Optional[int], ano_max: Optional[int]) -> tuple[Optional[int], Optional[int]]:
    """Converte years_back em ano_min de forma DETERMINÍSTICA (em Python, não no LLM).
    Convenção documentada: "últimos N anos" == ano_publicacao >= CURRENT_YEAR - N + 1? Não:
    adotamos ano >= CURRENT_YEAR - N (inclui o ano atual e os N-1 anteriores de forma generosa).
    Ex.: N=3, CURRENT_YEAR=2026 => ano >= 2023."""
    if years_back is not None and ano_min is None:
        ano_min = config.CURRENT_YEAR - int(years_back)
    return ano_min, ano_max


def _to_plan(out: PlannerLLMOutput, catalog: Catalog, source: str) -> RetrievalPlan:
    ano_min, ano_max = resolve_year_bounds(out.years_back, out.ano_min, out.ano_max)
    generos = catalog.match_generos(out.generos)
    publico = catalog.match_publico(out.publico_alvo)
    semantic = [q.strip() for q in out.semantic_queries if q and q.strip()]
    return RetrievalPlan(
        semantic_queries=semantic,
        generos=generos,
        publico_alvo=publico,
        idioma_contains=out.idioma_contains,
        ano_min=ano_min,
        ano_max=ano_max,
        aggregation=out.aggregation,
        group_by=out.group_by,
        diversity=out.diversity,
        title_lookup=out.title_lookup,
        author_lookup=out.author_lookup,
        is_ambiguous=out.is_ambiguous,
        hard_genre_filter=out.is_categorical,
        source=source,
    )


def _detect_signals(question: str, catalog: Catalog) -> PlannerLLMOutput:
    """Extrai sinais determinísticos da pergunta (regex/palavras-chave).
    Usado tanto como planner de fallback quanto para RECONCILIAR o plano do LLM
    (datas, agregação e título são padrões inequívocos que o LLM às vezes erra)."""
    q = question
    nq = normalize(q)
    out = PlannerLLMOutput(semantic_queries=[q.strip()])

    # anos
    m = _YEARS_BACK_RE.search(nq)
    if m:
        out.years_back = int(m.group(1))
    if "ultimo ano" in nq:
        out.years_back = 1
    abs_years = [int(y) for y in re.findall(r"\b(?:19|20)\d{2}\b", q)]
    if abs_years and ("apos" in nq or "depois de" in nq or "a partir de" in nq):
        out.ano_min = min(abs_years)

    # agregação
    if re.search(r"mais\s+(antig|velh)", nq):
        out.aggregation = Aggregation.min_year
    if re.search(r"mais\s+(recent|nov)", nq):
        # se a pergunta menciona ambos (mais antigo E mais recente), priorizamos min e
        # o pipeline computa os dois; marcamos max se só esse aparecer.
        out.aggregation = Aggregation.max_year if out.aggregation == Aggregation.none else out.aggregation

    # agrupamento / diversidade
    if "por categoria" in nq or "por genero" in nq or "por gênero" in nq:
        out.group_by = GroupBy.genero
        out.is_categorical = True
    if any(k in nq for k in ["diferentes", "variad", "faixas etarias", "faixas etárias"]):
        out.diversity = True

    # idioma (Q9: autor japonês)
    for lang in ["japon", "frances", "francês", "espanhol", "ingles", "inglês"]:
        if lang in nq:
            out.idioma_contains = lang.replace("ê", "e").replace("ç", "c")

    # ambiguidade (Q9): hedges típicos de pergunta vaga.
    if any(h in nq for h in ["aquele livro", "aquela obra", "provavelmente", "consegue identificar",
                              "qual seria", "deve estar falando", "esta falando"]):
        out.is_ambiguous = True

    # título entre aspas (Q10). Só tratamos como título de pertencimento quando a
    # citação PARECE um título (não uma descrição como "aquele livro do autor...").
    qm = _QUOTED_RE.search(q)
    if qm:
        quoted = qm.group(1).strip()
        descriptor = any(w in normalize(quoted) for w in
                         ["aquele", "aquela", "autor", "sobre", "livro do", "livro da", "algum livro"])
        if not descriptor:
            out.title_lookup = quoted
            am = _AUTHOR_RE.search(q[qm.end():])
            if am:
                out.author_lookup = am.group(1).strip()

    # público
    for kw in _PUBLICO_KEYWORDS:
        if normalize(kw) in nq:
            out.publico_alvo.append(kw)
    if any(k in nq for k in ["didatic", "didátic"]):
        out.is_categorical = True

    # gêneros explícitos presentes no vocabulário
    for g in catalog.generos_vocab:
        if normalize(g) in nq:
            out.generos.append(g)

    return out


def fallback_plan(question: str, catalog: Catalog) -> RetrievalPlan:
    """Planner 100% determinístico (sem LLM)."""
    return _to_plan(_detect_signals(question, catalog), catalog, source="fallback")


def _augment_with_rules(plan: RetrievalPlan, det: PlannerLLMOutput) -> RetrievalPlan:
    """Reconcilia o plano do LLM com sinais determinísticos. Para padrões inequívocos
    (agregação, data relativa, título entre aspas, idioma, ambiguidade), o determinístico
    PREENCHE lacunas do LLM — evita que um plano malformado do LLM quebre tudo."""
    if plan.aggregation == Aggregation.none and det.aggregation != Aggregation.none:
        plan.aggregation = det.aggregation
    if plan.ano_min is None and det.years_back is not None:
        plan.ano_min, _ = resolve_year_bounds(det.years_back, None, None)
    if plan.ano_min is None and det.ano_min is not None:
        plan.ano_min = det.ano_min
    if plan.group_by == GroupBy.none and det.group_by != GroupBy.none:
        plan.group_by = det.group_by
    if not plan.diversity and det.diversity:
        plan.diversity = True
    if not plan.idioma_contains and det.idioma_contains:
        plan.idioma_contains = det.idioma_contains
    # Ambiguidade: vale se o determinístico achou "hedges" (Q9). Mas se há uma INTENÇÃO
    # concreta (agregação/grupo/data/título/diversidade) e nenhum hedge, o LLM marcar
    # is_ambiguous é provavelmente ruído — limpamos para não cair em 'clarify' à toa.
    strong_intent = (
        det.aggregation != Aggregation.none or det.group_by != GroupBy.none
        or det.years_back is not None or det.ano_min is not None
        or bool(det.title_lookup) or det.diversity
    )
    plan.is_ambiguous = det.is_ambiguous or (plan.is_ambiguous and not strong_intent)
    if not plan.title_lookup and det.title_lookup and not plan.is_ambiguous:
        plan.title_lookup = det.title_lookup
        plan.author_lookup = plan.author_lookup or det.author_lookup
    return plan


class Planner:
    def __init__(self, catalog: Catalog, client: Optional[GeminiClient] = None):
        self.catalog = catalog
        self.client = client or get_client()
        self._system = planner_system(catalog.generos_vocab, catalog.publico_vocab, config.CURRENT_YEAR)

    def plan(self, question: str) -> tuple[RetrievalPlan, Optional[Usage]]:
        if not self.client.available:
            return fallback_plan(question, self.catalog), None
        try:
            data, usage = self.client.generate_structured(
                self._system, question, PlannerLLMOutput, model=config.GEMINI_PLANNER_MODEL
            )
            out = PlannerLLMOutput.model_validate(data)
            plan = _to_plan(out, self.catalog, source="llm")
            # Reconcilia com sinais determinísticos (datas/agregação/título/idioma/ambiguidade).
            plan = _augment_with_rules(plan, _detect_signals(question, self.catalog))
            # Se o LLM não extraiu nenhuma query semântica, garanta ao menos a pergunta.
            if not plan.semantic_queries:
                plan.semantic_queries = [question.strip()]
            return plan, usage
        except Exception:
            # Qualquer falha (rede, JSON inválido, schema) -> fallback determinístico.
            return fallback_plan(question, self.catalog), None
