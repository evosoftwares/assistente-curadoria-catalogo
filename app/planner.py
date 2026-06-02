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

# "últimos N anos" -> captura o N (grupo 1). Casa "ultimos 3 anos", "ultima 1 ano", etc.
_YEARS_BACK_RE = re.compile(r"ultim[oa]s?\s+(\d+)\s+anos?")
# Texto entre aspas (retas, curvas ou simples), com 3+ chars -> candidato a TÍTULO (Q10).
_QUOTED_RE = re.compile(r"[\"“”'']([^\"“”'']{3,})[\"“”'']")
# "de <Nome Próprio>" -> autor. Aceita conectores (de/da/do) no meio: "de Machado de Assis".
_AUTHOR_RE = re.compile(
    r"\bde\s+([A-ZÀ-Ú][\wÀ-ú]+(?:\s+(?:de|da|do|dos|das)\s+[A-ZÀ-Ú][\wÀ-ú]+|\s+[A-ZÀ-Ú][\wÀ-ú]+){0,3})"
)

# Palavras que sinalizam público-alvo na pergunta (usadas pelo fallback determinístico).
_PUBLICO_KEYWORDS = ["infantil", "crianç", "crianc", "jovens", "juvenil", "adolescente",
                     "ensino médio", "ensino medio", "ensino fundamental", "universitário", "universitario"]


def resolve_year_bounds(years_back: Optional[int], ano_min: Optional[int], ano_max: Optional[int]) -> tuple[Optional[int], Optional[int]]:
    """Converte years_back em ano_min de forma DETERMINÍSTICA (em Python, não no LLM).
    Convenção documentada (generosa): "últimos N anos" == ano_publicacao >= CURRENT_YEAR - N, o que
    abrange o ANO ATUAL e os N anos anteriores (N+1 anos no total).
    Ex.: N=3, CURRENT_YEAR=2026 => ano >= 2023 (2023, 2024, 2025, 2026)."""
    if years_back is not None and ano_min is None:   # só converte se não veio um ano absoluto
        ano_min = config.CURRENT_YEAR - int(years_back)  # a CONTA é aqui, em Python (nunca no LLM)
    return ano_min, ano_max


