"""Camada de LLM: clientes (Gemini direto e OpenRouter roteado), cache de CHAMADAS,
contabilidade de tokens/custo e fábricas (cliente de chat vs embedder).

Backends de CHAT (planner/geração/juiz) — escolhidos por LLM_BACKEND:
- ``GeminiClient``: SDK google-genai (structured output nativo via response_schema).
- ``OpenRouterClient``: ROTEAMENTO DE MODELOS (https://openrouter.ai) sobre a API
  OpenAI-compatível — troca de modelo/provedor por .env (sem deploy), FALLBACK automático
  entre modelos ("models": [...]), juiz de OUTRA família (mitiga viés de auto-avaliação)
  e custo REAL devolvido na própria resposta (usage.cost -> Usage.cost_override).

EMBEDDINGS ficam SEMPRE no Gemini (``get_embedder``) ou no backend local: o OpenRouter não
expõe endpoint de embeddings — roteamos apenas o chat. Centralizar tudo aqui mantém o resto
do código agnóstico ao provedor e facilita medir custo por requisição.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Optional, Type, Union

from pydantic import BaseModel

from . import config


@dataclass
class Usage:
    """Uso de UMA chamada ao LLM. Carregamos o `model` junto porque planner e gerador
    usam modelos diferentes (preços diferentes) — o custo precisa saber de qual modelo veio.
    `cost_override`: custo REAL informado pela API (o OpenRouter devolve usage.cost) — quando
    presente, vale mais que a tabela de preços. `cached=True` marca hit do cache de chamadas
    (tokens 0, custo 0 — a chamada original já foi paga)."""
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_override: Optional[float] = None
    cached: bool = False

    @property
    def cost_usd(self) -> float:
        if self.cost_override is not None:   # custo real reportado pela API tem precedência
            return self.cost_override
        # Preço das tabelas é por 1 MILHÃO de tokens -> dividimos por 1e6.
        # Mantemos o custo no código (não só no README) para expô-lo no retrieval_debug
        # de cada resposta: transparência de custo é requisito do desafio.
        p = config.price_for(self.model)
        return (self.input_tokens * p["input"] + self.output_tokens * p["output"]) / 1_000_000


@dataclass
class CostMeter:
    """Acumula uso de várias chamadas (uma requisição /ask pode ter planner + gerador)."""
    usages: list[Usage] = field(default_factory=list)

    def add(self, usage: Usage) -> None:
        self.usages.append(usage)

    @property
    def total_input(self) -> int:
        return sum(u.input_tokens for u in self.usages)

    @property
    def total_output(self) -> int:
        return sum(u.output_tokens for u in self.usages)

    @property
    def total_cost_usd(self) -> float:
        return sum(u.cost_usd for u in self.usages)

    def as_dict(self) -> dict:
        return {
            "input_tokens": self.total_input,
            "output_tokens": self.total_output,
            "calls": [{"model": u.model, "in": u.input_tokens, "out": u.output_tokens,
                       **({"cached": True} if u.cached else {})} for u in self.usages],
        }


# ---------------------------------------------------------------------------
# Cache de CHAMADAS ao LLM (economia de tokens — ver docs/economia_de_tokens.md)
# ---------------------------------------------------------------------------
class LLMCache:
    """Cache POR CHAMADA (chave = backend|modelo|temperatura|tipo|system|user), uma camada
    ABAIXO dos caches de resposta do pipeline: pega repetições que eles não veem — re-rodar
    eval/judge, regerar cartões de contexto, a mesma sub-chamada vinda de perguntas diferentes.
    temperature=0 torna a chamada determinística, então cachear é seguro (mesma entrada =>
    mesma saída). Em memória LIMITADO (evicção FIFO, anti-DoS — mesmo padrão dos caches do
    pipeline) e mutado SOB LOCK (o /ask roda no threadpool). Persistência OPCIONAL em disco
    (LLM_CACHE_PERSIST) para reaproveitar entre PROCESSOS: 1 arquivo por entrada (escritas
    independentes — sem corrupção por concorrência, sem lock de arquivo)."""

    def __init__(self):
        self._mem: dict[str, dict] = {}
        self._lock = threading.Lock()

    @staticmethod
    def key(backend: str, model: str, kind: str, system: str, user: str) -> str:
        # Temperatura entra na chave: mudou o sampling, muda a resposta esperada.
        blob = "␟".join([backend, model, str(config.LLM_TEMPERATURE), kind, system, user])
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def get(self, k: str) -> Optional[dict]:
        if not config.LLM_CACHE_ENABLED:
            return None
        with self._lock:
            if k in self._mem:
                return self._mem[k]
        if config.LLM_CACHE_PERSIST:                 # miss em memória -> tenta o disco
            p = config.LLM_CACHE_DIR / f"{k[:32]}.json"
            try:
                if p.exists():
                    val = json.loads(p.read_text(encoding="utf-8"))
                    self.put(k, val, persist=False)  # promove p/ memória (sem reescrever o disco)
                    return val
            except Exception:
                return None                          # cache é otimização — nunca derruba a chamada
        return None

    def put(self, k: str, value: dict, persist: bool = True) -> None:
        if not config.LLM_CACHE_ENABLED:
            return
        with self._lock:
            self._mem[k] = value
            while len(self._mem) > config.LLM_CACHE_MAX_ENTRIES:  # evicção FIFO (dict preserva ordem)
                self._mem.pop(next(iter(self._mem)))
        if persist and config.LLM_CACHE_PERSIST:
            try:
                config.LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                (config.LLM_CACHE_DIR / f"{k[:32]}.json").write_text(
                    json.dumps(value, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass                                 # disco é otimização — falha silenciosa

    def clear(self) -> None:
        with self._lock:
            self._mem.clear()


_llm_cache = LLMCache()


def _cached_usage(model: str) -> Usage:
    """Usage de um HIT do cache de chamadas: tokens 0 e custo 0 (o gasto já aconteceu na
    chamada original) — assim o retrieval_debug mostra o custo MARGINAL real da requisição."""
    return Usage(model=model, cached=True, cost_override=0.0)


# ---------------------------------------------------------------------------
# Helpers de JSON (compartilhados pelos dois backends)
# ---------------------------------------------------------------------------
def _extract_json_text(text: str) -> str:
    """Isola o JSON de uma resposta de chat: remove cercas de código (```json ... ```) e
    recorta do 1º '{' ao último '}'. Modelos sem constrained decoding às vezes embrulham o
    JSON em prosa/markdown; o conteúdo em si fica intacto."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t)
    i, j = t.find("{"), t.rfind("}")
    return t[i:j + 1] if i != -1 and j > i else t


