from types import SimpleNamespace

from src.storage import AppDB


def _result(**kw):
    base = dict(confidence=0.85, model_used="mock", refused=False, query_id="q1",
                usage=SimpleNamespace(cost_usd=0.0))
    base.update(kw)
    return SimpleNamespace(**base)


def test_record_and_tally(tmp_path):
    db = AppDB(path=tmp_path / "t.db")
    db.upsert_user("a@x.com", "Alice")
    db.record_query("a@x.com", "aapl revenue", ["AAPL"], intent="metric",
                    result=_result(), companies={"AAPL": "Apple Inc."})
    db.record_query("a@x.com", "compare aapl msft", ["AAPL", "MSFT"], intent="compare",
                    result=_result())

    tickers = {t["ticker"]: t for t in db.get_user_tickers("a@x.com")}
    assert tickers["AAPL"]["count"] == 2          # queried twice
    assert tickers["MSFT"]["count"] == 1
    assert tickers["AAPL"]["last_company"] == "Apple Inc."

    history = db.get_history("a@x.com")
    assert len(history) == 2
    assert history[0]["query"] == "compare aapl msft"   # newest first
    assert db.stats()["users"] == 1

    # per-user stats are isolated to that user
    stats = db.user_stats("a@x.com")
    assert stats["queries"] == 2 and stats["tickers"] == 2
    assert db.user_stats("someone-else@x.com")["queries"] == 0


def test_users_listing_and_isolation(tmp_path):
    db = AppDB(path=tmp_path / "t2.db")
    db.upsert_user("b@x.com")
    db.record_query("b@x.com", "nvda", ["NVDA"], intent="metric", result=_result())
    assert any(u["email"] == "b@x.com" for u in db.all_users())
    # a different user has no tickers
    assert db.get_user_tickers("nobody@x.com") == []
