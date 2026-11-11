from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException

from main import JWT_SECRET, TRAINING_USERNAME, get_current_user


def signed_token(subject: str, expires_at: datetime, secret: str) -> str:
    return jwt.encode(
        {"sub": subject, "exp": expires_at},
        secret,
        algorithm="HS256",
    )


def outcome(token: str) -> str:
    try:
        get_current_user(token)
        return "accepted"
    except HTTPException as exc:
        return str(exc.status_code)


future = datetime.now(timezone.utc) + timedelta(minutes=5)
past = datetime.now(timezone.utc) - timedelta(minutes=1)

checks = [
    ("Configured user", signed_token(TRAINING_USERNAME, future, JWT_SECRET), "accepted"),
    ("Unrelated user", signed_token(TRAINING_USERNAME + "-other", future, JWT_SECRET), "401"),
    ("Expired token", signed_token(TRAINING_USERNAME, past, JWT_SECRET), "401"),
    ("Wrong signature", signed_token(TRAINING_USERNAME, future, "different-secret"), "401"),
]

failures = 0
for label, token, expected in checks:
    actual = outcome(token)
    print(f"{label}: {actual} (expected {expected})")
    if actual != expected:
        failures += 1

if failures:
    raise SystemExit(1)

print("All JWT checks passed.")