def _strict_json_schema(schema: Type[BaseModel]) -> dict:
    """Converte o JSON Schema do Pydantic para o modo STRICT do response_format
    OpenAI-compatível: todo objeto fecha additionalProperties=false e lista TODAS as
    propriedades em required (exigência do modo estrito; campos opcionais continuam
    aceitando null via anyOf do Pydantic). Removemos "default" (keyword fora do core
    que alguns provedores rejeitam no modo estrito)."""
    import copy
    root = copy.deepcopy(schema.model_json_schema())

    def walk(node) -> None:
        if isinstance(node, dict):
            node.pop("default", None)
            if "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"].keys())
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(root)
    return root


# ---------------------------------------------------------------------------
# Backend 1: Gemini direto (SDK google-genai)
# ---------------------------------------------------------------------------
class GeminiClient:
    """Cliente único do Gemini. Inicializa preguiçosamente para que o app suba
    mesmo sem chave (partes determinísticas continuam funcionando). Além do chat,
    é o ÚNICO backend de embeddings remotos (o OpenRouter não embedda)."""

    backend = "gemini"

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key if api_key is not None else config.GEMINI_API_KEY
        self._client = None

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    # Modelos por PAPEL (planner/geração/juiz) e por PESO (light/heavy) — o roteamento
    # inteligente (pipeline.route_generation_model) escolhe entre eles pela complexidade
    # da solicitação. Centralizar aqui deixa os call sites agnósticos ao backend.
    @property
    def planner_model(self) -> str:
        return config.GEMINI_PLANNER_MODEL

    @property
    def generation_model(self) -> str:
        return config.GEMINI_MODEL

    @property
    def light_model(self) -> str:
        return config.GEMINI_MODEL_LIGHT or config.GEMINI_PLANNER_MODEL

    @property
    def heavy_model(self) -> str:
        return config.GEMINI_MODEL_HEAVY or config.GEMINI_MODEL

    @property
    def judge_model(self) -> str:
        return config.GEMINI_JUDGE_MODEL

    def _ensure(self):
        # Inicialização preguiçosa: criamos o cliente só na 1ª chamada real ao Gemini.
        # Motivo: a API, a UI e os testes precisam SUBIR mesmo sem chave (modo degradado /
        # BM25-only). Se inicializássemos no __init__, faltar a chave derrubaria tudo.
        if self._client is None:
            if not self._api_key:
                raise RuntimeError(
                    "GEMINI_API_KEY ausente. Defina no .env para usar geração/embeddings via Gemini."
                )
            from google import genai  # import tardio: só quando há chave (e evita custo de import sem uso)
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    # --- Geração estruturada (JSON validado por um modelo Pydantic) ---
    def generate_structured(
        self, system: str, user: str, schema: Type[BaseModel], model: Optional[str] = None
    ) -> tuple[dict, Usage]:
        """Usa `response_schema` (constrained decoding): o Gemini compila o schema Pydantic
        numa gramática e GARANTE JSON válido na forma esperada — em vez de pedir 'responda em
        JSON' e torcer. É o que o planner e a geração de resposta usam para não depender de
        parsing frágil. `model` default = planner (mais barato); o gerador passa o modelo forte."""
        from google.genai import types

        model = model or self.planner_model
        ck = LLMCache.key(self.backend, model, f"structured:{schema.__name__}", system, user)
        hit = _llm_cache.get(ck)
        if hit is not None:                          # repetição determinística -> custo marginal 0
            return dict(hit["data"]), _cached_usage(model)
        client = self._ensure()
        resp = client.models.generate_content(
            model=model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=config.LLM_TEMPERATURE,  # 0 -> determinístico (avaliação/demo reproduzíveis)
                # Teto de SAÍDA por chamada: bound de custo (economia de tokens). 0 -> sem teto.
                max_output_tokens=(config.LLM_MAX_OUTPUT_TOKENS or None),
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        usage = self._usage(model, resp)
        # Caminho feliz: o SDK já devolve a instância validada em resp.parsed. Caímos para
        # json.loads(resp.text) só se o parse interno falhar (raro) — pode lançar, e o
        # chamador (planner/pipeline) trata com fallback determinístico/degradação graciosa.
        data: dict
        if getattr(resp, "parsed", None) is not None:
            parsed = resp.parsed
            data = parsed.model_dump() if isinstance(parsed, BaseModel) else dict(parsed)
        else:
            data = json.loads(resp.text)
        _llm_cache.put(ck, {"data": data})
        return data, usage

    # --- Geração de texto (resposta ancorada / juiz) ---
    def generate_text(
        self, system: str, user: str, model: Optional[str] = None, as_json: bool = False
    ) -> tuple[str, Usage]:
        from google.genai import types

        model = model or self.generation_model
        ck = LLMCache.key(self.backend, model, f"text:{as_json}", system, user)
        hit = _llm_cache.get(ck)
        if hit is not None:
            return str(hit["text"]), _cached_usage(model)
        client = self._ensure()
        cfg = types.GenerateContentConfig(
            system_instruction=system,
            temperature=config.LLM_TEMPERATURE,
            max_output_tokens=(config.LLM_MAX_OUTPUT_TOKENS or None),
        )
        if as_json:
            cfg.response_mime_type = "application/json"
        resp = client.models.generate_content(model=model, contents=user, config=cfg)
        text = resp.text or ""
        _llm_cache.put(ck, {"text": text})
        return text, self._usage(model, resp)

    # --- Embeddings ---
    def embed(
        self,
        texts: list[str],
        task_type: str,
        model: Optional[str] = None,
        dim: Optional[int] = None,
        batch_size: int = 50,
    ) -> list[list[float]]:
        from google.genai import types

        # task_type é ASSIMÉTRICO de propósito: o gemini-embedding-001 rende mais quando o
        # corpus é embeddado como RETRIEVAL_DOCUMENT e a consulta como RETRIEVAL_QUERY (quem
        # chama escolhe). output_dimensionality=768 (MRL): 4x menos storage que 3072 e ótimo p/ 200 docs.
        model = model or config.GEMINI_EMBEDDING_MODEL
        dim = dim or config.EMBEDDING_DIM
        client = self._ensure()
        out: list[list[float]] = []
        # Batelamos (batch_size) para reduzir round-trips ao indexar 200 livros de uma vez.
        for start in range(0, len(texts), batch_size):
            chunk = texts[start : start + batch_size]
            cfg = types.EmbedContentConfig(task_type=task_type, output_dimensionality=dim)
            try:
                resp = client.models.embed_content(model=model, contents=chunk, config=cfg)
                out.extend([list(e.values) for e in resp.embeddings])
            except Exception:
                # Robustez: algumas versões do endpoint aceitam só 1 conteúdo por chamada.
                # Em vez de quebrar o batch inteiro, reembeddamos item a item.
                for t in chunk:
                    resp = client.models.embed_content(model=model, contents=t, config=cfg)
                    out.extend([list(e.values) for e in resp.embeddings])
        return out

    @staticmethod
    def _usage(model: str, resp) -> Usage:
        # getattr defensivo: se o SDK não popular usage_metadata numa versão, contamos 0
        # em vez de quebrar — custo é observabilidade, não pode derrubar a resposta.
        um = getattr(resp, "usage_metadata", None)
        return Usage(
            model=model,
            input_tokens=getattr(um, "prompt_token_count", 0) or 0,
            output_tokens=getattr(um, "candidates_token_count", 0) or 0,
        )


# ---------------------------------------------------------------------------
# Backend 2: OpenRouter (roteamento de modelos, API OpenAI-compatível)
# ---------------------------------------------------------------------------
class OpenRouterClient:
    """Cliente do OpenRouter — camada de ROTEAMENTO sobre /chat/completions. O que ganhamos:
    - trocar modelo/provedor por .env (slugs "provedor/modelo"; "openrouter/auto" delega);
    - FALLBACK automático entre modelos (payload "models": o roteador tenta o próximo se o
      primário falhar/estiver fora) — resiliência de demo sem retry manual;
    - roteamento de PROVEDOR por preço/vazão/latência (provider.sort);
    - juiz de OUTRA família de modelo (anti viés de auto-avaliação);
    - custo REAL por chamada na resposta (usage.cost), em vez de tabela manual.
    NÃO expõe embeddings (o OpenRouter não tem esse endpoint) — embeddings ficam no
    GeminiClient (get_embedder) ou no backend local. Interface espelha o GeminiClient
    (duck-typing), então pipeline/planner/juiz não sabem qual backend está ativo."""

    backend = "openrouter"

    def __init__(self, api_key: Optional[str] = None, http=None):
        self._api_key = api_key if api_key is not None else config.OPENROUTER_API_KEY
        self._http = http  # injetável nos testes (httpx.Client com MockTransport)

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    @property
    def planner_model(self) -> str:
        return config.OPENROUTER_PLANNER_MODEL

    @property
    def generation_model(self) -> str:
        return config.OPENROUTER_MODEL

    @property
    def light_model(self) -> str:
        return config.OPENROUTER_MODEL_LIGHT or config.OPENROUTER_PLANNER_MODEL

    @property
    def heavy_model(self) -> str:
        return config.OPENROUTER_MODEL_HEAVY or config.OPENROUTER_MODEL

    @property
    def judge_model(self) -> str:
        return config.OPENROUTER_JUDGE_MODEL

    # --- infra HTTP ---
    def _ensure(self):
        if not self._api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY ausente. Defina no .env para rotear o chat via OpenRouter."
            )
        if self._http is None:
            import httpx  # import tardio (mesma razão do SDK do Gemini)
            self._http = httpx.Client(base_url=config.OPENROUTER_BASE_URL,
                                      timeout=config.LLM_TIMEOUT_S)
        return self._http

    def _payload(self, system: str, user: str, model: str, response_format: Optional[dict] = None) -> dict:
        p: dict = {
            "model": model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": config.LLM_TEMPERATURE,
            "usage": {"include": True},   # devolve tokens E o custo real (USD) na resposta
        }
        if config.LLM_MAX_OUTPUT_TOKENS:  # teto de saída = bound de custo por chamada
            p["max_tokens"] = config.LLM_MAX_OUTPUT_TOKENS
        if config.OPENROUTER_FALLBACK_MODELS:
            # Lista ordenada primário -> alternativas: o OpenRouter tenta o próximo quando o
            # anterior falha/está indisponível (roteamento com fallback, sem código extra aqui).
            p["models"] = [model] + [m for m in config.OPENROUTER_FALLBACK_MODELS if m != model]
        provider: dict = {}
        if response_format is not None:
            p["response_format"] = response_format
            provider["require_parameters"] = True  # só roteia p/ provedores que HONRAM o schema
        if config.OPENROUTER_SORT in ("price", "throughput", "latency"):
            provider["sort"] = config.OPENROUTER_SORT
        if provider:
            p["provider"] = provider
        return p

    def _chat(self, payload: dict) -> dict:
        http = self._ensure()
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "X-Title": config.OPENROUTER_APP_TITLE,  # atribuição opcional no painel do OpenRouter
        }
        # 1 retry só para erros TRANSITÓRIOS (429/5xx) — resiliência de demo; erros de payload
        # (4xx) sobem direto para o chamador decidir (ex.: repetir sem response_format).
        for attempt in (1, 2):
            r = http.post("/chat/completions", json=payload, headers=headers)
            if r.status_code in (429, 500, 502, 503) and attempt == 1:
                time.sleep(1.0)
                continue
            break
        r.raise_for_status()
        return r.json()

    @staticmethod
    def _content(data: dict) -> str:
        return ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""

    @staticmethod
    def _usage(requested: str, data: dict) -> Usage:
        u = data.get("usage") or {}
        cost = u.get("cost")
        return Usage(
            # O campo "model" da resposta diz qual modelo REALMENTE atendeu (pode ser um
            # fallback da lista "models") — observabilidade do roteamento no retrieval_debug.
            model=data.get("model") or requested,
            input_tokens=int(u.get("prompt_tokens") or 0),
            output_tokens=int(u.get("completion_tokens") or 0),
            cost_override=float(cost) if cost is not None else None,
        )

    # --- Geração estruturada (JSON Schema estrito; fallback sem schema p/ modelos sem suporte) ---
    def generate_structured(
        self, system: str, user: str, schema: Type[BaseModel], model: Optional[str] = None
    ) -> tuple[dict, Usage]:
        model = model or self.planner_model
        ck = LLMCache.key(self.backend, model, f"structured:{schema.__name__}", system, user)
        hit = _llm_cache.get(ck)
        if hit is not None:
            return dict(hit["data"]), _cached_usage(model)
        rf = {"type": "json_schema",
              "json_schema": {"name": schema.__name__, "strict": True,
                              "schema": _strict_json_schema(schema)}}
        try:
            data = self._chat(self._payload(system, user, model, response_format=rf))
        except Exception as e:
            # Modelo/provedor sem suporte a json_schema (ou schema rejeitado): repete SEM o
            # response_format — os prompts já exigem "somente JSON" e o parse abaixo limpa
            # cercas. Erros reais (rede/auth/cota) sobem p/ o chamador degradar graciosamente.
            sc = getattr(getattr(e, "response", None), "status_code", None)
            if sc not in (400, 404, 405, 422):
                raise
            data = self._chat(self._payload(system, user, model))
        out = json.loads(_extract_json_text(self._content(data)))
        _llm_cache.put(ck, {"data": out})
        return out, self._usage(model, data)

    # --- Geração de texto (juiz) ---
    def generate_text(
        self, system: str, user: str, model: Optional[str] = None, as_json: bool = False
    ) -> tuple[str, Usage]:
        model = model or self.generation_model
        ck = LLMCache.key(self.backend, model, f"text:{as_json}", system, user)
        hit = _llm_cache.get(ck)
        if hit is not None:
            return str(hit["text"]), _cached_usage(model)
        data = self._chat(self._payload(system, user, model))
        text = self._content(data)
        if as_json:
            # Sem constrained decoding aqui (nem todo provedor suporta): limpamos cercas de
            # código para o json.loads do chamador (judge.py) funcionar com qualquer família.
            text = _extract_json_text(text)
        _llm_cache.put(ck, {"text": text})
        return text, self._usage(model, data)


