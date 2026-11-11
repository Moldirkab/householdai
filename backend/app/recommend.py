"""Forecast-based budget recommendations: LLM when an API key is configured, rule-based otherwise."""
from __future__ import annotations

import json
import math
import re

import httpx

from . import config

DISCLAIMER = "Decision support only, not professional financial advice."


def money(v: float, cur: str) -> str:
    s = f"{abs(round(v)):,}"
    return f"{'-' if v < 0 else ''}${s}" if cur == "$" else f"{'-' if v < 0 else ''}{s.replace(',', ' ')} {cur}"


def status(forecast: float | None, plan: float | None) -> tuple[str, str, float | None]:
    if forecast is None:
        return "none", "No forecast", None
    if not plan:
        return "none", "No spending yet" if forecast == 0 else "No plan", None
    d = (forecast - plan) / plan * 100
    if d > 5:
        return "over", "Over plan", d
    if d < -5:
        return "under", "Below plan", d
    return "ok", "On plan", d


def rule_text(cat: str, fc: float | None, plan: float | None, last: float | None, cur: str) -> str:
    """Same rules as the questionnaire demo."""
    if fc is None:
        return "Add expenses for at least one completed month to get a forecast and a recommendation."
    if fc == 0 and not plan:
        return "No spending recorded in this category yet, so there is nothing to recommend."
    if not plan:
        return f"No plan set yet. A plan close to the forecast ({money(fc, cur)}) is a reasonable start."
    d, pct = fc - plan, (fc - plan) / plan * 100
    if pct > 5:
        return (f"Forecast is {money(d, cur)} above the plan. Agree on a {cat.lower()} limit of {money(plan, cur)} "
                f"or raise the plan to {money(math.ceil(fc / 10) * 10, cur)} and cut another category.")
    if pct < -5:
        return (f"Forecast is {money(-d, cur)} below the plan. The household could move about "
                f"{money(math.floor(-d / 10) * 10, cur)} to savings or to a category that is over plan.")
    lm = f" (last month: {money(last, cur)})" if last is not None else ""
    return f"Spending is expected to stay within ±5% of the plan{lm}. No change needed."


def rule_based(items: list[dict], cur: str) -> dict:
    return {"source": "rules", "model": None, "disclaimer": DISCLAIMER,
            "items": {it["category"]: rule_text(it["category"], it["forecast"], it["plan"], it["last_month"], cur)
                      for it in items}}


PROMPT = """You help a household of {n} people plan a shared monthly budget.
For each spending category below you get: the AI forecast for {month}, its likely range,
the shared plan (budget) the household set, last month's spending, and a confidence flag.

Write ONE short, concrete recommendation per category (max 2 sentences, at most 40 words), in English, addressed to the household
("you"/"your household"). Base it only on these numbers. If the forecast is more than 5% above the plan, suggest a concrete limit
or which other category to cut; if more than 5% below, suggest where the difference could go (e.g. savings); otherwise say no change is needed.
If confidence is low, say briefly that the forecast is uncertain. Use the currency symbol "{cur}" and round amounts.
Do not give investment, loan or tax advice.

Return ONLY a JSON object mapping each category name to its recommendation text, e.g. {{"Food": "..."}}.

Data:
{data}"""


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON in LLM reply")
    return json.loads(m.group(0))


def _call_llm(prompt: str) -> tuple[str, str]:
    provider, key = config.LLM_PROVIDER, config.LLM_API_KEY
    model = config.LLM_MODEL or config.DEFAULT_MODELS.get(provider, "")
    t = config.LLM_TIMEOUT_SECONDS
    if provider == "anthropic":
        r = httpx.post("https://api.anthropic.com/v1/messages", timeout=t,
                       headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                       json={"model": model, "max_tokens": 1200, "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json()["content"]), model
    if provider == "openai":
        r = httpx.post("https://api.openai.com/v1/chat/completions", timeout=t,
                       headers={"Authorization": f"Bearer {key}"},
                       json={"model": model, "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"], model
    if provider == "gemini":
        r = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                       params={"key": key}, timeout=t, json={"contents": [{"parts": [{"text": prompt}]}]})
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"], model
    raise ValueError(f"Unknown LLM_PROVIDER '{provider}'")


def generate(items: list[dict], month: str, members: int, cur: str) -> dict:
    """items: [{category, forecast, low, high, plan, last_month, confidence}]"""
    fallback = rule_based(items, cur)
    if not config.LLM_API_KEY:
        fallback["note"] = "Rule-based recommendations (no LLM API key configured)."
        return fallback
    data = json.dumps([{k: (round(v) if isinstance(v, float) else v) for k, v in it.items()} for it in items], ensure_ascii=False)
    try:
        text, model = _call_llm(PROMPT.format(n=members, month=month, cur=cur, data=data))
        parsed = _extract_json(text)
        out = {it["category"]: str(parsed.get(it["category"]) or fallback["items"][it["category"]]).strip() for it in items}
        return {"source": "llm", "model": f"{config.LLM_PROVIDER}:{model}", "disclaimer": DISCLAIMER, "items": out}
    except Exception as e:  # network error, quota, bad JSON: fall back to rules
        fallback["note"] = f"LLM unavailable ({type(e).__name__}); rule-based recommendations shown instead."
        return fallback
