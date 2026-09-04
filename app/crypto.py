"""Keys, JWTs and nonces.

Authority key: Ed25519, generated once into KEYS_DIR (never committed).
Agent keys: Ed25519, generated per application; the demo "agent" lives inside
this process, so its private key is kept in the database for the simulation.
A rogue key is generated on demand to play the stolen-passport beat.

JWT = RFC 7519 compact serialisation, alg EdDSA (RFC 8037), via PyJWT.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import datetime, timezone

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from . import config


# ── helpers ────────────────────────────────────────────────────────────────
def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64u_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# ── key pairs ──────────────────────────────────────────────────────────────
def generate_keypair() -> tuple[str, str]:
    """Returns (private_pem, public_pem)."""
    priv = Ed25519PrivateKey.generate()
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    pub_pem = priv.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    return priv_pem, pub_pem


def public_jwk(pub_pem: str) -> dict:
    pub = serialization.load_pem_public_key(pub_pem.encode())
    raw = pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return {"kty": "OKP", "crv": "Ed25519", "x": b64u(raw)}


def jwk_thumbprint(jwk: dict) -> str:
    """RFC 7638 thumbprint (base64url of SHA-256 over the canonical required members)."""
    canon = json.dumps({"crv": jwk["crv"], "kty": jwk["kty"], "x": jwk["x"]}, separators=(",", ":"), sort_keys=True)
    return b64u(hashlib.sha256(canon.encode()).digest())


def sign_bytes(priv_pem: str, data: bytes) -> str:
    priv = serialization.load_pem_private_key(priv_pem.encode(), password=None)
    return b64u(priv.sign(data))


def verify_bytes(pub_pem: str, data: bytes, sig_b64u: str) -> bool:
    try:
        pub = serialization.load_pem_public_key(pub_pem.encode())
        assert isinstance(pub, Ed25519PublicKey)
        pub.verify(b64u_decode(sig_b64u), data)
        return True
    except Exception:  # noqa: BLE001 — any failure is "not verified"
        return False


# ── authority key (persisted) ──────────────────────────────────────────────
_authority: dict | None = None


def authority_keys() -> dict:
    global _authority
    if _authority:
        return _authority
    config.KEYS_DIR.mkdir(parents=True, exist_ok=True)
    priv_path = config.KEYS_DIR / "authority_ed25519.pem"
    pub_path = config.KEYS_DIR / "authority_ed25519.pub.pem"
    if not priv_path.exists():
        priv_pem, pub_pem = generate_keypair()
        priv_path.write_text(priv_pem)
        pub_path.write_text(pub_pem)
    priv_pem, pub_pem = priv_path.read_text(), pub_path.read_text()
    jwk = public_jwk(pub_pem)
    _authority = {"private_pem": priv_pem, "public_pem": pub_pem, "jwk": jwk, "kid": jwk_thumbprint(jwk)[:16]}
    return _authority


# ── JWTs ───────────────────────────────────────────────────────────────────
def sign_jwt(payload: dict, typ: str = "JWT") -> str:
    a = authority_keys()
    return jwt.encode(payload, a["private_pem"], algorithm="EdDSA", headers={"kid": a["kid"], "typ": typ})


def verify_jwt(token: str, check_exp: bool = False) -> dict | None:
    """Returns the payload if the signature verifies, else None. Expiry is
    checked by rule R.2 against the registry, not here, so the rule that
    fails is the honest one."""
    try:
        return jwt.decode(
            token, authority_keys()["public_pem"], algorithms=["EdDSA"],
            options={"verify_exp": check_exp, "verify_nbf": False, "verify_aud": False},
        )
    except Exception:  # noqa: BLE001
        return None


def decode_unverified(token: str) -> tuple[dict, dict]:
    header = jwt.get_unverified_header(token)
    payload = jwt.decode(token, options={"verify_signature": False})
    return header, payload


def new_nonce() -> str:
    return b64u(secrets.token_bytes(24))
