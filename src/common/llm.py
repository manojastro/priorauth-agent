"""LLM provider interface. Azure OpenAI (primary), OpenAI-compatible (secondary), FakeLLM (tests).

Every call goes through `complete_json` with a Pydantic schema (structured outputs) and is
recorded in a UsageLedger with tokens, estimated cost and latency.

Cost: prices are NOT hard-coded (they change). Set LLM_PRICE_INPUT_PER_1M and
LLM_PRICE_OUTPUT_PER_1M in .env; when unset, cost is reported as None ("unknown").
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, TypeVar

from pydantic import BaseModel

from src.common.config import Settings, get_settings

log = logging.getLogger("priorauth.llm")
T = TypeVar("T", bound=BaseModel)


@dataclass
class Usage:
    provider: str
    model: str
    step: str
    prompt_tokens: int
    completion_tokens: int
    latency_s: float
    cost_usd: float | None


@dataclass
class UsageLedger:
    calls: list[Usage] = field(default_factory=list)

    def add(self, u: Usage) -> None:
        self.calls.append(u)
        log.info(
            "llm_call provider=%s model=%s step=%s in=%d out=%d latency=%.3fs cost=%s",
            u.provider, u.model, u.step, u.prompt_tokens, u.completion_tokens, u.latency_s,
            "unknown" if u.cost_usd is None else f"{u.cost_usd:.6f}",
        )  # fmt: skip

    def totals(self, since: int = 0) -> dict:
        calls = self.calls[since:]
        costs = [c.cost_usd for c in calls]
        return {
            "calls": len(calls),
            "prompt_tokens": sum(c.prompt_tokens for c in calls),
            "completion_tokens": sum(c.completion_tokens for c in calls),
            "latency_s": round(sum(c.latency_s for c in calls), 4),
            "cost_usd": None if any(c is None for c in costs) else round(sum(costs), 6),
        }


def _price(tokens_in: int, tokens_out: int) -> float | None:
    pin, pout = os.getenv("LLM_PRICE_INPUT_PER_1M"), os.getenv("LLM_PRICE_OUTPUT_PER_1M")
    if not pin or not pout:
        return None
    return tokens_in / 1e6 * float(pin) + tokens_out / 1e6 * float(pout)


class LLM(Protocol):
    name: str
    ledger: UsageLedger

    def complete_json(
        self, *, step: str, system: str, user: str, schema: type[T], context: dict | None = None
    ) -> T: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIChatLLM:
    """Works for Azure OpenAI and any OpenAI-compatible endpoint (openai SDK)."""

    def __init__(self, client, chat_model: str, embed_model: str, name: str):
        self.client = client
        self.chat_model = chat_model
        self.embed_model = embed_model
        self.name = name
        self.ledger = UsageLedger()

    def complete_json(self, *, step, system, user, schema, context=None):
        t0 = time.perf_counter()
        resp = self.client.chat.completions.parse(
            model=self.chat_model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format=schema,
            temperature=0,
        )
        dt = time.perf_counter() - t0
        u = resp.usage
        pin, pout = (u.prompt_tokens, u.completion_tokens) if u else (0, 0)
        self.ledger.add(Usage(self.name, self.chat_model, step, pin, pout, dt, _price(pin, pout)))
        msg = resp.choices[0].message
        if msg.parsed is None:
            raise RuntimeError(f"{step}: model returned no parsed output (refusal={msg.refusal!r})")
        return msg.parsed

    def embed(self, texts):
        resp = self.client.embeddings.create(model=self.embed_model, input=texts)
        return [d.embedding for d in resp.data]


_TOKEN = re.compile(r"[a-z0-9]+")


def hash_embed(text: str, dim: int = 256) -> list[float]:
    """Deterministic bag-of-words hashing embedding. Offline stand-in only."""
    v = [0.0] * dim
    for tok in _TOKEN.findall(text.lower()):
        h = int.from_bytes(hashlib.sha1(tok.encode()).digest()[:4], "big")
        v[h % dim] += 1.0 if (h >> 31) & 1 else -1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


Handler = Callable[[str, dict | None, type[BaseModel]], dict]


class FakeLLM:
    """Offline LLM. `handler(step, context, schema) -> dict` produces the structured output.

    It is not a language model: evals that use it must say so.
    """

    name = "fake"

    def __init__(self, handler: Handler, embed_dim: int = 256):
        self.handler = handler
        self.embed_dim = embed_dim
        self.ledger = UsageLedger()

    def complete_json(self, *, step, system, user, schema, context=None):
        t0 = time.perf_counter()
        out = schema.model_validate(self.handler(step, context, schema))
        self.ledger.add(Usage("fake", "fake", step, 0, 0, time.perf_counter() - t0, 0.0))
        return out

    def embed(self, texts):
        return [hash_embed(t, self.embed_dim) for t in texts]


def get_llm(settings: Settings | None = None, fake_handler: Handler | None = None) -> LLM:
    s = settings or get_settings()
    if s.llm_provider == "azure":
        from openai import AzureOpenAI

        client = AzureOpenAI(
            azure_endpoint=s.azure_openai_endpoint,
            api_key=s.azure_openai_api_key.get_secret_value(),
            api_version=s.azure_openai_api_version,
        )
        return OpenAIChatLLM(
            client, s.azure_openai_chat_deployment, s.azure_openai_embed_deployment, "azure"
        )
    if s.llm_provider == "openai":
        from openai import OpenAI

        client = OpenAI(
            base_url=s.openai_base_url or None, api_key=s.openai_api_key.get_secret_value()
        )
        return OpenAIChatLLM(client, s.llm_model, s.embed_model, "openai")
    if fake_handler is None:
        from src.priorauth.notes import heuristic_handler

        fake_handler = heuristic_handler
    return FakeLLM(fake_handler)
