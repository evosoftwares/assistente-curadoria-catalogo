"""Wrapper fino sobre o SDK google-genai: geração estruturada/texto, embeddings
e contabilidade de tokens/custo. Centralizar aqui mantém o resto do código agnóstico
ao SDK e facilita medir custo por requisição.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Optional, Type

from pydantic import BaseModel

from . import config


@dataclass
class Usage:
    """Uso de UMA chamada ao LLM. Carregamos o `model` junto porque planner e gerador
    usam modelos diferentes (preços diferentes) — o custo precisa saber de qual modelo veio."""
    model: str
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def cost_usd(self) -> float:
        # Preço das tabelas do Gemini é por 1 MILHÃO de tokens -> dividimos por 1e6.
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
            "calls": [{"model": u.model, "in": u.input_tokens, "out": u.output_tokens} for u in self.usages],
        }


class GeminiClient:
    """Cliente único do Gemini. Inicializa preguiçosamente para que o app suba
    mesmo sem chave (partes determinísticas continuam funcionando)."""

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key if api_key is not None else config.GEMINI_API_KEY
        self._client = None

    @property
    def available(self) -> bool:
        return bool(self._api_key)

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

        model = model or config.GEMINI_PLANNER_MODEL
        client = self._ensure()
        resp = client.models.generate_content(
            model=model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=config.LLM_TEMPERATURE,  # 0 -> determinístico (avaliação/demo reproduzíveis)
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
        return data, usage

    # --- Geração de texto (resposta ancorada / juiz) ---
    def generate_text(
        self, system: str, user: str, model: Optional[str] = None, as_json: bool = False
    ) -> tuple[str, Usage]:
        from google.genai import types

        model = model or config.GEMINI_MODEL
        client = self._ensure()
        cfg = types.GenerateContentConfig(
            system_instruction=system,
            temperature=config.LLM_TEMPERATURE,
        )
        if as_json:
            cfg.response_mime_type = "application/json"
        resp = client.models.generate_content(model=model, contents=user, config=cfg)
        return (resp.text or ""), self._usage(model, resp)

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


# Singleton de processo: um cliente Gemini compartilhado por toda a app (evita recriar o
# cliente/conexão a cada requisição). A pipeline pode injetar um cliente próprio nos testes.
_client: Optional[GeminiClient] = None


def get_client() -> GeminiClient:
    global _client
    if _client is None:
        _client = GeminiClient()
    return _client
