"""Forecast engine: the best model for each category, as selected in the research notebook (CE_SARIMA_2017_2024.ipynb).

Model per category = lowest one-step-ahead test RMSE on 2024 (Assignment 3, Table V), with the orders selected on the
2023 validation year (Table IV):

    Housing, Transportation, Entertainment, Other  -> SARIMA
    Utilities, Healthcare                          -> ARIMA
    Food                                           -> MA(3), mean of the previous three months

Every forecast is one month ahead and uses only the household's own monthly totals before the target month.
If a household does not yet have enough months for its model (SARIMA 24, ARIMA 12), a simpler rule is used and flagged:
own recent average, adjusted by the seasonal pattern of the national SARIMA (fitted on the BLS series) for SARIMA categories.
"""
from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pandas as pd
from statsmodels.tsa.statespace.sarimax import SARIMAX

from .config import NATIONAL_DATA
from .models import CATEGORIES

warnings.filterwarnings("ignore")

# family, (p,d,q), (P,D,Q) for each category (Assignment 3, Tables IV and V)
BEST_MODEL = {
    "Food":           ("MA(3)",  None,      None),
    "Housing":        ("SARIMA", (2, 0, 2), (0, 1, 1)),
    "Utilities":      ("ARIMA",  (2, 1, 2), (0, 0, 0)),
    "Transportation": ("SARIMA", (2, 1, 2), (0, 1, 1)),
    "Healthcare":     ("ARIMA",  (0, 1, 1), (0, 0, 0)),
    "Entertainment":  ("SARIMA", (1, 1, 0), (0, 1, 1)),
    "Other":          ("SARIMA", (2, 1, 0), (0, 1, 1)),
}
MIN_MONTHS = {"SARIMA": 24, "ARIMA": 12, "MA(3)": 1}
COVID_MONTHS = {f"2020-{m:02d}" for m in range(4, 13)}       # COVID indicator, as in the research notebook


def month_add(month: str, k: int) -> str:
    y, m = map(int, month.split("-"))
    total = y * 12 + (m - 1) + k
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def month_range(start: str, end_inclusive: str) -> list[str]:
    out, cur = [], start
    while cur <= end_inclusive:
        out.append(cur)
        cur = month_add(cur, 1)
    return out


def _fit(y: pd.Series, order, seasonal, exog=None):
    trend = "c" if order[1] + seasonal[1] == 0 else "n"
    return SARIMAX(y, exog=exog, order=order, seasonal_order=(*seasonal, 12), trend=trend).fit(disp=False)


def _to_ts(history: pd.Series) -> pd.Series:
    y = pd.Series(history.values.astype(float),
                  index=pd.period_range(history.index[0], periods=len(history), freq="M").to_timestamp())
    y.index.freq = "MS"
    return y


@lru_cache(maxsize=1)
def national_seasonal_index() -> dict[str, dict[int, float]]:
    """Seasonal index per SARIMA category and calendar month, from the national SARIMA (BLS 2017-2024) forecast for 2025.
    Used only for households with too little history for their own SARIMA."""
    df = pd.read_csv(NATIONAL_DATA, index_col=0, parse_dates=True)
    df.index.freq = "MS"
    covid = pd.Series([1.0 if d.strftime("%Y-%m") in COVID_MONTHS else 0.0 for d in df.index], index=df.index, name="covid")
    future = pd.date_range(df.index[-1] + pd.offsets.MonthBegin(1), periods=12, freq="MS")
    out = {}
    for c, (family, order, seasonal) in BEST_MODEL.items():
        if family != "SARIMA":
            continue
        res = _fit(df[c].astype(float), order, seasonal, exog=covid)
        fc = pd.Series(res.forecast(12, exog=np.zeros((12, 1))).values, index=future)
        out[c] = {ts.month: float(v / fc.mean()) for ts, v in fc.items()}
    return out


