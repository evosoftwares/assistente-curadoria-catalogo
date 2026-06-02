"""Orquestração de /ask: plano -> filtro/ferramentas -> recuperação -> geração
ancorada -> verificação de citações -> resposta. Inclui abstenção (Q10), clarify
(Q9), reconhecimento de limitação (Q2), agregação (Q8), agrupamento (Q6) e
degradação graciosa quando o LLM/embeddings não estão disponíveis.
"""
from __future__ import annotations

import hashlib
import re
import threading
import time
from typing import Optional

import numpy as np

from . import config, tools
from .catalog import Catalog, get_catalog
from .embeddings import EmbeddingIndex
from .llm import CostMeter, GeminiClient, Usage, get_client
from .models import (
    Aggregation,
    AnswerOut,
    AskResponse,
    Behavior,
    BookRef,
    GroupBy,
    RetrievalDebug,
    RetrievalPlan,
)
from .planner import Planner
from .prompts import ANSWER_SYSTEM, build_answer_prompt
from .retriever import HybridRetriever


# Perguntas cujo SENTIDO depende de um token decisivo (número/data/negação/comparação) NÃO podem
# usar o cache semântico: "após 2015" vs "após 2020" e "infantis" vs "NÃO infantis" têm embeddings
# quase idênticos (cos > 0,92) mas exigem filtros OPOSTOS — serviriam a resposta ERRADA. Para essas,
# desligamos o cache (o cache exato por sha256 continua valendo). (Achado SEC-03 da auditoria.)
_CACHE_UNSAFE_RE = re.compile(
    r"\d|\bn[ãa]o\b|\bsem\b|\bexceto\b|\bantes\b|\bdepois\b|\bap[óo]s\b|\bat[ée]\b|\bmaior\b|\bmenor\b",
    re.IGNORECASE,
)


def _cacheable(question: str) -> bool:
    """False quando a pergunta tem número/negação/comparação (ver _CACHE_UNSAFE_RE)."""
    return not _CACHE_UNSAFE_RE.search(question)


