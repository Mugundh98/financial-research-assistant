from src.agent.planning import plan_query, tool_requests


def test_compare_intent_and_tickers(corpus):
    p = plan_query("How fast is NVIDIA revenue growing vs Microsoft?", corpus.companies)
    assert p.intent == "compare"
    assert set(p.tickers) == {"NVDA", "MSFT"}


def test_advice_detection(corpus):
    p = plan_query("Should I buy Apple stock?", corpus.companies)
    assert p.is_advice is True
    assert "AAPL" in p.tickers


def test_risks_intent(corpus):
    p = plan_query("What are the main risks facing NVIDIA?", corpus.companies)
    assert p.intent == "risks" and p.tickers == ["NVDA"]


def test_scenario_intent_requests_compare_scenarios(corpus):
    p = plan_query("Project Microsoft revenue over 3 years", corpus.companies)
    assert p.intent == "scenario"
    assert any(name == "compare_scenarios" for name, _ in tool_requests(p))


def test_no_company_gives_empty_tickers(corpus):
    p = plan_query("What is the weather today?", corpus.companies)
    assert p.tickers == []
