"""Local per-user storage (SQLite, standard-library only).

Persists who used the assistant and which tickers/queries they ran, so a user's
activity can be reviewed or queried later. Deliberately simple and
dependency-free (a real deployment would swap in Postgres behind the same API).

Tables:
  users         - one row per signed-in user
  query_history - one row per query a user runs
  user_tickers  - per-user tally of every ticker they've looked at
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..config import settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AppDB:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path or (settings.data_dir / "app.db"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    email TEXT PRIMARY KEY,
                    name TEXT,
                    created_at TEXT,
                    last_login TEXT
                );
                CREATE TABLE IF NOT EXISTS query_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT, ts TEXT, query TEXT, tickers TEXT, intent TEXT,
                    refused INTEGER, confidence REAL, model TEXT, cost_usd REAL, query_id TEXT
                );
                CREATE TABLE IF NOT EXISTS user_tickers (
                    email TEXT, ticker TEXT, count INTEGER,
                    first_seen TEXT, last_seen TEXT, last_company TEXT,
                    PRIMARY KEY (email, ticker)
                );
                """
            )

    # ---- writes ----------------------------------------------------------- #
    def upsert_user(self, email: str, name: Optional[str] = None) -> None:
        now = _now()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """INSERT INTO users(email, name, created_at, last_login) VALUES(?,?,?,?)
                   ON CONFLICT(email) DO UPDATE SET
                       last_login=excluded.last_login,
                       name=COALESCE(excluded.name, users.name)""",
                (email, name, now, now),
            )

    def record_query(self, email: str, query: str, tickers: list[str],
                     intent: Optional[str] = None, result=None,
                     companies: Optional[dict[str, str]] = None) -> None:
        now = _now()
        conf = getattr(result, "confidence", None)
        model = getattr(result, "model_used", None)
        refused = 1 if getattr(result, "refused", False) else 0
        usage = getattr(result, "usage", None)
        cost = getattr(usage, "cost_usd", 0.0) or 0.0
        qid = getattr(result, "query_id", None)
        companies = companies or {}
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """INSERT INTO query_history
                   (email, ts, query, tickers, intent, refused, confidence, model, cost_usd, query_id)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (email, now, query, ",".join(tickers), intent, refused, conf, model, cost, qid),
            )
            for tk in tickers:
                conn.execute(
                    """INSERT INTO user_tickers(email, ticker, count, first_seen, last_seen, last_company)
                       VALUES(?,?,1,?,?,?)
                       ON CONFLICT(email, ticker) DO UPDATE SET
                           count=user_tickers.count+1,
                           last_seen=excluded.last_seen,
                           last_company=COALESCE(excluded.last_company, user_tickers.last_company)""",
                    (email, tk, now, now, companies.get(tk)),
                )

    # ---- reads ------------------------------------------------------------ #
    def get_user_tickers(self, email: str) -> list[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """SELECT ticker, count, last_company, last_seen FROM user_tickers
                   WHERE email=? ORDER BY count DESC, last_seen DESC""",
                (email,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_history(self, email: str, limit: int = 25) -> list[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """SELECT ts, query, tickers, intent, confidence, model, refused, cost_usd
                   FROM query_history WHERE email=? ORDER BY id DESC LIMIT ?""",
                (email, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def user_stats(self, email: str) -> dict:
        """Per-user totals (queries, spend, distinct tickers) from the DB."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS queries, COALESCE(SUM(cost_usd), 0) AS cost_usd "
                "FROM query_history WHERE email=?", (email,),
            ).fetchone()
            tickers = conn.execute(
                "SELECT COUNT(*) FROM user_tickers WHERE email=?", (email,),
            ).fetchone()[0]
        return {"queries": row["queries"], "cost_usd": row["cost_usd"], "tickers": tickers}

    def all_users(self) -> list[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """SELECT u.email, u.name, u.last_login, COUNT(q.id) AS queries
                   FROM users u LEFT JOIN query_history q ON q.email=u.email
                   GROUP BY u.email ORDER BY u.last_login DESC""",
            ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict:
        with closing(self._connect()) as conn:
            users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            queries = conn.execute("SELECT COUNT(*) FROM query_history").fetchone()[0]
            tickers = conn.execute("SELECT COUNT(*) FROM user_tickers").fetchone()[0]
        return {"users": users, "queries": queries, "user_ticker_rows": tickers}