@dataclass
class CategoryForecast:
    category: str
    forecast: float | None
    low: float | None
    high: float | None
    model: str                 # SARIMA | ARIMA | MA(3)
    method: str                # what was actually computed
    confidence: str            # "low" | "normal"
    confidence_note: str
    history_months: int
    last_month: float | None


def _round(v) -> float | None:
    return None if v is None or not math.isfinite(float(v)) else float(round(max(float(v), 0.0), 2))


def forecast_category(category: str, history: pd.Series, target: str) -> CategoryForecast:
    """history: consecutive monthly totals indexed 'YYYY-MM', ending exactly the month before target."""
    family, order, seasonal = BEST_MODEL[category]
    n = len(history)
    last = float(history.iloc[-1]) if n else None
    if n == 0:
        return CategoryForecast(category, None, None, None, family, "no data", "low",
                                "Add expenses for at least one month to get a forecast.", 0, None)
    value, notes, fallback = None, [], False

    if family == "MA(3)":
        k = min(n, 3)
        value = float(history.iloc[-k:].mean())
        method = f"MA(3): mean of the last {k} month{'s' if k > 1 else ''}"
        if k < 3:
            notes.append(f"Needs 3 months of data; {k} available.")
    elif n >= MIN_MONTHS[family] and history.sum() > 0:
        try:
            y = _to_ts(history)
            exog = None
            if any(m in COVID_MONTHS for m in history.index):
                exog = pd.Series([1.0 if m in COVID_MONTHS else 0.0 for m in history.index], index=y.index, name="covid")
            res = _fit(y, order, seasonal, exog=exog)
            v = float(res.forecast(1, exog=np.zeros((1, 1)) if exog is not None else None).iloc[0])
            if math.isfinite(v) and v >= 0:
                value = v
                spec = f"{order}{seasonal}12" if family == "SARIMA" else f"{order}"
                method = f"{family}{spec} fitted on {n} months" + (" with COVID indicator" if exog is not None else "")
        except Exception:
            value = None
    if value is None:                      # not enough history (or fit failed): simpler rule, flagged
        fallback = True
        h = min(n, 6)
        recent = history.iloc[-h:]
        base = float(recent.mean())
        if family == "SARIMA":
            season = national_seasonal_index()[category]
            value = base * season[int(target[5:7])] / np.mean([season[int(m[5:7])] for m in recent.index])
            method = f"Own {h}-month average × seasonal pattern of the national SARIMA (BLS)"
        else:
            value = base
            method = f"Own {h}-month average"
        notes.append(f"Needs at least {MIN_MONTHS[family]} months of data; {n} available, so a simpler rule is used.")

    if n >= 3 and history.iloc[-12:].mean() > 0:
        spread = float(np.clip(history.iloc[-12:].std(ddof=0) / history.iloc[-12:].mean(), 0.05, 0.60))
    else:
        spread = 0.35
    confidence = "low" if (n < 3 or fallback) else "normal"
    if n < 3 and not any("months" in x for x in notes):
        notes.append(f"Based on only {n} month{'s' if n != 1 else ''} of data.")
    return CategoryForecast(category, _round(value), _round(value * (1 - spread)), _round(value * (1 + spread)),
                            family, method, confidence, " ".join(notes), n, _round(last))


def household_forecast(monthly: pd.DataFrame, target: str) -> dict:
    """monthly: index 'YYYY-MM' (strings), columns = CATEGORIES; only months before target are used."""
    hist = monthly[monthly.index.astype(str) < target] if len(monthly) else monthly
    if len(hist):
        hist = hist.reindex(month_range(hist.index.min(), month_add(target, -1)), fill_value=0.0)
    cats = [forecast_category(c, hist[c] if len(hist) else pd.Series(dtype=float), target) for c in CATEGORIES]
    ok = all(c.forecast is not None for c in cats)
    return {"month": target, "history_months": len(hist), "categories": [c.__dict__ for c in cats],
            "total": round(sum(c.forecast for c in cats), 2) if ok else None,
            "total_low": round(sum(c.low for c in cats), 2) if ok else None,
            "total_high": round(sum(c.high for c in cats), 2) if ok else None}
