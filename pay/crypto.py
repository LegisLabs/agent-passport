"""Keys, JWTs and nonces for the composite passport.

Three signers, each entitled to exactly one claim set:
  authority  signs the assurance JWT      (KY-A assurance + supervisor condition)
  payrail    signs the agent_identity JWT (agent name, agent public key, software, config hash)
  northgate  signs the mandate JWT        (supplier allowlist, limits, expiry)
Each is an Ed25519 key generated once into KEYS_DIR (never committed). The
agent has a fourth key, generated per application; the demo agent lives inside
this process, so its private key is kept in the database for the simulation.
A rogue key is generated on demand for the stolen-passport beat.

JWT = RFC 7519 compact serialisation, alg EdDSA (RFC 8037), via PyJWT. The three
envelope parts are W3C Verifiable Credentials in the JWT profile (`typ: vc+jwt`,
a `vc` object carrying @context, type and credentialSubject); receipts and
delegations are plain JWTs, because neither is a credential.
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


def sign_jwt_pem(priv_pem: str, payload: dict, typ: str = "JWT") -> str:
    """Sign with an arbitrary Ed25519 private key (an agent's), kid = thumbprint of its public key."""
    priv = serialization.load_pem_private_key(priv_pem.encode(), password=None)
    pub_pem = priv.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    kid = jwk_thumbprint(public_jwk(pub_pem))[:16]
    return jwt.encode(payload, priv_pem, algorithm="EdDSA", headers={"kid": kid, "typ": typ})


def verify_jwt_jwk(jwk: dict | None, token: str | None) -> dict | None:
    """Payload if the token verifies against the Ed25519 public key in this JWK, else None."""
    if not jwk or not token:
        return None
    try:
        pub = Ed25519PublicKey.from_public_bytes(b64u_decode(jwk["x"]))
        pem = pub.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        return jwt.decode(token, pem, algorithms=["EdDSA"], options={"verify_exp": False, "verify_nbf": False, "verify_aud": False})
    except Exception:  # noqa: BLE001
        return None


def decode_unverified(token: str) -> tuple[dict, dict]:
    """Header and payload exactly as they sit on the wire, credential structure included:
    this is what the console prints, so a reader can check the VC for themselves."""
    header = jwt.get_unverified_header(token)
    payload = jwt.decode(token, options={"verify_signature": False})
    return header, payload


# ── the three parts as W3C Verifiable Credentials (JWT profile) ────────────
VC_TYP = "vc+jwt"
VC_CONTEXT = ["https://www.w3.org/ns/credentials/v2"]

# envelope part → (the signer entitled to the claim set, credential type). The Builder Guide calls the
# provider's part its attestation; the envelope key stays agent_identity because that is what it names.
CREDENTIALS = {
    "assurance": ("authority", "AgentAssuranceCredential"),
    "agent_identity": ("payrail", "AgentAttestationCredential"),
    "mandate": ("northgate", "PaymentMandateCredential"),
}


def sign_credential(part: str, subject_id: str | None, claims: dict, credential_subject: dict) -> str:
    """One envelope part as a W3C VC, JWT profile: registered claims (iss, sub, jti, iat, nbf, exp,
    cnf) stay at the top level; everything the issuer asserts about the agent goes in
    credentialSubject. No JSON-LD processing is required to read it."""
    name, vc_type = CREDENTIALS[part]
    subject = {"id": subject_id, **credential_subject} if subject_id else dict(credential_subject)
    payload = {**claims, "vc": {"@context": VC_CONTEXT, "type": ["VerifiableCredential", vc_type], "credentialSubject": subject}}
    return sign_jwt(name, payload, typ=VC_TYP)


def flatten_credential(payload: dict) -> dict:
    """The claims as every reader expects them: JWT claims with credentialSubject merged back in.
    Where the credential puts a claim is a question for the format, not for the rules."""
    vc = payload.get("vc")
    if not isinstance(vc, dict):
        return payload
    flat = {k: v for k, v in payload.items() if k != "vc"}
    flat.update(vc.get("credentialSubject") or {})
    return flat


def verify_credential(part: str, token: str | None) -> dict | None:
    """Flattened claims if this part verifies against the signer entitled to it and carries the
    credential type that part must have, else None. The type check is what stops an assurance
    being presented as a mandate, and is what makes the W3C VC label mean something."""
    name, vc_type = CREDENTIALS[part]
    payload = verify_jwt(name, token)
    if payload is None or vc_type not in ((payload.get("vc") or {}).get("type") or []):
        return None
    return flatten_credential(payload)


def verify_envelope(env: dict) -> dict:
    """Checks all three credentials against the party entitled to each claim set, and that each
    carries its own credential type.

    Returns {ok, failure, assurance, agent_identity, mandate}: `failure` is the
    first part that did not verify ("assurance" | "agent_identity" |
    "mandate_missing" | "mandate"), or None. Payloads are None when unverified.
    """
    out = {"ok": False, "failure": None, "assurance": None, "agent_identity": None, "mandate": None}
    out["assurance"] = verify_credential("assurance", env.get("assurance"))
    if out["assurance"] is None:
        out["failure"] = "assurance"
        return out
    out["agent_identity"] = verify_credential("agent_identity", env.get("agent_identity"))
    if out["agent_identity"] is None:
        out["failure"] = "agent_identity"
        return out
    if not env.get("mandate"):
        out["failure"] = "mandate_missing"
        return out
    out["mandate"] = verify_credential("mandate", env.get("mandate"))
    if out["mandate"] is None:
        out["failure"] = "mandate"
        return out
    out["ok"] = True
    return out


def new_nonce() -> str:
    return b64u(secrets.token_bytes(24))
