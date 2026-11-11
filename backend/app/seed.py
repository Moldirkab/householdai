"""Demo households containing ONLY real data from the research dataset.

Each demo household holds the real BLS Consumer Expenditure Survey series used in the research
(backend/data/ce_monthly_2017_2024.csv): the weighted average monthly expenditure per U.S. household, by category,
January 2017 - December 2024, in USD, with the real dates. Nothing is invented: no fictional members, no random
transactions, no shifted dates and no pre-set budgets. Each record is one real monthly category value
(Food is stored as its two real components, Groceries and Dining out).

Dataset records are read-only in the app. Survey participants use their own accounts and join a demo household
with its invite code (DEMOG1, DEMOG2, ...).

    python -m app.seed               # create demo household G1 if it does not exist
    python -m app.seed --groups 6    # create G1..G6 (one per survey group)
    python -m app.seed --reset       # delete the database and start again with G1
"""
from __future__ import annotations

import argparse
from datetime import date

import pandas as pd

from .config import NATIONAL_DATA
from .db import Base, SessionLocal, engine, migrate
from .models import CATEGORIES, Activity, Expense, Household, Membership, User
from .security import hash_password

DEMO_PASSWORD = "demo1234"
SOURCE_NOTE = "BLS CE {part}: weighted average per U.S. household"


def create_demo_household(db, group: int) -> Household | None:
    name = f"Demo household G{group} (BLS data)"
    if db.query(Household).filter_by(name=name).first():
        return None
    bls = pd.read_csv(NATIONAL_DATA, index_col=0, parse_dates=True)

    owner_email = f"g{group}.demo@demo.kz"
    owner = db.query(User).filter_by(email=owner_email).first() or User(
        name=f"Demo account G{group}", email=owner_email, password_hash=hash_password(DEMO_PASSWORD))
    db.add(owner)
    h = Household(name=name, currency="$", invite_code=f"DEMOG{group}", data_source="bls")
    db.add(h)
    db.flush()
    db.add(Membership(household_id=h.id, user_id=owner.id, role="owner"))

    for ts, row in bls.iterrows():
        day = date(ts.year, ts.month, 1)
        for c in CATEGORIES:
            parts = [("Groceries", row["Groceries"]), ("Dining out", row["Dining out"])] if c == "Food" else [(c, row[c])]
            for part, value in parts:
                db.add(Expense(household_id=h.id, paid_by=None, created_by=None, category=c, amount=round(float(value), 2),
                               spent_on=day, note=SOURCE_NOTE.format(part=part), shared=True))
    first, last = bls.index.min().strftime("%Y-%m"), bls.index.max().strftime("%Y-%m")
    db.add(Activity(household_id=h.id, user_id=None,
                    action=f"Real data loaded: BLS Consumer Expenditure Survey, weighted average monthly spending per "
                           f"U.S. household, {first} to {last} (USD, {len(bls)} months). Source: research dataset "
                           f"ce_monthly_2017_2024.csv. Not the spending of any member of this household."))
    db.commit()
    return h


def seed(groups: int = 1, reset: bool = False) -> list[str]:
    if reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    migrate()
    db = SessionLocal()
    try:
        made = [h.name for g in range(1, groups + 1) if (h := create_demo_household(db, g))]
    finally:
        db.close()
    return made


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--groups", type=int, default=1)
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args()
    made = seed(a.groups, a.reset)
    print("Created:", ", ".join(made) if made else "nothing new (already exists)")
    print(f"Demo login: g1.demo@demo.kz / {DEMO_PASSWORD} (g2.demo@demo.kz ... for other groups). "
          "Participants create their own account and join with invite code DEMOG1, DEMOG2, ...")
