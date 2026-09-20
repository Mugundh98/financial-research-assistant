from src.agent.llm import AnthropicLLM, GeminiLLM, MockLLM, get_llm
from src.config import Settings


def test_falls_back_to_mock_without_key():
    assert isinstance(get_llm(Settings(llm_backend="gemini", gemini_api_key=None)), MockLLM)
    assert isinstance(get_llm(Settings(llm_backend="anthropic", anthropic_api_key=None)), MockLLM)
    assert isinstance(get_llm(Settings(llm_backend="mock")), MockLLM)


def test_gemini_selected_with_key():
    llm = get_llm(Settings(llm_backend="gemini", gemini_api_key="x",
                           gemini_model_strong="gemini-2.5-flash",
                           gemini_model_fast="gemini-2.5-flash"))
    assert isinstance(llm, GeminiLLM)
    assert llm.backend == "gemini" and llm.is_real
    assert llm.model_for_tier("strong") == "gemini-2.5-flash"
    assert llm.model_for_tier("fast") == "gemini-2.5-flash"


def test_anthropic_tier_mapping_with_key():
    llm = get_llm(Settings(llm_backend="anthropic", anthropic_api_key="x",
                           llm_model_strong="claude-sonnet-5",
                           llm_model_fast="claude-haiku-4-5-20251001"))
    assert isinstance(llm, AnthropicLLM)
    assert llm.model_for_tier("strong") == "claude-sonnet-5"
    assert llm.model_for_tier("fast") == "claude-haiku-4-5-20251001"


def test_mock_is_not_real():
    m = MockLLM()
    assert m.is_real is False
    assert m.model_for_tier("strong") == "mock"
