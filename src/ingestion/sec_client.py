"""SEC EDGAR client with a transparent on-disk cache.

Why SEC EDGAR: it is the authoritative source of *approved* financial records
(10-K / 10-Q filings) and needs no API key. It exposes both structured data
(XBRL "company facts") and unstructured narrative (filing documents), each with
real filing/period dates -- ideal for provenance and freshness.

Every response is cached under ``data/cache/`` so repeated runs are reproducible
and work offline after the first fetch. A politeness throttle keeps us within
SEC's fair-access guidance, and the required contact User-Agent is configurable.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Optional

import httpx

from ..config import settings


class SECClient:
    def __init__(
        self,
        user_agent: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        min_interval: Optional[float] = None,
    ) -> None:
        self.user_agent = user_agent or settings.sec_user_agent
        self.cache_dir = Path(cache_dir or settings.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval = settings.sec_min_interval if min_interval is None else min_interval
        self._last_request = 0.0
        self._client = httpx.Client(
            headers={"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"},
            timeout=settings.request_timeout,
            follow_redirects=True,
        )

    # ---- low level --------------------------------------------------------- #
    @staticmethod
    def pad_cik(cik: str | int) -> str:
        digits = re.sub(r"\D", "", str(cik))
        return digits.zfill(10) if digits else "0000000000"

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_request = time.monotonic()

    def _cache_path(self, url: str, ext: str) -> Path:
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        tail = re.sub(r"[^A-Za-z0-9._-]", "_", url.split("//", 1)[-1])[-80:]
        return self.cache_dir / f"{tail}.{digest}.{ext}"

    def _get(self, url: str, ext: str, force: bool = False) -> str:
        path = self._cache_path(url, ext)
        if path.exists() and not force:
            return path.read_text(encoding="utf-8")
        self._throttle()
        resp = self._client.get(url)
        resp.raise_for_status()
        text = resp.text
        path.write_text(text, encoding="utf-8")
        return text

    def get_json(self, url: str, force: bool = False) -> Any:
        return json.loads(self._get(url, "json", force))

    def get_text(self, url: str, force: bool = False) -> str:
        return self._get(url, "txt", force)

    # ---- high level -------------------------------------------------------- #
    def company_tickers(self, force: bool = False) -> dict:
        return self.get_json(f"{settings.sec_base_www}/files/company_tickers.json", force)

    def resolve_cik(self, ticker: str) -> Optional[str]:
        want = ticker.upper().strip()
        for row in self.company_tickers().values():
            if str(row.get("ticker", "")).upper() == want:
                return self.pad_cik(row["cik_str"])
        return None

    def submissions(self, cik: str, force: bool = False) -> dict:
        cik10 = self.pad_cik(cik)
        return self.get_json(f"{settings.sec_base_data}/submissions/CIK{cik10}.json", force)

    def company_concept(
        self, cik: str, tag: str, taxonomy: str = "us-gaap", force: bool = False
    ) -> dict:
        cik10 = self.pad_cik(cik)
        url = f"{settings.sec_base_data}/api/xbrl/companyconcept/CIK{cik10}/{taxonomy}/{tag}.json"
        return self.get_json(url, force)

    def company_facts(self, cik: str, force: bool = False) -> dict:
        cik10 = self.pad_cik(cik)
        return self.get_json(
            f"{settings.sec_base_data}/api/xbrl/companyfacts/CIK{cik10}.json", force
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SECClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
