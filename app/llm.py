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
    model: str
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def cost_usd(self) -> float:
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
        if self._client is None:
            if not self._api_key:
                raise RuntimeError(
                    "GEMINI_API_KEY ausente. Defina no .env para usar geração/embeddings via Gemini."
                )
            from google import genai  # import tardio: só quando há chave
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    # --- Geração estruturada (JSON validado por um modelo Pydantic) ---
    def generate_structured(
        self, system: str, user: str, schema: Type[BaseModel], model: Optional[str] = None
    ) -> tuple[dict, Usage]:
        from google.genai import types

        model = model or config.GEMINI_PLANNER_MODEL
        client = self._ensure()
        resp = client.models.generate_content(
            model=model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=config.LLM_TEMPERATURE,
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        usage = self._usage(model, resp)
        # resp.parsed é uma instância do schema quando o parse interno funciona.
        data: dict
        if getattr(resp, "parsed", None) is not None:
            parsed = resp.parsed
            data = parsed.model_dump() if isinstance(parsed, BaseModel) else dict(parsed)
        else:
            data = json.loads(resp.text)  # pode lançar; o chamador trata
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

        model = model or config.GEMINI_EMBEDDING_MODEL
        dim = dim or config.EMBEDDING_DIM
        client = self._ensure()
        out: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            chunk = texts[start : start + batch_size]
            cfg = types.EmbedContentConfig(task_type=task_type, output_dimensionality=dim)
            try:
                resp = client.models.embed_content(model=model, contents=chunk, config=cfg)
                out.extend([list(e.values) for e in resp.embeddings])
            except Exception:
                # Fallback: alguns endpoints aceitam só 1 conteúdo por chamada.
                for t in chunk:
                    resp = client.models.embed_content(model=model, contents=t, config=cfg)
                    out.extend([list(e.values) for e in resp.embeddings])
        return out

    @staticmethod
    def _usage(model: str, resp) -> Usage:
        um = getattr(resp, "usage_metadata", None)
        return Usage(
            model=model,
            input_tokens=getattr(um, "prompt_token_count", 0) or 0,
            output_tokens=getattr(um, "candidates_token_count", 0) or 0,
        )


_client: Optional[GeminiClient] = None


def get_client() -> GeminiClient:
    global _client
    if _client is None:
        _client = GeminiClient()
    return _client
