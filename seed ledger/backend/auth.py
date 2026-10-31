"""Password hashing and session authentication."""

import hashlib
import hmac
import secrets

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import Account, LoginSession


# ---------------------------------------------------------
# Password hashing
# ---------------------------------------------------------

def hash_password(password):
    """Store a salted password hash rather than plain text."""
    salt = secrets.token_hex(16)

    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt.encode("utf-8"),
        n=16384,
        r=8,
        p=1,
    ).hex()

    return f"{salt}${digest}"


def verify_password(password, stored):
    """Compare the supplied password with its stored hash."""
    try:
        salt, expected = stored.split("$", 1)

        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt.encode("utf-8"),
            n=16384,
            r=8,
            p=1,
        ).hex()

        return hmac.compare_digest(digest, expected)

    except (ValueError, TypeError, AttributeError):
        return False


# ---------------------------------------------------------
# Session creation
# ---------------------------------------------------------

def new_session(db, account_id):
    """Create a random login token valid for 12 hours."""
    token = secrets.token_urlsafe(32)

    token_hash = hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()

    expires_at = (
        datetime.now(timezone.utc).replace(tzinfo=None)
        + timedelta(hours=12)
    )

    session = LoginSession(
        token_hash=token_hash,
        account_id=account_id,
        expires_at=expires_at,
    )

    db.add(session)
    db.commit()

    # The browser receives the token.
    # The database stores only its hash.
    return token


# ---------------------------------------------------------
# Check the current signed-in account
# ---------------------------------------------------------

def current_account(
    request: Request,
    db: Session = Depends(get_db),
):
    authorization = request.headers.get("Authorization", "")

    scheme, _, token = authorization.partition(" ")

    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=401,
            detail="Please sign in again.",
        )

    token_hash = hashlib.sha256(
        token.strip().encode("utf-8")
    ).hexdigest()

    session = db.get(LoginSession, token_hash)

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    if session is None or session.expires_at <= now:
        raise HTTPException(
            status_code=401,
            detail="Please sign in again.",
        )

    account = db.get(Account, session.account_id)

    if account is None:
        raise HTTPException(
            status_code=401,
            detail="Account not found. Please sign in again.",
        )

    return account