def _coerce_id_list(value) -> list[str]:
    """Normaliza cited_ids do LLM: aceita lista de strings; string vira [string]
    (não quebra em caracteres); descarta não-strings; DEDUPLICA preservando ordem (evita
    referências repetidas quando o LLM cita o mesmo id em duas frases — achado NEW-01)."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(v for v in value if isinstance(v, str)))


def _book_ref(book: dict, score: Optional[float] = None) -> BookRef:
    return BookRef(
        id=book["id"], titulo=book["titulo"], autores=book.get("autores", []),
        generos=book.get("generos", []), publico_alvo=book.get("publico_alvo", ""),
        ano_publicacao=book["ano_publicacao"], idioma=book.get("idioma", ""),
        isbn=book.get("isbn", ""), score=round(score, 4) if score is not None else None,
    )


class AskPipeline:
    def __init__(
        self,
        catalog: Optional[Catalog] = None,
        index: Optional[EmbeddingIndex] = None,
        client: Optional[GeminiClient] = None,
    ):
        self.catalog = catalog or get_catalog()
        self.client = client or get_client()
        self.index = index or self._init_index()
        self.retriever = HybridRetriever(self.catalog, self.index)
        self.planner = Planner(self.catalog, self.client)
        self._cache: dict[str, AskResponse] = {}
        self._sem_cache: list[tuple[np.ndarray, str]] = []  # (embedding da pergunta, chave)
        # O pipeline é UM objeto compartilhado e /ask é síncrono (FastAPI o roda num threadpool):
        # requisições concorrentes tocam os caches em paralelo. Este lock serializa as mutações
        # dos caches para evitar corrida na evicção/append (achado SEC-02 da auditoria).
        self._cache_lock = threading.Lock()

    def _init_index(self) -> EmbeddingIndex:
        """Carrega o cache de embeddings; só (re)constrói se houver como embeddar.
        Sem chave e sem cache, segue em modo BM25-only (matrix=None)."""
        idx = EmbeddingIndex(self.catalog, self.client)
        if idx.load():
            return idx
        if self.client.available or config.EMBEDDINGS_BACKEND == "local":
            idx.build()
        return idx  # matrix pode ficar None -> retrieval cai p/ BM25-only

    # ------------------------------------------------------------------ ask
    def ask(self, question: str) -> AskResponse:
        t0 = time.perf_counter()
        q = question.strip()
        # Pergunta vazia/trivial: curto-circuita sem gastar uma ida ao LLM.
        if len(q) < 2:
            return AskResponse(
                answer="Sua pergunta está vazia. Diga o que você procura no catálogo (tema, gênero, público, autor…).",
                references=[],
                retrieval_debug=RetrievalDebug(
                    plan={}, behavior=Behavior.clarify, retrieved_ids=[], candidate_count=0,
                    latency_ms={"total_ms": round((time.perf_counter() - t0) * 1000, 1)},
                    notes=["pergunta vazia/trivial -> clarify (sem LLM)"],
                ),
            )
        meter = CostMeter()                          # criado JÁ (conta também o embedding da pergunta)
        key = hashlib.sha256(q.lower().encode("utf-8")).hexdigest()
        with self._cache_lock:                       # leitura do cache exato sob lock (thread-safe)
            cached = self._cache.get(key)
        if cached is not None:
            out = cached.model_copy(deep=True)
            out.retrieval_debug.from_cache = True
            return out

        # Cache SEMÂNTICO: pega paráfrases que o sha256 (exato) perderia — MAS só para perguntas
        # "cacheáveis" (sem número/negação/comparação), senão serviria a resposta errada (SEC-03).
        q_vec = self._maybe_embed_question(q, meter) if _cacheable(q) else None
        hit = self._semantic_cache_lookup(q_vec)
        if hit is not None:
            return hit

        timings: dict[str, float] = {}

        # 1) Plano
        ts = time.perf_counter()
        plan, plan_usage = self.planner.plan(question)
        if plan_usage:
            meter.add(plan_usage)
        timings["planner_ms"] = round((time.perf_counter() - ts) * 1000, 1)

        # 2) Pertencimento ao catálogo (Q10) — curto-circuito determinístico.
        #    Pulamos quando a pergunta é ambígua (Q9 quer esclarecimento, não abstenção).
        if plan.title_lookup and not plan.is_ambiguous:
            resp = self._handle_title_lookup(question, plan, meter, timings, t0)
            if resp is not None:
                self._store(key, resp, q_vec)
                return resp

        # 3) Recuperação (embedding da consulta + híbrido)
        ts = time.perf_counter()
        query_vecs = self._embed_queries(plan, meter)   # passa o meter p/ contabilizar embeddings
        results, rdebug = self.retriever.retrieve(plan, query_vecs)
        timings["retrieval_ms"] = round((time.perf_counter() - ts) * 1000, 1)

        # 4) DESPACHO DE COMPORTAMENTO — escolhe o que `context_books` (o que o gerador vê) e o
        #    comportamento serão, segundo o plano. Cada ramo trata uma das "armadilhas".
        behavior = Behavior.answer                 # default: responder normalmente
        computed_facts: Optional[str] = None       # fatos pré-calculados (agregação/grupo) p/ o prompt
        extra_directive: Optional[str] = None      # instrução extra ao gerador (clarify/limitação)
        context_books: list[dict]                  # os livros que vão ao gerador
        ranking_used = False  # True só nos paths cujo context_books vem do RANKING de relevância
        notes = list(rdebug["notes"])              # copia as notas do retrieve p/ acrescentar as nossas

        if plan.is_ambiguous:                      # Q9: pergunta vaga -> NÃO cravar; pedir contexto
            behavior = Behavior.clarify
            context_books = [r.book for r in results]   # mostra os candidatos recuperados
            ranking_used = True                          # vieram do ranking -> score faz sentido
            extra_directive = (
                "A pergunta é ambígua. NÃO afirme um único livro com certeza; liste os candidatos "
                "abaixo como possibilidades e peça o contexto que falta."
            )
        elif plan.aggregations:                    # Q8: "mais antigo/recente" -> CÁLCULO, não busca
            cand = self.retriever.candidates(plan)      # conjunto pós-filtro inteiro (não o top-k)
            agg = tools.aggregate_min_max(cand)         # mín/máx + TODOS os empatados, em Python
            want_min = Aggregation.min_year in plan.aggregations  # pediu o mais antigo?
            want_max = Aggregation.max_year in plan.aggregations  # pediu o mais recente?
            # contexto = só o(s) extremo(s) PEDIDO(s) (não narra ambos se só um foi pedido)
            ctx = (agg.get("oldest", []) if want_min else []) + (agg.get("newest", []) if want_max else [])
            seen = set(); context_books = [b for b in ctx if not (b["id"] in seen or seen.add(b["id"]))]  # dedup
            computed_facts = self._facts_aggregation(agg, want_min, want_max)  # vira "FATO" no prompt
            notes.append(f"agregação determinística (min={want_min}, max={want_max})")
        elif plan.group_by == GroupBy.genero:      # Q6: "liste por categoria" -> agrupar em Python
            cand = self.retriever.candidates(plan)      # todos os que passaram no filtro de ano
            groups = tools.group_by_genero(cand)        # {gênero: [livros]}
            context_books = cand                        # o gerador vê todos (narra por categoria)
            computed_facts = self._facts_groups(groups)
            notes.append(f"agrupamento por categoria ({len(groups)} categorias, {len(cand)} livros)")
        elif plan.diversity:                       # Q2: "5 de faixas DIFERENTES" -> diversificar
            cand = self.retriever.candidates(plan)
            div = tools.diversify(cand, field="publico_alvo", n=5)  # 1 por faixa distinta, até 5
            context_books = div["selected"]
            if div["distinct_count"] <= 1:               # o dado só tem 1 faixa? -> ser honesto
                behavior = Behavior.acknowledge_limitation
                extra_directive = (
                    f"O catálogo rotula esses livros em apenas {div['distinct_count']} faixa(s) de "
                    f"público ({', '.join(div['distinct_values'])}). NÃO invente subfaixas etárias; "
                    "explique que essa diferenciação mais fina não existe nos dados."
                )
            notes.append(f"diversidade: {div['distinct_count']} faixa(s) distinta(s)")
        else:                                      # Q1/Q3/Q5/Q7: busca semântica normal
            context_books = [r.book for r in results]    # top-k ranqueado
            ranking_used = True

        # 5) GERAÇÃO ANCORADA (ou degradação graciosa sem LLM). Retorna texto, ids citados e
        #    uma nota (não-vazia se caiu no fallback degradado — observabilidade).
        ts = time.perf_counter()
        answer, cited_ids, gen_note = self._generate(question, context_books, behavior,
                                                     computed_facts, extra_directive, meter)
        timings["generation_ms"] = round((time.perf_counter() - ts) * 1000, 1)
        if gen_note:
            notes.append(gen_note)

        # 6) VERIFICAÇÃO DE CITAÇÕES — a salvaguarda anti-alucinação de citação.
        context_ids = {b["id"] for b in context_books}            # ids que o gerador REALMENTE viu
        verified = [cid for cid in cited_ids if cid in context_ids]      # mantém só citações reais
        dropped = [cid for cid in cited_ids if cid not in context_ids]   # citou algo que não viu?
        if dropped:
            notes.append(f"citações descartadas (não recuperadas): {dropped}")  # registra p/ auditoria
        # Score só faz sentido onde houve RANKING. Nos paths determinísticos (agregação/grupo/
        # diversidade) a seleção é por regra -> dict vazio -> todas as refs ficam com score=None
        # (consistente), em vez de herdar um score do top-k que não foi usado (enganoso).
        score_by_id = {r.book["id"]: r.fused for r in results} if ranking_used else {}
        # Monta as referências finais SÓ a partir dos ids verificados (toda ref é um livro real).
        references = [_book_ref(self.catalog.get(cid), score_by_id.get(cid)) for cid in verified
                      if self.catalog.get(cid)]

        timings["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        resp = AskResponse(
            answer=answer,
            references=references,
            retrieval_debug=RetrievalDebug(
                plan=plan.model_dump(),
                behavior=behavior,
                retrieved_ids=rdebug["retrieved_ids"],
                context_ids=[b["id"] for b in context_books],
                candidate_count=rdebug["candidate_count"],
                top_cosine=rdebug["top_cosine"],
                latency_ms=timings,
                tokens=meter.as_dict(),
                estimated_cost_usd=round(meter.total_cost_usd, 6),
                from_cache=False,
                notes=notes,
            ),
        )
        self._store(key, resp, q_vec)
        return resp

    # ------------------------------------------------------------- helpers
    def _embed_with_cost(self, text: str, meter: Optional[CostMeter]) -> np.ndarray:
        """Embedda `text` e CONTABILIZA o custo (mesmo embeddings sendo baratos) — sem isso o
        teto de custo subestimaria o gasto real (achado COMP-02 da auditoria)."""
        vec = self.index.embed_query(text)
        if meter is not None and self.index.backend != "local":   # backend local não tem custo de API
            meter.add(Usage(config.GEMINI_EMBEDDING_MODEL, input_tokens=max(1, len(text) // 4)))
        return vec

    def _maybe_embed_question(self, q: str, meter: Optional[CostMeter] = None) -> Optional[np.ndarray]:
        """Embedding da pergunta CRUA, usado pelo cache semântico. Retorna None (cache off)
        se a feature está desabilitada, não há índice, ou não há como embeddar (sem chave)."""
        if not config.SEMANTIC_CACHE_ENABLED or self.index.matrix is None:
            return None
        if not (self.client.available or config.EMBEDDINGS_BACKEND == "local"):
            return None
        try:
            return self._embed_with_cost(q, meter)  # 1 embedding curto, contabilizado; None se falhar
        except Exception:
            return None                             # cache é otimização — nunca pode derrubar o /ask

    def _semantic_cache_lookup(self, q_vec: Optional[np.ndarray]) -> Optional[AskResponse]:
        """Procura uma pergunta anterior semanticamente quase idêntica (cosseno >= limiar).
        Itera os candidatos por similaridade DECRESCENTE e usa o 1º acima do limiar que ainda
        exista no cache exato — assim uma entrada stale no topo não suprime um hit válido (NEW-03)."""
        with self._cache_lock:                      # leitura consistente dos caches sob lock
            if q_vec is None or not self._sem_cache:
                return None
            sims = [float(np.dot(q_vec, v)) for v, _ in self._sem_cache]  # cos vs cada entrada (unitários)
            for j in np.argsort(sims)[::-1]:        # do mais parecido p/ o menos
                if sims[j] < config.SEMANTIC_CACHE_THRESHOLD:
                    break                           # abaixo do limiar -> nenhum candidato serve
                k = self._sem_cache[j][1]
                if k in self._cache:                # ignora entradas stale (chave já evicta do exato)
                    out = self._cache[k].model_copy(deep=True)   # cópia isolada (não vaza estado)
                    out.retrieval_debug.from_cache = True
                    out.retrieval_debug.notes = list(out.retrieval_debug.notes) + [
                        f"cache semântico (cos={sims[j]:.3f})"]
                    return out
        return None

    def _store(self, key: str, resp: AskResponse, q_vec: Optional[np.ndarray]) -> None:
        """Guarda no cache exato (cópia isolada) e, p/ comportamentos estáveis, no semântico.
        Não cacheia 'clarify' por similaridade (ambíguo: pergunta parecida pode pedir outro contexto).
        SEGURANÇA: caches LIMITADOS (evicção do mais antigo, anti-DoS de memória) e mutados SOB LOCK
        (o endpoint é sync no threadpool — sem lock, evicção+append concorrentes corromperiam)."""
        with self._cache_lock:
            self._cache[key] = resp.model_copy(deep=True)   # cópia: cache nunca compartilha objeto c/ o chamador
            while len(self._cache) > config.MAX_CACHE_ENTRIES:   # evicção FIFO (dict preserva ordem)
                self._cache.pop(next(iter(self._cache)))
            if q_vec is not None and resp.retrieval_debug.behavior != Behavior.clarify:
                self._sem_cache.append((q_vec, key))
                if len(self._sem_cache) > config.MAX_CACHE_ENTRIES:
                    self._sem_cache.pop(0)

    def _embed_queries(self, plan: RetrievalPlan, meter: Optional[CostMeter] = None) -> Optional[list]:
        """Embeddings das SUB-QUERIES (para o lado semântico do retriever). None -> BM25-only.
        Contabiliza o custo de cada embedding no meter (COMP-02)."""
        if not self.client.available and config.EMBEDDINGS_BACKEND != "local":
            return None  # sem chave e backend remoto -> recuperação cai p/ BM25-only (degradação graciosa)
        try:
            return [self._embed_with_cost(q, meter) for q in (plan.semantic_queries or [])] or None
        except Exception:
            return None  # falha de embedding -> BM25-only, em vez de quebrar

    def _handle_title_lookup(self, question, plan, meter, timings, t0) -> Optional[AskResponse]:
        """Q10 ("vocês têm o livro X?"): checagem DETERMINÍSTICA de pertencimento ao catálogo.
        É a salvaguarda anti-alucinação mais forte — para um livro ausente, nem chamamos o LLM."""
        q = plan.title_lookup + (" " + plan.author_lookup if plan.author_lookup else "")  # título (+ autor)
        matches = self.catalog.find_title(q)        # fuzzy título+autor (token_set + token_sort, anti-fragmento)
        if matches:
            # O livro EXISTE -> aí sim usamos o LLM, com os matches como ÚNICO contexto.
            ts = time.perf_counter()
            answer, cited_ids, _ = self._generate(question, matches, Behavior.answer, None, None, meter)
            timings["generation_ms"] = round((time.perf_counter() - ts) * 1000, 1)
            context_ids = {b["id"] for b in matches}                 # ids do contexto
            verified = [c for c in cited_ids if c in context_ids]    # mantém só citações reais
            refs = [_book_ref(self.catalog.get(c)) for c in verified if self.catalog.get(c)]
            timings["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            return AskResponse(
                answer=answer, references=refs,
                retrieval_debug=RetrievalDebug(
                    plan=plan.model_dump(), behavior=Behavior.answer,
                    retrieved_ids=[b["id"] for b in matches],
                    context_ids=[b["id"] for b in matches], candidate_count=len(matches),
                    latency_ms=timings, tokens=meter.as_dict(),
                    estimated_cost_usd=round(meter.total_cost_usd, 6),
                    notes=["title_lookup: encontrado no catálogo"],
                ),
            )
        # NÃO encontrado -> ABSTENÇÃO determinística, SEM chamar o gerador (custo ~US$0,00008,
        # só o planner). Resposta fixa = zero superfície de alucinação para livro fora do acervo.
        titulo = plan.title_lookup
        autor = f", de {plan.author_lookup}" if plan.author_lookup else ""
        timings["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        return AskResponse(
            answer=(f'Não. O título "{titulo}"{autor} não consta no nosso catálogo. '
                    "Posso sugerir livros parecidos do nosso acervo, se quiser."),
            references=[],
            retrieval_debug=RetrievalDebug(
                plan=plan.model_dump(), behavior=Behavior.abstain,
                retrieved_ids=[], candidate_count=0, latency_ms=timings,
                tokens=meter.as_dict(), estimated_cost_usd=round(meter.total_cost_usd, 6),
                notes=["title_lookup: ausente -> abstenção (curto-circuito, sem LLM)"],
            ),
        )

    def _generate(self, question, context_books, behavior, computed_facts, extra_directive, meter):
        """Geração ancorada. Retorna (answer, cited_ids, note); note != '' sinaliza que caiu na
        degradação (observabilidade — o operador vê que NÃO foi uma geração normal do LLM)."""
        if not self.client.available:               # sem chave -> resposta determinística (template)
            return (self._degraded_answer(context_books, behavior, computed_facts),
                    [b["id"] for b in context_books], "geração degradada: LLM indisponível (sem chave)")
        try:
            # Monta o prompt: dados do catálogo entram ESCAPADOS/delimitados (anti-injeção) + diretivas.
            prompt = build_answer_prompt(question, context_books, behavior, computed_facts, extra_directive)
            # Structured output (response_schema=AnswerOut): JSON garantido pelo schema, sem json.loads
            # manual — o fallback abaixo fica só p/ falha real de rede/indisponibilidade.
            data, usage = self.client.generate_structured(
                ANSWER_SYSTEM, prompt, AnswerOut, model=config.GEMINI_MODEL)
            meter.add(usage)                         # contabiliza tokens/custo da geração
            ans = str(data.get("answer", "")).strip()
            if not ans:                              # NEW-02: answer vazio do schema -> degrada (não entrega em branco)
                return (self._degraded_answer(context_books, behavior, computed_facts),
                        [b["id"] for b in context_books], "geração degradada: answer vazio do LLM")
            return ans, _coerce_id_list(data.get("cited_ids", [])), ""
        except Exception as e:
            # LLM falhou (rede/cota/timeout) -> degradação graciosa COM nota (não mascara a falha).
            # Não vazamos a exceção crua: registramos só o TIPO (não a mensagem, que pode ter detalhes).
            return (self._degraded_answer(context_books, behavior, computed_facts),
                    [b["id"] for b in context_books], f"geração degradada: {type(e).__name__}")

    @staticmethod
    def _degraded_answer(context_books, behavior, computed_facts) -> str:
        """Resposta determinística sem LLM (sem chave/rede). Crua, mas factual e sem alucinação —
        garante que o /ask sempre devolve algo útil mesmo com o Gemini fora do ar."""
        if behavior == Behavior.abstain or not context_books:   # nada relevante / abstenção
            return "Não encontrei nada relevante no catálogo para esse pedido."
        lines = []
        if computed_facts:                            # se houver fatos (agregação/grupo), abre com eles
            lines.append(computed_facts)
        lines.append("Livros relevantes do catálogo (modo sem LLM):")
        for b in context_books[:8]:                   # lista crua dos livros do contexto (cap 8)
            autores = ", ".join(b.get("autores", []))
            lines.append(f"- {b['titulo']} ({b['id']}), {autores}, {b['ano_publicacao']} — "
                         f"{', '.join(b.get('generos', []))} — público: {b.get('publico_alvo','')}")
        return "\n".join(lines)

    @staticmethod
    def _facts_aggregation(agg: dict, want_min: bool = True, want_max: bool = True) -> str:
        """Monta o bloco "FATOS COMPUTADOS" da agregação que o gerador vai NARRAR (não recalcular).
        Inclui só o(s) extremo(s) pedido(s) e SINALIZA o empate quando há vários no máximo."""
        if not agg:
            return ""
        s = []
        if want_min:
            old = agg["oldest"]                      # NEW-04: tratar empate no mais ANTIGO igual ao mais recente
            if len(old) == 1:
                s.append(f"Livro mais ANTIGO: \"{old[0]['titulo']}\" ({old[0]['id']}), {agg['min_year']}.")
            else:
                titulos = "; ".join(f"\"{b['titulo']}\" ({b['id']})" for b in old)
                s.append(f"Mais ANTIGO: há {len(old)} livros EMPATADOS em {agg['min_year']}: {titulos}.")
        if want_max:
            newest = agg["newest"]
            if len(newest) == 1:
                s.append(f"Livro mais RECENTE: \"{newest[0]['titulo']}\" ({newest[0]['id']}), {agg['max_year']}.")
            else:
                titulos = "; ".join(f"\"{b['titulo']}\" ({b['id']})" for b in newest)
                s.append(f"Mais RECENTE: há {len(newest)} livros EMPATADOS em {agg['max_year']}: {titulos}.")
        return " ".join(s)

    @staticmethod
    def _facts_groups(groups) -> str:
        """Bloco "FATOS COMPUTADOS" do agrupamento (Q6): contagem total + livros por categoria."""
        parts = [f"Total de {sum(len(v) for v in groups.values())} livros, por categoria (gênero primário):"]
        for g, books in groups.items():
            titulos = "; ".join(f"\"{b['titulo']}\" ({b['id']}, {b['ano_publicacao']})" for b in books)
            parts.append(f"- {g} ({len(books)}): {titulos}")
        return "\n".join(parts)
