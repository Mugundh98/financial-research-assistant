"""Provider-agnostic LLM client with a deterministic mock fallback.

Default backend is Anthropic Claude. If no API key is configured (or the SDK
isn't importable), :func:`get_llm` returns a :class:`MockLLM` so the whole agent
still runs end-to-end with zero secrets — the orchestrator then composes its
answer deterministically from the gathered evidence.

The LLM is used ONLY to write prose. It never sees or produces the numbers:
those come from deterministic tools, so there is nothing for it to hallucinate.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from ..config import Settings, settings as default_settings
from ..contracts.models import TokenUsage

# Approximate list prices (USD per 1M tokens) for token economics. Override as needed.
PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-4-8": (15.0, 75.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (0.80, 4.0),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-pro-latest": (1.25, 10.0),
    "gemini-flash-latest": (0.30, 2.50),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    p_in, p_out = PRICES.get(model, (3.0, 15.0))
    return input_tokens / 1e6 * p_in + output_tokens / 1e6 * p_out


@dataclass
class LLMResult:
    text: str
    usage: TokenUsage
    model: str
    backend: str


class BaseLLM:
    backend = "base"

    @property
    def is_real(self) -> bool:
        """True for any backend that actually calls a model (not the mock)."""
        return self.backend != "mock"

    def model_for_tier(self, tier: str) -> str:
        """Map a capability tier ('strong'/'fast') to this backend's model id."""
        return self.backend

    def generate(self, system: str, prompt: str, model: str | None = None,
                 max_tokens: int | None = None, temperature: float | None = None) -> LLMResult:
        raise NotImplementedError


class MockLLM(BaseLLM):
    """Deterministic stand-in. Returns empty text so the orchestrator uses its
    own templated answer; records zero-cost usage."""

    backend = "mock"

    def generate(self, system, prompt, model=None, max_tokens=None, temperature=None) -> LLMResult:
        return LLMResult(text="", usage=TokenUsage(model="mock"), model="mock", backend="mock")


class AnthropicLLM(BaseLLM):
    backend = "anthropic"

    def __init__(self, api_key: str, cfg: Settings):
        import anthropic  # imported lazily so the SDK is optional

        self._client = anthropic.Anthropic(api_key=api_key)
        self._cfg = cfg

    def model_for_tier(self, tier: str) -> str:
        return self._cfg.llm_model_fast if tier == "fast" else self._cfg.llm_model_strong

    def generate(self, system, prompt, model=None, max_tokens=None, temperature=None) -> LLMResult:
        model = model or self._cfg.llm_model_strong
        resp = self._client.messages.create(
            model=model,
            system=system,
            max_tokens=max_tokens or self._cfg.llm_max_tokens,
            temperature=self._cfg.llm_temperature if temperature is None else temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        usage = TokenUsage(
            model=model,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            cost_usd=estimate_cost(model, resp.usage.input_tokens, resp.usage.output_tokens),
        )
        return LLMResult(text=text, usage=usage, model=model, backend="anthropic")


class GeminiLLM(BaseLLM):
    """Google Gemini via the REST API (no extra SDK dependency; uses httpx)."""

    backend = "gemini"
    _BASE = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, api_key: str, cfg: Settings):
        self._key = api_key
        self._cfg = cfg
        self._http = httpx.Client(timeout=cfg.request_timeout)

    def model_for_tier(self, tier: str) -> str:
        return self._cfg.gemini_model_fast if tier == "fast" else self._cfg.gemini_model_strong

    def generate(self, system, prompt, model=None, max_tokens=None, temperature=None) -> LLMResult:
        model = model or self._cfg.gemini_model_strong
        url = f"{self._BASE}/models/{model}:generateContent?key={self._key}"
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": self._cfg.llm_temperature if temperature is None else temperature,
                "maxOutputTokens": max_tokens or self._cfg.llm_max_tokens,
            },
        }
        resp = self._http.post(url, json=body)
        resp.raise_for_status()
        data = resp.json()
        text = ""
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", []) or []
            text = "".join(p.get("text", "") for p in parts)
        um = data.get("usageMetadata", {})
        in_tok = um.get("promptTokenCount", 0) or 0
        # 2.5 models bill "thinking" tokens as output.
        out_tok = (um.get("candidatesTokenCount", 0) or 0) + (um.get("thoughtsTokenCount", 0) or 0)
        usage = TokenUsage(model=model, input_tokens=in_tok, output_tokens=out_tok,
                           cost_usd=estimate_cost(model, in_tok, out_tok))
        return LLMResult(text=text, usage=usage, model=model, backend="gemini")


def get_llm(cfg: Settings | None = None) -> BaseLLM:
    """Return the configured backend, falling back to the deterministic mock when
    the chosen provider is unavailable (no key, or SDK/transport issue)."""
    cfg = cfg or default_settings
    backend = (cfg.llm_backend or "mock").lower()
    if backend == "gemini" and cfg.gemini_api_key:
        try:
            return GeminiLLM(cfg.gemini_api_key, cfg)
        except Exception:  # noqa: BLE001
            return MockLLM()
    if backend == "anthropic" and cfg.anthropic_api_key:
        try:
            return AnthropicLLM(cfg.anthropic_api_key, cfg)
        except Exception:  # noqa: BLE001
            return MockLLM()
    return MockLLM()
