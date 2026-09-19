import pytest

from src.contracts.models import AnalysisResult, Company, FinancialFact


def test_cik_is_zero_padded():
    assert Company(cik="320193", name="Apple").cik == "0000320193"
    assert Company(cik=789019, name="Microsoft").cik == "0000789019"


def test_extra_fields_forbidden():
    with pytest.raises(Exception):
        Company(cik="1", name="X", bogus_field=123)


def test_financialfact_defaults_approved():
    f = FinancialFact(id="i", cik="0000320193", concept="Revenues", value=1.0)
    assert f.approved is True
    assert f.source == "SEC EDGAR"


def test_analysisresult_minimal():
    r = AnalysisResult(query_id="q1", query="hello")
    assert r.findings == [] and r.confidence == 0.0 and r.refused is False