def _to_plan(out: PlannerLLMOutput, catalog: Catalog, source: str) -> RetrievalPlan:
    """Resolve a saída crua do LLM (PlannerLLMOutput) no plano usável (RetrievalPlan):
    aqui o Python faz o que NÃO se delega ao LLM — calcular datas e validar enums."""
    ano_min, ano_max = resolve_year_bounds(out.years_back, out.ano_min, out.ano_max)  # data em Python
    generos = catalog.match_generos(out.generos)        # mapeia p/ gêneros REAIS (fuzzy); descarta inválidos
    publico = catalog.match_publico(out.publico_alvo)   # idem p/ público (sinônimos: "infantil"->faixa real)
    semantic = [q.strip() for q in out.semantic_queries if q and q.strip()]  # limpa sub-queries vazias
    # Valida idioma contra os idiomas REAIS: descarta extrações espúrias (ex.: o LLM
    # tirar 'brasileiro'/'português' de 'cidades brasileiras'), que zerariam o conjunto.
    idioma = out.idioma_contains if (out.idioma_contains and catalog.valid_idioma(out.idioma_contains)) else None
    return RetrievalPlan(
        semantic_queries=semantic,
        generos=generos,
        publico_alvo=publico,
        idioma_contains=idioma,
        ano_min=ano_min,
        ano_max=ano_max,
        aggregation=out.aggregation,
        aggregations=([out.aggregation] if out.aggregation != Aggregation.none else []),
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
    q = question                                  # texto original (preserva maiúsculas p/ autor/título)
    nq = normalize(q)                              # versão sem acento/minúscula p/ casar palavras-chave
    out = PlannerLLMOutput(semantic_queries=[q.strip()])  # base: a própria pergunta como query semântica

    # --- ANOS ---
    m = _YEARS_BACK_RE.search(nq)                  # procura "últimos N anos"
    if m:
        out.years_back = int(m.group(1))           # guarda só o N; o Python calcula o ano em _to_plan
    if "ultimo ano" in nq:                         # caso especial "último ano" (sem número) = N=1
        out.years_back = 1
    abs_years = [int(y) for y in re.findall(r"\b(?:19|20)\d{2}\b", q)]  # anos absolutos citados (ex.: 2015)
    if abs_years and ("apos" in nq or "depois de" in nq or "a partir de" in nq):  # "após 2015" etc.
        out.ano_min = min(abs_years)

    # --- AGREGAÇÃO (mín/máx ano) ---
    if re.search(r"mais\s+(antig|velh)", nq):      # "mais antigo / mais velho"
        out.aggregation = Aggregation.min_year
    if re.search(r"mais\s+(recent|nov)", nq):      # "mais recente / mais novo"
        # Se a pergunta cita os DOIS extremos, _augment monta a lista completa; aqui só
        # marcamos max se min ainda não foi marcado (o enum único guarda 1; a lista guarda os 2).
        out.aggregation = Aggregation.max_year if out.aggregation == Aggregation.none else out.aggregation

    # --- AGRUPAMENTO / DIVERSIDADE ---
    if "por categoria" in nq or "por genero" in nq or "por gênero" in nq:  # "liste por categoria" (Q6)
        out.group_by = GroupBy.genero
        out.is_categorical = True                  # "por categoria" torna o gênero um filtro DURO
    if any(k in nq for k in ["diferentes", "variad", "faixas etarias", "faixas etárias"]):  # diversidade (Q2)
        out.diversity = True

    # --- IDIOMA (Q9: "autor japonês") ---
    for lang in ["japon", "frances", "francês", "espanhol", "ingles", "inglês"]:
        if lang in nq:
            out.idioma_contains = lang.replace("ê", "e").replace("ç", "c")  # normaliza p/ casar "tradução do japonês"

    # --- AMBIGUIDADE (Q9): "hedges" que denunciam pergunta vaga ---
    if any(h in nq for h in ["aquele livro", "aquela obra", "provavelmente", "consegue identificar",
                              "qual seria", "deve estar falando", "esta falando"]):
        out.is_ambiguous = True

    # --- TÍTULO entre aspas (Q10) ---
    qm = _QUOTED_RE.search(q)                       # há algo entre aspas?
    if qm:
        quoted = qm.group(1).strip()
        # Só é "título de pertencimento" se NÃO for uma descrição ("aquele livro do autor...").
        descriptor = any(w in normalize(quoted) for w in
                         ["aquele", "aquela", "autor", "sobre", "livro do", "livro da", "algum livro"])
        if not descriptor:
            out.title_lookup = quoted               # vira a checagem de pertencimento (Q10)
            am = _AUTHOR_RE.search(q[qm.end():])     # busca o autor APÓS as aspas (não dentro do título)
            if am:
                out.author_lookup = am.group(1).strip()

    # --- PÚBLICO ---
    for kw in _PUBLICO_KEYWORDS:                     # "infantil", "ensino médio", etc. presentes na pergunta
        if normalize(kw) in nq:
            out.publico_alvo.append(kw)              # match_publico (em _to_plan) mapeia p/ a faixa real
    if any(k in nq for k in ["didatic", "didátic"]):  # "livros didáticos" -> gênero como exigência dura
        out.is_categorical = True

    # --- GÊNEROS explícitos que existem no vocabulário do catálogo ---
    for g in catalog.generos_vocab:
        if normalize(g) in nq:                       # o nome do gênero aparece literalmente na pergunta?
            out.generos.append(g)

    return out


def fallback_plan(question: str, catalog: Catalog) -> RetrievalPlan:
    """Planner 100% determinístico (sem LLM): usado sem chave OU quando o LLM falha.
    Detecta sinais por regex, resolve no plano e passa pela MESMA reconciliação do caminho LLM."""
    det = _detect_signals(question, catalog)         # 1x os sinais por regex
    return _augment_with_rules(_to_plan(det, catalog, source="fallback"), det, question)  # resolve + reconcilia


def _augment_with_rules(plan: RetrievalPlan, det: PlannerLLMOutput, question: str) -> RetrievalPlan:
    """Reconcilia o plano do LLM com sinais determinísticos. Para padrões inequívocos
    (agregação, data relativa, título entre aspas, idioma, ambiguidade), o determinístico
    PREENCHE lacunas do LLM — evita que um plano malformado do LLM quebre tudo."""
    nq = normalize(question)

    # AGREGAÇÃO direto do texto: a pergunta pode pedir os DOIS extremos ("mais antigo E o mais
    # recente") — o enum único do LLM não representa isso, então montamos a LISTA aqui.
    aggs: list[Aggregation] = []
    if re.search(r"mais\s+(antig|velh)", nq):           # pediu o mais antigo
        aggs.append(Aggregation.min_year)
    if re.search(r"mais\s+(recent|nov)", nq):           # pediu o mais recente
        aggs.append(Aggregation.max_year)
    if not aggs and plan.aggregation != Aggregation.none:
        aggs = [plan.aggregation]                        # regex não achou, mas o LLM marcou -> respeita
    plan.aggregations = aggs                             # lista (0, 1 ou 2 extremos) que o pipeline usa
    plan.aggregation = aggs[0] if aggs else Aggregation.none  # compat: 1º extremo no campo único

    # Preenchimento de LACUNAS: o determinístico só entra onde o LLM não definiu (datas/grupo/etc.).
    if plan.ano_min is None and det.years_back is not None:      # LLM não deu ano, mas há "últimos N anos"
        plan.ano_min, _ = resolve_year_bounds(det.years_back, None, None)  # calcula o ano em Python
    if plan.ano_min is None and det.ano_min is not None:        # ou um ano absoluto ("após 2015")
        plan.ano_min = det.ano_min
    if plan.group_by == GroupBy.none and det.group_by != GroupBy.none:  # "por categoria" que o LLM perdeu
        plan.group_by = det.group_by
    if not plan.diversity and det.diversity:                    # "faixas diferentes" que o LLM perdeu
        plan.diversity = True
    if not plan.idioma_contains and det.idioma_contains:        # det só usa idiomas reais conhecidos
        plan.idioma_contains = det.idioma_contains

    # TÍTULO de pertencimento: copia do detector se o LLM não pegou. Decidido ANTES da
    # ambiguidade de propósito, para o título contar como "intenção forte" logo abaixo.
    if not plan.title_lookup and det.title_lookup:
        plan.title_lookup = det.title_lookup
        plan.author_lookup = plan.author_lookup or det.author_lookup

    # AMBIGUIDADE: vale o "hedge" (det ou LLM), MAS uma intenção concreta no plano JÁ MESCLADO
    # a SUPRIME. É isto que faz o título entre aspas (Q10) vencer um hedge e cair na abstenção,
    # em vez de virar "clarify" à toa.
    strong_intent = bool(
        plan.aggregations or plan.group_by != GroupBy.none or plan.ano_min is not None
        or plan.title_lookup or plan.diversity
    )
    plan.is_ambiguous = (det.is_ambiguous or plan.is_ambiguous) and not strong_intent
    return plan


class Planner:
    def __init__(self, catalog: Catalog, client: Optional[GeminiClient] = None):
        self.catalog = catalog
        self.client = client or get_client()
        self._system = planner_system(catalog.generos_vocab, catalog.publico_vocab, config.CURRENT_YEAR)

    def plan(self, question: str) -> tuple[RetrievalPlan, Optional[Usage]]:
        # Sem chave de API -> nem tenta o LLM: vai direto ao planner determinístico (e o resto
        # do sistema roda em modo BM25-only). Retorna usage=None (não houve custo de LLM).
        if not self.client.available:
            return fallback_plan(question, self.catalog), None
        try:
            # Caminho primário: LLM extrai a intenção em JSON validado pelo schema (barato: flash-lite).
            data, usage = self.client.generate_structured(
                self._system, question, PlannerLLMOutput, model=config.GEMINI_PLANNER_MODEL
            )
            out = PlannerLLMOutput.model_validate(data)         # valida a forma (Pydantic)
            plan = _to_plan(out, self.catalog, source="llm")    # resolve datas/enums em Python
            # RECONCILIAÇÃO: sinais determinísticos preenchem/corrigem o que o LLM erra
            # (datas, agregação, título, idioma, ambiguidade) — elimina o ponto único de falha.
            plan = _augment_with_rules(plan, _detect_signals(question, self.catalog), question)
            if not plan.semantic_queries:                        # garante ao menos a pergunta como query
                plan.semantic_queries = [question.strip()]
            return plan, usage
        except Exception:
            # QUALQUER falha do LLM (rede, timeout, JSON inválido, schema) cai no fallback
            # 100% determinístico — o sistema nunca quebra por causa do planner.
            return fallback_plan(question, self.catalog), None
