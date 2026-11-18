"""Daily currency exchange rates (USD base) used when a household changes its currency.

Rates are fetched at most once per day from a free public source and cached in memory.
If the primary source fails, a second source is tried; if both fail, the last good rates are reused.
"""
from __future__ import annotations

import threading
from datetime import date, datetime, timezone

import httpx

# Household currency symbols used in the app -> ISO codes
SYMBOL_TO_CODE = {"₸": "KZT", "$": "USD", "€": "EUR", "₽": "RUB"}
CODES = list(SYMBOL_TO_CODE.values())

_lock = threading.Lock()
_cache: dict | None = None  # {"fetched_on": date, "payload": {...}}


def _from_open_er_api(client: httpx.Client) -> dict:
    r = client.get("https://open.er-api.com/v6/latest/USD")
    r.raise_for_status()
    d = r.json()
    if d.get("result") != "success":
        raise ValueError("open.er-api.com returned an error")
    updated = datetime.fromtimestamp(d["time_last_update_unix"], tz=timezone.utc).date().isoformat()
    return {"rates": {c: float(d["rates"][c]) for c in CODES}, "date": updated, "source": "open.er-api.com"}


def _from_currency_api(client: httpx.Client) -> dict:
    r = client.get("https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json")
    r.raise_for_status()
    d = r.json()
    return {"rates": {c: float(d["usd"][c.lower()]) for c in CODES}, "date": d["date"], "source": "fawazahmed0/currency-api"}


def get_rates() -> dict:
    """USD-based rates for KZT, USD, EUR and RUB, refreshed once per day."""
    global _cache
    today = date.today()
    with _lock:
        if _cache and _cache["fetched_on"] == today:
            return _cache["payload"]
        errors = []
        with httpx.Client(timeout=8) as client:
            for fetch in (_from_open_er_api, _from_currency_api):
                try:
                    data = fetch(client)
                    data["rates"]["USD"] = 1.0
                    payload = {"base": "USD", **data, "symbols": SYMBOL_TO_CODE, "stale": False}
                    _cache = {"fetched_on": today, "payload": payload}
                    return payload
                except Exception as e:  # noqa: BLE001 - try the next source
                    errors.append(f"{fetch.__name__}: {e}")
        if _cache:  # serve yesterday's rates rather than nothing
            return {**_cache["payload"], "stale": True}
        raise RuntimeError("; ".join(errors))
