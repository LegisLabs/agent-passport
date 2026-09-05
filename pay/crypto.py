"""Keys, JWTs and nonces for the composite passport.

Three signers, each entitled to exactly one claim set:
  authority  signs the assurance JWT      (KY-A assurance + supervisor condition)
  payrail    signs the agent_identity JWT (agent name, agent public key, software, config hash)
  northgate  signs the mandate JWT        (supplier allowlist, limits, expiry)
Each is an Ed25519 key generated once into KEYS_DIR (never committed). The
agent has a fourth key, generated per application; the demo agent lives inside
this process, so its private key is kept in the database for the simulation.
A rogue key is generated on demand for the stolen-passport beat.

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

SIGNERS = ("authority", "payrail", "northgate")


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


def verify_with_jwk(jwk: dict, data: bytes, sig_b64u: str) -> bool:
    try:
        pub = Ed25519PublicKey.from_public_bytes(b64u_decode(jwk["x"]))
        pub.verify(b64u_decode(sig_b64u), data)
        return True
    except Exception:  # noqa: BLE001
        return False


# ── the three persisted signers ────────────────────────────────────────────
_keys: dict[str, dict] = {}


def signer(name: str) -> dict:
    """{private_pem, public_pem, jwk, kid} for authority | payrail | northgate."""
    if name not in SIGNERS:
        raise KeyError(name)
    if name in _keys:
        return _keys[name]
    config.KEYS_DIR.mkdir(parents=True, exist_ok=True)
    priv_path = config.KEYS_DIR / f"{name}_ed25519.pem"
    pub_path = config.KEYS_DIR / f"{name}_ed25519.pub.pem"
    if not priv_path.exists():
        priv_pem, pub_pem = generate_keypair()
        priv_path.write_text(priv_pem)
        pub_path.write_text(pub_pem)
    priv_pem, pub_pem = priv_path.read_text(), pub_path.read_text()
    jwk = public_jwk(pub_pem)
    _keys[name] = {"name": name, "private_pem": priv_pem, "public_pem": pub_pem, "jwk": jwk, "kid": jwk_thumbprint(jwk)[:16]}
    return _keys[name]


def all_signers() -> dict:
    return {n: signer(n) for n in SIGNERS}


# ── JWTs ───────────────────────────────────────────────────────────────────
def sign_jwt(name: str, payload: dict, typ: str = "JWT") -> str:
    s = signer(name)
    return jwt.encode(payload, s["private_pem"], algorithm="EdDSA", headers={"kid": s["kid"], "typ": typ})


def verify_jwt(name: str, token: str | None) -> dict | None:
    """Payload if the signature verifies against that signer's key, else None.
    Expiry is checked by the rule that owns it (R.2 / R.5), not here, so the
    rule that fails is the honest one."""
    if not token:
        return None
    try:
        return jwt.decode(
            token, signer(name)["public_pem"], algorithms=["EdDSA"],
            options={"verify_exp": False, "verify_nbf": False, "verify_aud": False},
        )
    except Exception:  # noqa: BLE001
        return None


def decode_unverified(token: str) -> tuple[dict, dict]:
    header = jwt.get_unverified_header(token)
    payload = jwt.decode(token, options={"verify_signature": False})
    return header, payload


def verify_envelope(env: dict) -> dict:
    """Checks all three JWTs against the party entitled to each claim set.

    Returns {ok, failure, assurance, agent_identity, mandate}: `failure` is the
    first part that did not verify ("assurance" | "agent_identity" |
    "mandate_missing" | "mandate"), or None. Payloads are None when unverified.
    """
    out = {"ok": False, "failure": None, "assurance": None, "agent_identity": None, "mandate": None}
    out["assurance"] = verify_jwt("authority", env.get("assurance"))
    if out["assurance"] is None:
        out["failure"] = "assurance"
        return out
    out["agent_identity"] = verify_jwt("payrail", env.get("agent_identity"))
    if out["agent_identity"] is None:
        out["failure"] = "agent_identity"
        return out
    if not env.get("mandate"):
        out["failure"] = "mandate_missing"
        return out
    out["mandate"] = verify_jwt("northgate", env.get("mandate"))
    if out["mandate"] is None:
        out["failure"] = "mandate"
        return out
    out["ok"] = True
    return out


def new_nonce() -> str:
    return b64u(secrets.token_bytes(24))
