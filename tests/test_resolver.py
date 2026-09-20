from src.ingestion.resolver import TickerResolver, extract_candidate_tickers


def test_extract_uppercase_and_alias():
    cands = extract_candidate_tickers("Compare AAPL and Tesla, ignoring the SEC and EPS")
    assert "AAPL" in cands       # explicit ticker
    assert "TSLA" in cands       # alias "Tesla"
    assert "SEC" not in cands    # stoplisted acronym
    assert "EPS" not in cands


def test_titlecase_fake_name_yields_no_candidate():
    # Title-case words are not all-caps tokens, so they don't look like tickers.
    assert extract_candidate_tickers("What is the revenue of Zzxqqmax Holdings?") == set()


class _StubClient:
    """Stands in for SECClient.company_tickers() without network."""
    def company_tickers(self):
        return {"0": {"ticker": "TSLA", "cik_str": 1318605, "title": "Tesla, Inc."}}


def test_resolver_maps_alias_to_cik():
    out = TickerResolver(_StubClient()).resolve("tell me about Tesla")
    assert out == [("0001318605", "TSLA")]


def test_resolver_ignores_unknown_ticker():
    assert TickerResolver(_StubClient()).resolve("what about ZZZZZ") == []