# Tipo do cliente de chat (duck-typing — os dois expõem a mesma interface).
ChatClient = Union[GeminiClient, OpenRouterClient]

# Singletons de processo: um cliente de CHAT (roteado conforme LLM_BACKEND) e um EMBEDDER
# (sempre Gemini — o OpenRouter não embedda). A pipeline pode injetar clientes nos testes.
_client: Optional[ChatClient] = None
_embedder: Optional[GeminiClient] = None


def get_client() -> ChatClient:
    """Cliente de CHAT (planner/geração/juiz) conforme LLM_BACKEND:
    "auto" -> OpenRouter se houver OPENROUTER_API_KEY; senão Gemini direto."""
    global _client
    if _client is None:
        use_openrouter = config.LLM_BACKEND == "openrouter" or (
            config.LLM_BACKEND == "auto" and bool(config.OPENROUTER_API_KEY)
        )
        _client = OpenRouterClient() if use_openrouter else GeminiClient()
    return _client


def get_embedder() -> GeminiClient:
    """Cliente usado SÓ para embeddings (índice + consultas). Mesmo com o chat roteado pelo
    OpenRouter, embeddings continuam no Gemini (ou no backend local) — não há endpoint de
    embeddings no roteador. Reusa o cliente de chat quando ele já é um GeminiClient."""
    global _embedder
    if _embedder is None:
        c = get_client()
        _embedder = c if isinstance(c, GeminiClient) else GeminiClient()
    return _embedder
