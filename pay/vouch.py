"""vouch.finance adapter: mirror the passport's mandate on the vouch rail.

The bank mints the voucher when the customer signs its mandate and revokes it with the passport, so one
action by the bank is refused on two rails.

Two switches, both safe by default:
  VOUCH_MODE    fixture | live      fixture = canned responses, never touches the network
  PAYMENT_RAIL  local | vouch       vouch = also settle each ALLOW on the vouch rail

Live mode talks to the hackathon sandbox (https://cdir.vouch.finance/api/v1)
with the org's sk_test_ key in the x-api-key header. Mandates are AI Vouchers:
  POST   /ai-vouchers             {label, policy, metadata}  -> {id, keyPrefix}
  DELETE /ai-vouchers/{id}                                   -> revoked
  GET    /ai-vouchers/{id}                                   -> {status: ACTIVE|REVOKED, ...}
  GET    /ai-vouchers/{id}/ledger                            -> spend ledger entries
Payments (PAYMENT_RAIL=vouch) are intent -> quote -> authorize under
/payments/* and need x-privy-user-id + x-sim-time; a 403 is an expected deny.
They target a program on the rail that mirrors the customer's mandate: VOUCH_PROGRAM_ID, VOUCH_PRIVY_USER_ID
(the agent's identity on the rail), VOUCH_MERCHANTS (JSON map payee account -> merchant id), VOUCH_CATEGORY.
Any failure in live mode falls back to the fixture answer, labelled so the UI
never pretends. Verdicts come from HTTP responses, never from the SSE stream.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from . import config

FIXTURE_VOUCHER = "VCH-FIX-001"
_fixture_state: dict[str, str] = {}


def mode() -> str:
    return "live" if config.VOUCH_MODE == "live" and config.VOUCH_API_KEY else "fixture"


def rail() -> str:
    return "vouch" if config.PAYMENT_RAIL == "vouch" else "local"


def _req(method: str, path: str, body: dict | None = None, headers: dict | None = None, timeout: float = 15) -> tuple[int, dict | str | None]:
    """Returns (status, parsed body). Raises only on transport failure."""
    url = f"{config.VOUCH_BASE_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("x-api-key", config.VOUCH_API_KEY)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode()
            status = resp.status
    except urllib.error.HTTPError as e:
        text = e.read().decode(errors="replace")
        status = e.code
    try:
        return status, json.loads(text) if text else None
    except json.JSONDecodeError:
        return status, text


# ── org ────────────────────────────────────────────────────────────────────
def org_self() -> dict:
    if mode() != "live":
        return {"mode": "fixture", "org": None}
    try:
        status, body = _req("GET", "/hackathon/orgs/self")
        if status == 200 and isinstance(body, dict):
            return {"mode": "live", "org": {"id": body.get("orgId"), "name": body.get("name"), "is_hackathon_org": body.get("isHackathonOrg")}}
        return {"mode": "live-fallback", "org": None, "error": f"HTTP {status}"}
    except Exception as exc:  # noqa: BLE001
        return {"mode": "live-fallback", "org": None, "error": str(exc)[:200]}


# ── mandates ───────────────────────────────────────────────────────────────
def mint_mandate(passport: dict) -> dict:
    """Mirror the passport's mandate as an AI Voucher. Returns {voucher_id, mode, status, detail}."""
    proposed = passport.get("mandate_proposed") or {}
    ad = (proposed.get("authorization_details") or [{}])[0]
    monthly = float((ad.get("monthly_limit_per_account") or {}).get("amount") or 0)
    per = float((ad.get("per_payment_limit") or {}).get("amount") or 0)
    label = f"Agent Passport {passport['passport_id']} · {passport['agent_identity']['agent']['name']} for {(proposed.get('customer') or {}).get('legal_name') or 'customer mandates within the admission ceilings'}"
    body = {
        "label": label[:120],
        "policy": {"quota": {"totalCostUsd": monthly}},
        "metadata": {
            "passport_id": passport["passport_id"],
            "issuer": config.BANK_ID,
            "agent_id": passport["agent_identity"]["agent"]["agent_id"],
            "customer": (proposed.get("customer") or {}).get("legal_name"),
            "per_payment_limit": per, "monthly_limit_per_account": monthly, "currency": ad.get("currency"),
            "status_url": f"/api/status/{passport['passport_id']}",
            "compat": "docs/KYA_extension_for_purpose_bound_value.md",
        },
    }
    if mode() == "live":
        try:
            status, resp = _req("POST", "/ai-vouchers", body)
            if status in (200, 201) and isinstance(resp, dict) and resp.get("id"):
                return {"voucher_id": resp["id"], "mode": "live", "status": "ACTIVE", "detail": f"minted on the vouch rail (key prefix {resp.get('keyPrefix')})", "request": body}
            return _fixture_mint(passport, f"live mint failed: HTTP {status} {str(resp)[:160]}", body)
        except Exception as exc:  # noqa: BLE001
            return _fixture_mint(passport, f"live mint failed: {str(exc)[:160]}", body)
    return _fixture_mint(passport, None, body)


