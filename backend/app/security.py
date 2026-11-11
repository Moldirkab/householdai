"""Password hashing (PBKDF2-SHA256, standard library) and bearer-token authentication."""
import hashlib
import hmac
import secrets

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .db import get_db
from .models import Household, Membership, Token, User

ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, digest = stored.split("$")
        check = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
        return hmac.compare_digest(check, digest)
    except ValueError:
        return False


def new_token(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    db.add(Token(token=token, user_id=user.id))
    db.commit()
    return token


def current_user(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> User:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Please log in.")
    row = db.get(Token, authorization.split(" ", 1)[1].strip())
    user = db.get(User, row.user_id) if row else None
    if not user:
        raise HTTPException(401, "Your session has expired. Please log in again.")
    return user


def membership_or_404(db: Session, household_id: int, user: User) -> Membership:
    m = db.query(Membership).filter_by(household_id=household_id, user_id=user.id).first()
    if not m or not db.get(Household, household_id):
        raise HTTPException(404, "Household not found or you are not a member.")
    return m


def require_role(m: Membership, allowed: set[str], action: str) -> None:
    if m.role not in allowed:
        raise HTTPException(403, f"Your role ({m.role}) cannot {action}.")
