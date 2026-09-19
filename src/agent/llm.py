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

from ..config import Settings, settings as default_settings
from ..contracts.models import TokenUsage

# Approximate list prices (USD per 1M tokens) for token economics. Override as needed.
PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-4-8": (15.0, 75.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (0.80, 4.0),
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


def get_llm(cfg: Settings | None = None) -> BaseLLM:
    """Return the configured backend, falling back to the mock when Claude is
    unavailable (no key, or SDK not importable)."""
    cfg = cfg or default_settings
    if cfg.llm_backend == "anthropic" and cfg.anthropic_api_key:
        try:
            return AnthropicLLM(cfg.anthropic_api_key, cfg)
        except Exception:  # noqa: BLE001 - any SDK/import/config issue -> mock
            return MockLLM()
    return MockLLM()
