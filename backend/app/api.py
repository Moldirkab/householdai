from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import secrets
from datetime import date

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import recommend
from .db import get_db
from .forecast import household_forecast, month_add
from .models import (CATEGORIES, ROLES, Activity, Agreement, Budget, Expense, Feedback, Household, Membership,
                     RecommendationCache, Token, User)
from .security import current_user, hash_password, membership_or_404, new_token, require_role, verify_password

router = APIRouter(prefix="/api")
WRITE_ROLES = {"owner", "member"}


# ---------- helpers ----------
def this_month() -> str:
    return date.today().strftime("%Y-%m")


def check_month(m: str) -> str:
    try:
        y, mm = m.split("-")
        assert len(y) == 4 and 1 <= int(y) <= 9998 and 1 <= int(mm) <= 12
        return f"{int(y):04d}-{int(mm):02d}"
    except Exception:
        raise HTTPException(422, "Month must look like YYYY-MM.")


def month_bounds(m: str) -> tuple[date, date]:
    """First day of the month and first day of the next one, for filtering dates in any database."""
    return date.fromisoformat(f"{m}-01"), date.fromisoformat(f"{month_add(m, 1)}-01")


def log(db: Session, hid: int, uid: int | None, action: str) -> None:
    db.add(Activity(household_id=hid, user_id=uid, action=action[:300]))


def fmt(v: float, cur: str) -> str:
    return recommend.money(v, cur)


def round_plan(v: float, cur: str) -> float:
    step = 10 if cur == "$" else (1000 if v >= 10000 else 100)
    return float(math.ceil(v / step) * step) if v > 0 else 0.0


def monthly_spending(db: Session, hid: int) -> pd.DataFrame:
    rows = db.query(Expense.spent_on, Expense.category, Expense.amount).filter_by(household_id=hid).all()
    if not rows:
        return pd.DataFrame(index=pd.Index([], dtype=str, name="m"), columns=CATEGORIES, dtype=float)
    df = pd.DataFrame(rows, columns=["d", "c", "a"])
    df["m"] = pd.to_datetime(df.d).dt.strftime("%Y-%m")
    return df.pivot_table(index="m", columns="c", values="a", aggfunc="sum", fill_value=0.0).reindex(
        columns=CATEGORIES, fill_value=0.0).sort_index()


def data_window(monthly: pd.DataFrame) -> dict:
    """Months with data. Only completed months count: the current calendar month is never used as history."""
    if not len(monthly):
        return {"first_month": None, "latest_month": None, "forecast_month": this_month()}
    latest = min(monthly.index.max(), month_add(this_month(), -1))
    if latest < monthly.index.min():
        return {"first_month": monthly.index.min(), "latest_month": None, "forecast_month": this_month()}
    return {"first_month": monthly.index.min(), "latest_month": latest, "forecast_month": month_add(latest, 1)}


def plans_for(db: Session, hid: int, month: str, monthly: pd.DataFrame, cur: str) -> dict[str, dict]:
    set_ = {b.category: b.amount for b in db.query(Budget).filter_by(household_id=hid, month=month)}
    prev = monthly[monthly.index < month].iloc[-3:]
    out = {}
    for c in CATEGORIES:
        if c in set_:
            out[c] = {"amount": set_[c], "suggested": False}
        else:
            out[c] = {"amount": round_plan(float(prev[c].mean()), cur) if len(prev) else None, "suggested": True}
    return out


def member_list(db: Session, hid: int) -> list[dict]:
    ms = db.query(Membership, User).join(User, User.id == Membership.user_id).filter(Membership.household_id == hid)
    return [{"user_id": u.id, "name": u.name, "email": u.email, "role": m.role} for m, u in ms.order_by(Membership.id)]


def user_name(db: Session, uid: int | None) -> str:
    u = db.get(User, uid) if uid else None
    return u.name if u else "Former member"


# ---------- auth ----------
class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=6, max_length=200)


class LoginIn(BaseModel):
    email: str
    password: str