def _fixture_mint(passport: dict, error: str | None, body: dict) -> dict:
    vid = FIXTURE_VOUCHER if passport["passport_id"].endswith("0107") else f"VCH-FIX-{passport['passport_id'][-4:]}"
    _fixture_state[vid] = "ACTIVE"
    return {"voucher_id": vid, "mode": "live-fallback" if error else "fixture", "status": "ACTIVE",
            "detail": (error + "; fixture voucher recorded") if error else "fixture voucher recorded (no network call)", "request": body}


def revoke_mandate(voucher_id: str | None) -> dict:
    if not voucher_id:
        return {"ok": False, "mode": mode(), "status": None, "detail": "no voucher to revoke"}
    if mode() == "live" and not voucher_id.startswith("VCH-FIX"):
        try:
            status, resp = _req("DELETE", f"/ai-vouchers/{voucher_id}")
            if status in (200, 204):
                st = (resp or {}).get("status") if isinstance(resp, dict) else None
                return {"ok": True, "mode": "live", "status": st or "REVOKED", "detail": "revoked on the vouch rail"}
            if status == 404:
                return {"ok": False, "mode": "live", "status": "UNKNOWN", "detail": "voucher not found on the vouch rail"}
            return {"ok": True, "mode": "live-fallback", "status": "REVOKED", "detail": f"live revoke failed: HTTP {status}; fixture revoke recorded"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": True, "mode": "live-fallback", "status": "REVOKED", "detail": f"live revoke failed: {str(exc)[:160]}; fixture revoke recorded"}
    _fixture_state[voucher_id] = "REVOKED"
    return {"ok": True, "mode": "fixture", "status": "REVOKED", "detail": "fixture voucher revoked (no network call)"}


def mandate_status(voucher_id: str | None) -> dict:
    """Re-verify on the vouch rail. Returns {status, mode, detail}."""
    if not voucher_id:
        return {"status": None, "mode": mode(), "detail": "no voucher"}
    if mode() == "live" and not voucher_id.startswith("VCH-FIX"):
        try:
            status, resp = _req("GET", f"/ai-vouchers/{voucher_id}")
            if status == 200 and isinstance(resp, dict) and resp.get("status"):
                return {"status": str(resp["status"]).upper(), "mode": "live", "detail": f"read from the vouch rail (key prefix {resp.get('keyPrefix')}, {resp.get('totalRequestCount', 0)} requests)",
                        "raw": {k: resp.get(k) for k in ("id", "status", "label", "expiresAt", "createdAt")}}
            if status in (404, 410):
                return {"status": "REVOKED", "mode": "live", "detail": f"vouch rail answers HTTP {status}: voucher no longer exists"}
            return {"status": "UNKNOWN", "mode": "live-fallback", "detail": f"HTTP {status}"}
        except Exception as exc:  # noqa: BLE001
            return {"status": "UNKNOWN", "mode": "live-fallback", "detail": str(exc)[:160]}
    return {"status": _fixture_state.get(voucher_id, "ACTIVE"), "mode": "fixture", "detail": "fixture state"}


# ── payments (only when PAYMENT_RAIL=vouch) ────────────────────────────────
def settle_payment(instruction: dict) -> dict:
    """Settle an ALLOWed instruction on the vouch rail: intent -> quote -> authorize.
    Needs a seeded program: VOUCH_PROGRAM_ID, VOUCH_MERCHANT_ID, VOUCH_PRIVY_USER_ID (from the kit's state sidecar)."""
    if rail() != "vouch":
        return {"settled": True, "rail": "local", "rail_reason": "executed by the bank (local rail)", "ref": None}
    program, privy = os.environ.get("VOUCH_PROGRAM_ID"), os.environ.get("VOUCH_PRIVY_USER_ID")
    merchant = merchant_for(instruction.get("payee_account_ref"))
    if mode() != "live" or not (program and privy):
        return {"settled": True, "rail": "vouch-fallback", "rail_reason": "vouch rail not configured (needs VOUCH_PROGRAM_ID, VOUCH_PRIVY_USER_ID, VOUCH_MERCHANTS); fixture settlement", "ref": "TXN-FIX-001"}
    if not merchant:
        return {"settled": False, "rail": "vouch", "rail_reason": f"payee account {instruction.get('payee_account_ref')} has no merchant on the vouch rail", "ref": None}
    sim = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    hdr = {"x-privy-user-id": privy, "x-sim-time": sim}
    try:
        st, intent = _req("POST", "/payments/intents", {
            "merchantId": merchant, "programId": program,
            "items": [{"sku": instruction.get("invoice_ref") or "INV", "name": f"Invoice {instruction.get('invoice_ref')} {instruction.get('supplier_name')}", "categoryCode": os.environ.get("VOUCH_CATEGORY", "SUPPLIES"), "qty": 1, "unitPrice": float(instruction.get("amount") or 0)}],
        })
        if st not in (200, 201) or not isinstance(intent, dict):
            return {"settled": False, "rail": "vouch", "rail_reason": f"intent refused: HTTP {st} {str(intent)[:120]}", "ref": None}
        iid = intent.get("intentId") or intent.get("id")
        st, quote = _req("POST", "/payments/quote", {"intentId": iid}, hdr)
        if st == 403:
            return {"settled": False, "rail": "vouch", "rail_reason": f"declined at quote: {_reason(quote)}", "ref": iid}
        if st not in (200, 201):
            return {"settled": True, "rail": "vouch-fallback", "rail_reason": f"vouch rail error at quote (HTTP {st}); executed on the local rail", "ref": iid}
        st, auth = _req("POST", "/payments/authorize", {"intentId": iid}, hdr)
        if st >= 500:  # the sandbox's authorize step is intermittent; one retry before falling back
            time.sleep(1.5)
            st, auth = _req("POST", "/payments/authorize", {"intentId": iid}, hdr)
        if st == 403:
            return {"settled": False, "rail": "vouch", "rail_reason": f"declined at authorize: {_reason(auth)}", "ref": iid}
        if st in (200, 201):
            ref = (auth.get("authId") or auth.get("txnRef") or iid) if isinstance(auth, dict) else iid
            return {"settled": True, "rail": "vouch", "rail_reason": "quoted and authorized on the vouch rail", "ref": ref}
        # 5xx or anything else is a rail fault, not a decision: the bank's ALLOW stands and the local rail executes
        return {"settled": True, "rail": "vouch-fallback", "rail_reason": f"vouch rail error at authorize (HTTP {st}: {_reason(auth)[:80]}); executed on the local rail", "ref": iid}
    except Exception as exc:  # noqa: BLE001
        return {"settled": True, "rail": "vouch-fallback", "rail_reason": f"vouch rail unreachable ({str(exc)[:100]}); executed on the local rail", "ref": "TXN-FIX-001"}


def merchant_for(payee_account_ref: str | None) -> str | None:
    """VOUCH_MERCHANTS is a JSON map {payee_account_ref: merchant id on the rail}; VOUCH_MERCHANT_ID is a single fallback."""
    digits = "".join(ch for ch in str(payee_account_ref or "") if ch.isdigit())
    try:
        table = json.loads(os.environ.get("VOUCH_MERCHANTS") or "{}")
    except json.JSONDecodeError:
        table = {}
    for k, v in table.items():
        if "".join(ch for ch in k if ch.isdigit()) == digits and digits:
            return v
    return os.environ.get("VOUCH_MERCHANT_ID")


def _reason(body) -> str:
    if isinstance(body, dict):
        return str(body.get("reason") or body.get("error") or body.get("message") or body)[:160]
    return str(body)[:160]
