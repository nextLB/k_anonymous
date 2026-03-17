from __future__ import annotations

from django.conf import settings
from django.core import signing


def make_email_verification_token(*, user_id: int, email: str) -> str:
    payload = {"uid": int(user_id), "email": email}
    return signing.dumps(payload, salt="email-verify", compress=True)


def parse_email_verification_token(token: str) -> dict:
    max_age = int(getattr(settings, "ACCOUNT_EMAIL_VERIFICATION_SECONDS", 60 * 60 * 24 * 3))
    return signing.loads(token, salt="email-verify", max_age=max_age)

