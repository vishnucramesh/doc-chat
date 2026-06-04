"""Test setup.

Two responsibilities, both load-bearing for the test suite to even import:

1. **Seed env vars before any `app.*` import.** pydantic-settings reads the
   environment at first instantiation; without these, `from app.config import
   get_settings` blows up during test collection.

2. **Generate an RSA keypair and patch the JWKS client.** Auth now uses
   asymmetric RS256 verification against Supabase's JWKS endpoint. To
   exercise the real verification path without a network round-trip, we
   generate a keypair at import time and monkeypatch `app.deps._jwks_client`
   to return a stub that always yields the matching public key. Tests sign
   tokens with `TEST_PRIVATE_KEY_PEM` (exported from this module); the verify
   side then uses the public half, just like production.
"""

from __future__ import annotations

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "service")
os.environ.setdefault("NVIDIA_API_KEY", "nvapi-fake")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")

import pytest  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402

# Keypair generation runs once at module import (~50ms). 2048 bits is plenty
# for tests — production uses whatever Supabase's signing service uses.
_priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)

TEST_PRIVATE_KEY_PEM: bytes = _priv.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
_TEST_PUBLIC_KEY_PEM: bytes = _priv.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
)


class _StubSigningKey:
    """Mimics the surface area of jwt.PyJWK that `jwt.decode` actually uses."""

    def __init__(self, key_pem: bytes):
        self.key = key_pem


class _StubJWKSClient:
    """Replaces PyJWKClient. Always returns our test public key — sufficient
    for verifying that the real RS256 decode + audience/sub checks work."""

    def get_signing_key_from_jwt(self, _token: str) -> _StubSigningKey:
        return _StubSigningKey(_TEST_PUBLIC_KEY_PEM)


@pytest.fixture(autouse=True)
def _patch_jwks(monkeypatch: pytest.MonkeyPatch) -> None:
    # autouse so every test gets the patch — the real client tries to fetch
    # https://example.supabase.co/auth/v1/.well-known/jwks.json and time out.
    monkeypatch.setattr("app.deps._jwks_client", lambda _url: _StubJWKSClient())
