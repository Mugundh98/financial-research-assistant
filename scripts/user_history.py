"""Query the local per-user database (users, tickers, query history).

    python -m scripts.user_history --users
    python -m scripts.user_history --email you@firm.com
"""
from __future__ import annotations

import argparse

from src.storage import AppDB


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", help="show one user's tickers + query history")
    ap.add_argument("--users", action="store_true", help="list all users")
    ap.add_argument("--limit", type=int, default=25)
    args = ap.parse_args()

    db = AppDB()

    if args.users or not args.email:
        print("Users:")
        for u in db.all_users():
            print(f"  {u['email']} ({u['name'] or '-'}) - {u['queries']} queries, last {u['last_login']}")
        print("\nDB stats:", db.stats())

    if args.email:
        em = args.email.strip().lower()
        print(f"\nTickers for {em}:")
        for t in db.get_user_tickers(em):
            print(f"  {t['ticker']:6s} x{t['count']:<3} last={t['last_seen']}  {t['last_company'] or ''}")
        print(f"\nRecent queries for {em}:")
        for h in db.get_history(em, args.limit):
            print(f"  [{h['ts']}] ({h['intent']}) {h['query'][:70]}  "
                  f"-> tickers={h['tickers']} refused={h['refused']}")


if __name__ == "__main__":
    main()
