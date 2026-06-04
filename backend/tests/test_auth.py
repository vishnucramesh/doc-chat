from __future__ import annotations

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from app.config import get_settings
from app.deps import require_user
from tests.conftest import TEST_PRIVATE_KEY_PEM


def _token(sub: str = "user-1", email: str = "u@example.com", **extra) -> str:
    payload = {"sub": sub, "email": email, "aud": "authenticated", **extra}
    return jwt.encode(payload, TEST_PRIVATE_KEY_PEM, algorithm="RS256")


def test_require_user_accepts_valid_bearer():
    user = require_user(authorization=f"Bearer {_token()}", settings=get_settings())
    assert user.id == "user-1"
    assert user.email == "u@example.com"


def test_require_user_rejects_missing_header():
    with pytest.raises(HTTPException) as exc:
        require_user(authorization=None, settings=get_settings())
    assert exc.value.status_code == 401


def test_require_user_rejects_token_signed_with_wrong_key():
    # Sign with a different RSA keypair than the one the JWKS stub serves.
    # The verifier should reject — this is the canonical "stolen JWT signed by
    # an attacker" scenario.
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_pem = other.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    bad = jwt.encode({"sub": "u", "aud": "authenticated"}, other_pem, algorithm="RS256")
    with pytest.raises(HTTPException) as exc:
        require_user(authorization=f"Bearer {bad}", settings=get_settings())
    assert exc.value.status_code == 401


def test_require_user_rejects_wrong_audience():
    # Right key, wrong `aud` claim — Supabase uses "authenticated" for
    # signed-in users; "service_role" tokens must NOT be accepted by the
    # user-facing API.
    tok = jwt.encode({"sub": "u", "aud": "service_role"}, TEST_PRIVATE_KEY_PEM, algorithm="RS256")
    with pytest.raises(HTTPException):
        require_user(authorization=f"Bearer {tok}", settings=get_settings())


def test_require_user_rejects_token_without_sub():
    tok = jwt.encode({"aud": "authenticated"}, TEST_PRIVATE_KEY_PEM, algorithm="RS256")
    with pytest.raises(HTTPException) as exc:
        require_user(authorization=f"Bearer {tok}", settings=get_settings())
    assert exc.value.status_code == 401
