"""Functional test checklist (O1) and the end-to-end check: expense -> forecast -> recommendation shown to all members.

Run:  python -m pytest -v        (from the backend folder)
Uses a temporary SQLite file. To run on PostgreSQL, set TEST_DATABASE_URL to a new, empty database.
"""
import os
import tempfile
from datetime import date

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ["SEED_DEMO_ON_START"] = "0"
os.environ["LLM_API_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config, recommend  # noqa: E402
from app.forecast import BEST_MODEL, month_add  # noqa: E402
from app.main import app  # noqa: E402
from app.models import CATEGORIES  # noqa: E402

THIS = date.today().strftime("%Y-%m")
PREV = month_add(THIS, -1)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def register(c, name):
    r = c.post("/api/auth/register", json={"name": name, "email": f"{name.lower()}@test.kz", "password": "secret123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def house(client):
    a, b, v = register(client, "Aigerim"), register(client, "Bauyrzhan"), register(client, "Viewer")
    hid = client.post("/api/households", json={"name": "Test home", "currency": "₸"}, headers=a).json()["id"]
    code = client.get(f"/api/households/{hid}", headers=a).json()["invite_code"]
    assert client.post("/api/households/join", json={"invite_code": code}, headers=b).status_code == 200
    assert client.post("/api/households/join", json={"invite_code": code}, headers=v).status_code == 200
    members = client.get(f"/api/households/{hid}", headers=a).json()["members"]
    vid = [m for m in members if m["name"] == "Viewer"][0]["user_id"]
    assert client.patch(f"/api/households/{hid}/members/{vid}", json={"role": "viewer"}, headers=a).status_code == 200
    return {"hid": hid, "a": a, "b": b, "v": v}


# FT-01 Accounts
def test_ft01_register_login_and_wrong_password(client):
    register(client, "Login")
    assert client.post("/api/auth/login", json={"email": "login@test.kz", "password": "secret123"}).status_code == 200
    assert client.post("/api/auth/login", json={"email": "login@test.kz", "password": "nope"}).status_code == 401
    assert client.get("/api/me").status_code == 401


# FT-02 Household, invite code, roles
def test_ft02_household_members_and_roles(client, house):
    h = client.get(f"/api/households/{house['hid']}", headers=house["b"]).json()
    assert {m["role"] for m in h["members"]} == {"owner", "member", "viewer"}
    assert h["my_role"] == "member"


# FT-03 Permissions
def test_ft03_permissions(client, house):
    hid = house["hid"]
    body = {"category": "Food", "amount": 5000, "spent_on": f"{PREV}-03"}
    assert client.post(f"/api/households/{hid}/expenses", json=body, headers=house["v"]).status_code == 403
    eid = client.post(f"/api/households/{hid}/expenses", json=body, headers=house["a"]).json()["id"]
    assert client.delete(f"/api/households/{hid}/expenses/{eid}", headers=house["b"]).status_code == 403   # member, not creator
    assert client.delete(f"/api/households/{hid}/expenses/{eid}", headers=house["a"]).status_code == 200   # creator / owner
    outsider = register(client, "Outsider")
    assert client.get(f"/api/households/{hid}", headers=outsider).status_code == 404


# FT-04 Expenses: add, validate, filter
def test_ft04_expenses(client, house):
    hid = house["hid"]
    assert client.post(f"/api/households/{hid}/expenses", headers=house["a"],
                       json={"category": "Pets", "amount": 1, "spent_on": f"{PREV}-01"}).status_code == 422
    assert client.post(f"/api/households/{hid}/expenses", headers=house["a"],
                       json={"category": "Food", "amount": -5, "spent_on": f"{PREV}-01"}).status_code == 422
    for cat, amt in [("Food", 120000), ("Housing", 250000), ("Utilities", 30000), ("Transportation", 40000),
                     ("Healthcare", 15000), ("Entertainment", 20000), ("Other", 25000)]:
        r = client.post(f"/api/households/{hid}/expenses", headers=house["b"],
                        json={"category": cat, "amount": amt, "spent_on": f"{PREV}-10", "note": "test"})
        assert r.status_code == 200
    rows = client.get(f"/api/households/{hid}/expenses", params={"month": PREV, "category": "Food"}, headers=house["v"]).json()
    assert len(rows) == 1 and rows[0]["amount"] == 120000


# FT-05 Shared plan and agreement (a changed plan resets agreement)
def test_ft05_budget_and_agreement(client, house):
    hid = house["hid"]
    st = client.put(f"/api/households/{hid}/agreement/{THIS}", json={"agreed": True}, headers=house["a"]).json()
    assert st["agreed_count"] == 1 and st["voters"] == 2
    client.put(f"/api/households/{hid}/agreement/{THIS}", json={"agreed": True}, headers=house["b"])
    assert client.get(f"/api/households/{hid}/budgets/{THIS}", headers=house["a"]).json()["agreement"]["final"] is True
    r = client.put(f"/api/households/{hid}/budgets/{THIS}", json={"amounts": {"Food": 110000}}, headers=house["b"]).json()
    assert r["plans"]["Food"] == {"amount": 110000, "suggested": False}
    assert r["agreement"]["agreed_count"] == 0                     # plan changed -> agreement reset
    assert client.put(f"/api/households/{hid}/agreement/{THIS}", json={"agreed": True}, headers=house["v"]).status_code == 403


# FT-06 Forecast from one month of data
def test_ft06_forecast_one_month(client, house):
    fc = client.get(f"/api/households/{house['hid']}/forecast/{THIS}", headers=house["a"]).json()
    assert fc["history_months"] == 1 and fc["total"] > 0
    for c in fc["categories"]:
        assert c["low"] <= c["forecast"] <= c["high"]
        assert c["confidence"] == "low"                             # only one month of data
        assert c["model"] == BEST_MODEL[c["category"]][0]           # best model for the category (Table V)
    # the current, unfinished month is never used as history, and forecasts stop one month after the last completed month
    client.post(f"/api/households/{house['hid']}/expenses", headers=house["a"],
                json={"category": "Other", "amount": 999999, "spent_on": f"{THIS}-01"})
    again = client.get(f"/api/households/{house['hid']}/forecast/{THIS}", headers=house["a"]).json()
    assert again["total"] == fc["total"] and again["latest_month"] == PREV
    assert client.get(f"/api/households/{house['hid']}/forecast/{month_add(THIS, 1)}", headers=house["a"]).status_code == 422


# FT-07 Recommendations (rule-based when no LLM key), cached, feedback
def test_ft07_recommendations_rules(client, house):
    r = client.get(f"/api/households/{house['hid']}/recommendations/{THIS}", headers=house["a"]).json()
    assert r["source"] == "rules" and set(r["items"]) >= {"Food", "Housing"}
    assert "not professional financial advice" in r["disclaimer"]
    assert client.put(f"/api/households/{house['hid']}/recommendations/{THIS}/feedback",
                      json={"category": "Food", "value": 1}, headers=house["b"]).status_code == 200


# FT-08 Activity log (audit trail)
def test_ft08_activity_log(client, house):
    acts = [a["action"] for a in client.get(f"/api/households/{house['hid']}/activity", headers=house["v"]).json()]
    assert any("joined the household" in a for a in acts)
    assert any("added Food" in a for a in acts)
    assert any("changed the" in a and "plan" in a for a in acts)
    assert any("role to viewer" in a for a in acts)


# FT-09 End-to-end: a member adds an expense -> forecast changes -> the same recommendation reaches every member
def test_ft09_end_to_end(client, house):
    hid = house["hid"]
    before = client.get(f"/api/households/{hid}/forecast/{THIS}", headers=house["a"]).json()
    client.post(f"/api/households/{hid}/expenses", headers=house["b"],
                json={"category": "Food", "amount": 200000, "spent_on": f"{PREV}-20", "note": "big shop"})
    after = client.get(f"/api/households/{hid}/forecast/{THIS}", headers=house["a"]).json()
    f0 = next(c for c in before["categories"] if c["category"] == "Food")["forecast"]
    f1 = next(c for c in after["categories"] if c["category"] == "Food")["forecast"]
    assert f1 > f0
    recs = [client.get(f"/api/households/{hid}/recommendations/{THIS}", headers=house[k]).json() for k in ("a", "b", "v")]
    assert recs[0]["items"] == recs[1]["items"] == recs[2]["items"]
    assert "above the plan" in recs[0]["items"]["Food"]           # forecast now above the 110 000 plan


# FT-10 Demo household holds only real BLS data, read-only; each category uses its best model
def test_ft10_demo_household_real_bls_data(client):
    import pandas as pd
    from app.config import NATIONAL_DATA
    from app.db import SessionLocal
    from app.seed import create_demo_household
    db = SessionLocal()
    h = create_demo_household(db, 99)
    db.close()
    tok = {"Authorization": "Bearer " + client.post("/api/auth/login", json={"email": "g99.demo@demo.kz", "password": "demo1234"}).json()["token"]}
    info = client.get(f"/api/households/{h.id}", headers=tok).json()
    assert info["data_source"] == "bls" and info["first_month"] == "2017-01" and info["latest_month"] == "2024-12"
    assert info["forecast_month"] == "2025-01" and len(info["members"]) == 1          # no fictional members
    # monthly totals in the app equal the research dataset exactly
    bls = pd.read_csv(NATIONAL_DATA, index_col=0)
    s = client.get(f"/api/households/{h.id}/summary/2024-03", headers=tok).json()["spent"]
    for c in ["Food", "Housing", "Utilities", "Transportation", "Healthcare", "Entertainment", "Other"]:
        assert abs(s[c] - bls.loc["2024-03-01", c]) < 0.02
    # dataset records are read-only; no expenses can be added to the demo household
    row = client.get(f"/api/households/{h.id}/expenses", params={"month": "2024-03"}, headers=tok).json()[0]
    assert row["dataset_record"] and row["paid_by_name"] == "BLS dataset"
    assert client.delete(f"/api/households/{h.id}/expenses/{row['id']}", headers=tok).status_code == 403
    assert client.post(f"/api/households/{h.id}/expenses", headers=tok,
                       json={"category": "Food", "amount": 1, "spent_on": "2024-12-01"}).status_code == 403
    fc = client.get(f"/api/households/{h.id}/forecast/2025-01", headers=tok).json()
    for c in fc["categories"]:
        fam = BEST_MODEL[c["category"]][0]
        assert c["model"] == fam and c["confidence"] == "normal"
        assert c["method"].startswith(fam)                                  # the model itself, not a fallback
    assert client.get(f"/api/households/{h.id}/forecast/2025-02", headers=tok).status_code == 422


# FT-12 The app reproduces the research evaluation: 2024 one-step RMSE close to Assignment 3, Table V (best model per category)
def test_ft12_app_matches_research_results():
    import numpy as np
    import pandas as pd
    from app.config import NATIONAL_DATA
    from app.forecast import household_forecast, month_range
    d = pd.read_csv(NATIONAL_DATA, index_col=0)
    d.index = [x[:7] for x in d.index]
    cats = list(BEST_MODEL)
    preds = pd.DataFrame([{c["category"]: c["forecast"] for c in household_forecast(d.loc[d.index < t, cats], t)["categories"]}
                          for t in month_range("2024-01", "2024-12")], index=month_range("2024-01", "2024-12"))
    rmse = np.sqrt(((preds - d.loc["2024-01":"2024-12", cats]) ** 2).mean())
    table_v = {"Food": 23.29, "Housing": 59.18, "Utilities": 7.91, "Transportation": 69.29,
               "Healthcare": 14.14, "Entertainment": 21.24, "Other": 62.43}
    for c, ref in table_v.items():
        assert abs(rmse[c] - ref) / ref < 0.15, (c, rmse[c], ref)       # app refits monthly, so small differences are expected


# FT-11 LLM path: valid reply used; failure falls back to rules
def test_ft11_llm_and_fallback(monkeypatch):
    items = [{"category": "Food", "forecast": 900.0, "low": 800.0, "high": 1000.0, "plan": 800.0, "last_month": 850.0,
              "confidence": "low"}]
    monkeypatch.setattr(config, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(recommend, "_call_llm", lambda p: ('{"Food": "Set a food limit of $800."}', "m"))
    r = recommend.generate(items, THIS, 3, "$")
    assert r["source"] == "llm" and r["items"]["Food"] == "Set a food limit of $800."

    def boom(p):
        raise TimeoutError()
    monkeypatch.setattr(recommend, "_call_llm", boom)
    r = recommend.generate(items, THIS, 3, "$")
    assert r["source"] == "rules" and "LLM unavailable" in r["note"]


# FT-13 A household with no expenses yet: every month-based page loads instead of failing
def test_ft13_household_with_no_expenses(client):
    h = register(client, "Newcomer")
    hid = client.post("/api/households", json={"name": "Empty home", "currency": "$"}, headers=h).json()["id"]
    for path in (f"budgets/{THIS}", f"summary/{THIS}", f"forecast/{THIS}"):
        r = client.get(f"/api/households/{hid}/{path}", headers=h)
        assert r.status_code == 200, f"{path}: {r.text}"
    s = client.get(f"/api/households/{hid}/summary/{THIS}", headers=h).json()
    assert s["spent_total"] == 0 and all(p["amount"] is None for p in s["plans"].values())
    assert client.delete("/api/me", headers=h).status_code == 200


# FT-14 Values the database would reject are refused or shortened, not turned into server errors
def test_ft14_length_limits(client, house):
    hid, a = house["hid"], house["a"]
    r = client.put(f"/api/households/{hid}/recommendations/{THIS}/feedback", json={"category": "x" * 40, "value": 1}, headers=a)
    assert r.status_code == 422
    expense = {"category": "Food", "amount": 1, "spent_on": str(date.today()), "note": "n" * 200}
    long_name = register(client, "L" * 80)
    h2 = client.post("/api/households", json={"name": "Long", "currency": "$"}, headers=long_name).json()["id"]
    assert client.post(f"/api/households/{h2}/expenses", json=expense, headers=long_name).status_code == 200
    plan = {c: 999_999_999_999 for c in CATEGORIES}
    assert client.put(f"/api/households/{h2}/budgets/{THIS}", json={"amounts": plan}, headers=long_name).status_code == 200
    for bad in ("0000-01", "9999-12"):
        assert client.get(f"/api/households/{h2}/summary/{bad}", headers=long_name).status_code == 422
