import pytest

from src.retrieval import FactStore


@pytest.fixture(scope="session")
def fs(corpus):
    return FactStore(corpus.facts, corpus.companies)


def test_fiscal_year_derived_from_period_end(fs):
    f = next(x for x in fs.series("revenue", ticker="AAPL") if x.fiscal_year == 2024)
    assert f.value == 391035000000
    assert f.period_end.year == 2024


def test_series_sorted_and_annual(fs):
    ser = fs.series("revenue", ticker="MSFT")
    years = [x.fiscal_year for x in ser]
    assert years == sorted(years)
    assert all(x.period_type == "annual" for x in ser)


def test_latest_revenue_is_recent_and_large(fs):
    f = fs.latest("revenue", ticker="AAPL")
    assert f.fiscal_year >= 2024
    assert f.value > 3e11


def test_instant_metric_uses_year_end_balance(fs):
    f = fs.latest("assets", ticker="AAPL")
    assert f is not None and f.period_type == "instant"


def test_ticker_resolution(fs):
    assert fs.resolve_cik(ticker="NVDA") == "0001045810"