def me_payload(db: Session, user: User) -> dict:
    hs = (db.query(Membership, Household).join(Household, Household.id == Membership.household_id)
          .filter(Membership.user_id == user.id).order_by(Membership.id).all())
    return {"id": user.id, "name": user.name, "email": user.email,
            "households": [{"id": h.id, "name": h.name, "role": m.role, "currency": h.currency} for m, h in hs]}


@router.post("/auth/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(422, "Please enter a valid email.")
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(409, "An account with this email already exists.")
    user = User(name=body.name.strip(), email=email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    return {"token": new_token(db, user), "user": me_payload(db, user)}


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=body.email.strip().lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Wrong email or password.")
    return {"token": new_token(db, user), "user": me_payload(db, user)}


@router.post("/auth/logout")
def logout(user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.query(Token).filter_by(user_id=user.id).delete()
    db.commit()
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return me_payload(db, user)


@router.delete("/me")
def delete_me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    for m in db.query(Membership).filter_by(user_id=user.id).all():
        owners = db.query(Membership).filter_by(household_id=m.household_id, role="owner").count()
        others = db.query(Membership).filter(Membership.household_id == m.household_id, Membership.user_id != user.id).count()
        if m.role == "owner" and owners == 1 and others > 0:
            raise HTTPException(409, "Make another member an owner of your household before deleting your account.")
    hids = [m.household_id for m in db.query(Membership).filter_by(user_id=user.id)]
    for hid in hids:
        if db.query(Membership).filter_by(household_id=hid).count() == 1:
            db.delete(db.get(Household, hid))
        else:
            log(db, hid, None, f"{user.name} deleted their account")
    db.query(Token).filter_by(user_id=user.id).delete()
    db.delete(user)
    db.commit()
    return {"ok": True}


# ---------- households and members ----------
class HouseholdIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    currency: str = Field(default="₸", max_length=8)


class JoinIn(BaseModel):
    invite_code: str


class RoleIn(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def valid(cls, v):
        if v not in ROLES:
            raise ValueError(f"role must be one of {ROLES}")
        return v


def new_code() -> str:
    return secrets.token_hex(3).upper()


@router.post("/households")
def create_household(body: HouseholdIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    h = Household(name=body.name.strip(), currency=body.currency.strip() or "₸", invite_code=new_code())
    db.add(h)
    db.flush()
    db.add(Membership(household_id=h.id, user_id=user.id, role="owner"))
    log(db, h.id, user.id, f"{user.name} created the household")
    db.commit()
    return {"id": h.id}


@router.post("/households/join")
def join_household(body: JoinIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    h = db.query(Household).filter_by(invite_code=body.invite_code.strip().upper()).first()
    if not h:
        raise HTTPException(404, "No household found with this invite code.")
    if db.query(Membership).filter_by(household_id=h.id, user_id=user.id).first():
        return {"id": h.id}
    db.add(Membership(household_id=h.id, user_id=user.id, role="member"))
    log(db, h.id, user.id, f"{user.name} joined the household")
    db.commit()
    return {"id": h.id}


@router.get("/households/{hid}")
def get_household(hid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = membership_or_404(db, hid, user)
    h = db.get(Household, hid)
    return {"id": h.id, "name": h.name, "currency": h.currency, "my_role": m.role, "data_source": h.data_source,
            "invite_code": h.invite_code if m.role in WRITE_ROLES else None,
            "members": member_list(db, hid), "categories": CATEGORIES, "this_month": this_month(),
            **data_window(monthly_spending(db, hid))}


class HouseholdPatch(BaseModel):
    name: str | None = None
    currency: str | None = None


@router.patch("/households/{hid}")
def patch_household(hid: int, body: HouseholdPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = membership_or_404(db, hid, user)
    require_role(m, {"owner"}, "change household settings")
    h = db.get(Household, hid)
    if body.name:
        h.name = body.name.strip()
    if body.currency:
        h.currency = body.currency.strip()
    log(db, hid, user.id, f"{user.name} updated household settings")
    db.commit()
    return {"ok": True}


@router.post("/households/{hid}/invite/regenerate")
def regenerate_invite(hid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = membership_or_404(db, hid, user)
    require_role(m, {"owner"}, "change the invite code")
    db.get(Household, hid).invite_code = new_code()
    log(db, hid, user.id, f"{user.name} created a new invite code")
    db.commit()
    return {"invite_code": db.get(Household, hid).invite_code}


@router.patch("/households/{hid}/members/{uid}")
def change_role(hid: int, uid: int, body: RoleIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = membership_or_404(db, hid, user)
    require_role(m, {"owner"}, "change member roles")
    target = db.query(Membership).filter_by(household_id=hid, user_id=uid).first()
    if not target:
        raise HTTPException(404, "Member not found.")
    if target.role == "owner" and body.role != "owner" and \
            db.query(Membership).filter_by(household_id=hid, role="owner").count() == 1:
        raise HTTPException(409, "A household needs at least one owner.")
    target.role = body.role
    log(db, hid, user.id, f"{user.name} changed {user_name(db, uid)}'s role to {body.role}")
    db.commit()
    return {"ok": True}


@router.delete("/households/{hid}/members/{uid}")
def remove_member(hid: int, uid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = membership_or_404(db, hid, user)
    if uid != user.id:
        require_role(m, {"owner"}, "remove other members")
    target = db.query(Membership).filter_by(household_id=hid, user_id=uid).first()
    if not target:
        raise HTTPException(404, "Member not found.")
    owners = db.query(Membership).filter_by(household_id=hid, role="owner").count()
    total = db.query(Membership).filter_by(household_id=hid).count()
    if target.role == "owner" and owners == 1 and total > 1:
        raise HTTPException(409, "Make another member an owner first.")
    name = user_name(db, uid)
    db.delete(target)
    if total == 1:
        db.delete(db.get(Household, hid))
    else:
        log(db, hid, user.id, f"{name} left the household" if uid == user.id else f"{user.name} removed {name}")
    db.commit()
    return {"ok": True}


# ---------- expenses ----------
class ExpenseIn(BaseModel):
    category: str
    amount: float = Field(gt=0, lt=1e12)
    spent_on: date
    note: str = Field(default="", max_length=200)
    shared: bool = True
    paid_by: int | None = None

    @field_validator("category")
    @classmethod
    def valid_cat(cls, v):
        if v not in CATEGORIES:
            raise ValueError(f"category must be one of {CATEGORIES}")
        return v


def expense_out(e: Expense, db: Session) -> dict:
    return {"id": e.id, "category": e.category, "amount": e.amount, "spent_on": e.spent_on.isoformat(),
            "note": e.note, "shared": e.shared, "paid_by": e.paid_by,
            "paid_by_name": "BLS dataset" if e.paid_by is None and e.created_by is None else user_name(db, e.paid_by),
            "created_by": e.created_by, "dataset_record": e.created_by is None and e.paid_by is None}


@router.get("/households/{hid}/expenses")
def list_expenses(hid: int, month: str | None = None, category: str | None = None, paid_by: int | None = None,
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    membership_or_404(db, hid, user)
    q = db.query(Expense).filter_by(household_id=hid)
    if month:
        first, end = month_bounds(check_month(month))
        q = q.filter(Expense.spent_on >= first, Expense.spent_on < end)
    if category:
        q = q.filter_by(category=category)
    if paid_by:
        q = q.filter_by(paid_by=paid_by)
    return [expense_out(e, db) for e in q.order_by(Expense.spent_on.desc(), Expense.id.desc()).limit(1000)]


def _check_payer(db: Session, hid: int, uid: int | None) -> None:
    if uid and not db.query(Membership).filter_by(household_id=hid, user_id=uid).first():
        raise HTTPException(422, "The payer must be a member of this household.")


@router.post("/households/{hid}/expenses")
def add_expense(hid: int, body: ExpenseIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = membership_or_404(db, hid, user)
    require_role(m, WRITE_ROLES, "add expenses")
    if db.get(Household, hid).data_source == "bls":
        raise HTTPException(403, "This demo household contains only real BLS data. Create your own household to add expenses.")
    payer = body.paid_by or user.id
    _check_payer(db, hid, payer)
    e = Expense(household_id=hid, paid_by=payer, created_by=user.id, category=body.category, amount=body.amount,
                spent_on=body.spent_on, note=body.note.strip(), shared=body.shared)
    db.add(e)
    cur = db.get(Household, hid).currency
    log(db, hid, user.id, f"{user.name} added {body.category} {fmt(body.amount, cur)}"
                          + (f" ({body.note.strip()})" if body.note.strip() else ""))
    db.commit()
    return expense_out(e, db)


def _editable_expense(db: Session, hid: int, eid: int, user: User) -> tuple[Expense, Membership]:
    m = membership_or_404(db, hid, user)
    e = db.get(Expense, eid)
    if not e or e.household_id != hid:
        raise HTTPException(404, "Expense not found.")
    if e.created_by is None and e.paid_by is None:
        raise HTTPException(403, "Records from the BLS dataset cannot be changed.")
    if m.role == "viewer" or (m.role == "member" and e.created_by != user.id):
        raise HTTPException(403, "You can only change expenses you added (owners can change any expense).")
    return e, m


@router.put("/households/{hid}/expenses/{eid}")
def update_expense(hid: int, eid: int, body: ExpenseIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    e, _ = _editable_expense(db, hid, eid, user)
    _check_payer(db, hid, body.paid_by or e.paid_by)
    old = f"{e.category} {fmt(e.amount, db.get(Household, hid).currency)}"
    e.category, e.amount, e.spent_on, e.note, e.shared = body.category, body.amount, body.spent_on, body.note.strip(), body.shared
    e.paid_by = body.paid_by or e.paid_by
    log(db, hid, user.id, f"{user.name} edited an expense: {old} → {e.category} {fmt(e.amount, db.get(Household, hid).currency)}")
    db.commit()
    return expense_out(e, db)


@router.delete("/households/{hid}/expenses/{eid}")
def delete_expense(hid: int, eid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    e, _ = _editable_expense(db, hid, eid, user)
    log(db, hid, user.id, f"{user.name} deleted {e.category} {fmt(e.amount, db.get(Household, hid).currency)}")
    db.delete(e)
    db.commit()
    return {"ok": True}


# ---------- budgets (shared plan) and agreement ----------
class BudgetIn(BaseModel):
    amounts: dict[str, float]


def agreement_state(db: Session, hid: int, month: str) -> dict:
    members = member_list(db, hid)
    voters = [mm for mm in members if mm["role"] in WRITE_ROLES]
    agreed = {a.user_id for a in db.query(Agreement).filter_by(household_id=hid, month=month, agreed=True)}
    return {"month": month, "members": [{**mm, "agreed": mm["user_id"] in agreed} for mm in members],
            "agreed_count": sum(1 for v in voters if v["user_id"] in agreed), "voters": len(voters),
            "final": len(voters) > 0 and all(v["user_id"] in agreed for v in voters)}


@router.get("/households/{hid}/budgets/{month}")
def get_budget(hid: int, month: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    membership_or_404(db, hid, user)
    month = check_month(month)
    cur = db.get(Household, hid).currency
    monthly = monthly_spending(db, hid)
    plans = plans_for(db, hid, month, monthly, cur)
    spent = monthly.loc[month].to_dict() if month in monthly.index else {c: 0.0 for c in CATEGORIES}
    return {"month": month, "plans": plans, "spent": {c: round(float(spent[c]), 2) for c in CATEGORIES},
            "agreement": agreement_state(db, hid, month)}


@router.put("/households/{hid}/budgets/{month}")
def set_budget(hid: int, month: str, body: BudgetIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = membership_or_404(db, hid, user)
    require_role(m, WRITE_ROLES, "change the shared plan")
    month = check_month(month)
    cur = db.get(Household, hid).currency
    changes = []
    for c, v in body.amounts.items():
        if c not in CATEGORIES or v is None or v < 0:
            raise HTTPException(422, f"Invalid plan for {c}.")
        b = db.query(Budget).filter_by(household_id=hid, month=month, category=c).first()
        if b and abs(b.amount - v) < 1e-9:
            continue
        changes.append(f"{c} {fmt(b.amount, cur) + ' → ' if b else ''}{fmt(v, cur)}")
        if b:
            b.amount = v
        else:
            db.add(Budget(household_id=hid, month=month, category=c, amount=v))
    if changes:
        # a changed plan needs everyone's agreement again
        db.query(Agreement).filter_by(household_id=hid, month=month).update({"agreed": False})
        log(db, hid, user.id, f"{user.name} changed the {month} plan: " + ", ".join(changes))
    db.commit()
    return get_budget(hid, month, user, db)


class AgreeIn(BaseModel):
    agreed: bool


@router.put("/households/{hid}/agreement/{month}")
def set_agreement(hid: int, month: str, body: AgreeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = membership_or_404(db, hid, user)
    require_role(m, WRITE_ROLES, "agree to the plan")
    month = check_month(month)
    a = db.query(Agreement).filter_by(household_id=hid, month=month, user_id=user.id).first()
    if not a:
        a = Agreement(household_id=hid, month=month, user_id=user.id)
        db.add(a)
    a.agreed = body.agreed
    log(db, hid, user.id, f"{user.name} {'agreed to' if body.agreed else 'withdrew agreement from'} the {month} plan")
    db.commit()
    return agreement_state(db, hid, month)


# ---------- forecast and recommendations ----------
_forecast_cache: dict[tuple, dict] = {}


def compute_forecast(db: Session, hid: int, month: str) -> dict:
    monthly = monthly_spending(db, hid)
    win = data_window(monthly)
    if win["latest_month"] and month > win["forecast_month"]:
        raise HTTPException(422, f"Forecasts are available up to {win['forecast_month']} "
                                 f"(data up to the last completed month, {win['latest_month']}).")
    hist = monthly[(monthly.index < month) & (monthly.index <= (win["latest_month"] or ""))]
    key = (hid, month, hashlib.sha1(hist.round(2).to_csv().encode()).hexdigest())
    if key not in _forecast_cache:
        if len(_forecast_cache) > 200:
            _forecast_cache.clear()
        _forecast_cache[key] = household_forecast(hist, month)
    return _forecast_cache[key]


@router.get("/households/{hid}/forecast/{month}")
def get_forecast(hid: int, month: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    membership_or_404(db, hid, user)
    month = check_month(month)
    cur = db.get(Household, hid).currency
    fc = compute_forecast(db, hid, month)
    monthly = monthly_spending(db, hid)
    plans = plans_for(db, hid, month, monthly, cur)
    win = data_window(monthly)
    complete = bool(win["latest_month"]) and month <= win["latest_month"]
    actual = monthly.loc[month].to_dict() if month in monthly.index else None
    for c in fc["categories"]:
        p = plans[c["category"]]["amount"]
        c["plan"], c["plan_suggested"] = p, plans[c["category"]]["suggested"]
        c["status"], c["status_label"], c["vs_plan_pct"] = recommend.status(c["forecast"], p)
        c["actual"] = round(float(actual[c["category"]]), 2) if actual is not None and complete else None
    plan_total = sum(p["amount"] or 0 for p in plans.values())
    return {**fc, "currency": cur, "plan_total": plan_total, "agreement": agreement_state(db, hid, month),
            "month_is_past": complete, **win}


def recommendation_items(fc: dict) -> list[dict]:
    return [{"category": c["category"], "forecast": c["forecast"], "low": c["low"], "high": c["high"],
             "plan": c["plan"], "last_month": c["last_month"], "confidence": c["confidence"]} for c in fc["categories"]]


@router.get("/households/{hid}/recommendations/{month}")
def get_recommendations(hid: int, month: str, refresh: bool = False, user: User = Depends(current_user),
                        db: Session = Depends(get_db)):
    fc = get_forecast(hid, month, user, db)
    month = fc["month"]
    items = recommendation_items(fc)
    h = hashlib.sha256(json.dumps(items, sort_keys=True).encode()).hexdigest()
    row = db.query(RecommendationCache).filter_by(household_id=hid, month=month).first()
    if row and row.input_hash == h and not refresh:
        payload = json.loads(row.payload)
    else:
        payload = recommend.generate(items, month, len(fc["agreement"]["members"]), fc["currency"])
        if row:
            row.input_hash, row.payload = h, json.dumps(payload)
        else:
            db.add(RecommendationCache(household_id=hid, month=month, input_hash=h, payload=json.dumps(payload)))
        db.commit()
    mine = {f.category: f.value for f in db.query(Feedback).filter_by(household_id=hid, user_id=user.id, month=month)}
    return {**payload, "month": month, "my_feedback": mine}


class FeedbackIn(BaseModel):
    category: str
    value: int

    @field_validator("category")
    @classmethod
    def valid_cat(cls, v):
        if v not in CATEGORIES:
            raise ValueError(f"category must be one of {CATEGORIES}")
        return v

    @field_validator("value")
    @classmethod
    def pm1(cls, v):
        if v not in (-1, 0, 1):
            raise ValueError("value must be -1, 0 or 1")
        return v


@router.put("/households/{hid}/recommendations/{month}/feedback")
def recommendation_feedback(hid: int, month: str, body: FeedbackIn, user: User = Depends(current_user),
                            db: Session = Depends(get_db)):
    membership_or_404(db, hid, user)
    month = check_month(month)
    f = db.query(Feedback).filter_by(household_id=hid, user_id=user.id, month=month, category=body.category).first()
    if body.value == 0:
        if f:
            db.delete(f)
    elif f:
        f.value = body.value
    else:
        db.add(Feedback(household_id=hid, user_id=user.id, month=month, category=body.category, value=body.value))
    db.commit()
    return {"ok": True}


# ---------- dashboard, activity, export ----------
@router.get("/households/{hid}/summary/{month}")
def summary(hid: int, month: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    membership_or_404(db, hid, user)
    month = check_month(month)
    budget = get_budget(hid, month, user, db)
    first, end = month_bounds(month)
    by_member = (db.query(Expense.paid_by, func.sum(Expense.amount))
                 .filter(Expense.household_id == hid, Expense.spent_on >= first, Expense.spent_on < end)
                 .group_by(Expense.paid_by).all())
    return {**budget, "by_member": [{"user_id": u, "name": user_name(db, u), "amount": round(a, 2)} for u, a in by_member],
            "spent_total": round(sum(budget["spent"].values()), 2),
            "plan_total": sum(p["amount"] or 0 for p in budget["plans"].values())}


@router.get("/households/{hid}/activity")
def activity(hid: int, limit: int = 100, user: User = Depends(current_user), db: Session = Depends(get_db)):
    membership_or_404(db, hid, user)
    rows = db.query(Activity).filter_by(household_id=hid).order_by(Activity.id.desc()).limit(min(limit, 500))
    return [{"id": a.id, "action": a.action, "at": a.created_at.isoformat() + "Z", "user_id": a.user_id} for a in rows]


@router.get("/households/{hid}/export.csv")
def export_csv(hid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    membership_or_404(db, hid, user)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "category", "amount", "paid_by", "shared", "note"])
    for e in db.query(Expense).filter_by(household_id=hid).order_by(Expense.spent_on):
        w.writerow([e.spent_on.isoformat(), e.category, e.amount, user_name(db, e.paid_by), e.shared, e.note])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="household_{hid}_expenses.csv"'})


@router.get("/health")
def health():
    from . import config
    return {"ok": True, "llm": bool(config.LLM_API_KEY), "llm_provider": config.LLM_PROVIDER if config.LLM_API_KEY else None}
