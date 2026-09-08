"""Companies House, the UK public register of companies, as a payee and provider check.

Companies House verifies nothing itself: it reports what companies filed. This module reports what the
register says (legal name, status, registered office) and labels where the answer came from. With
COMPANIES_HOUSE_API_KEY set it calls the Public Data API (https://developer.company-information.service.gov.uk,
company profile by number and company search; basic auth with the key as the username, published rate limit
600 requests per five minutes). Without a key, offline, on an error or on a rate limit it answers from the
synthetic demo register in fixtures/pay/registry.json and says so. No bank account data lives here.
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config

API = os.environ.get("COMPANIES_HOUSE_API_URL", "https://api.company-information.service.gov.uk").rstrip("/")
_cache: dict[str, tuple[float, dict]] = {}
_TTL = 600
_backoff_until = 0.0


def key() -> str:
    return os.environ.get("COMPANIES_HOUSE_API_KEY", "").strip()


def mode() -> str:
    return "live" if key() else "demo"


def normalise_number(n: str | None) -> str:
    s = re.sub(r"\s", "", str(n or "")).upper()
    return s.zfill(8) if s.isdigit() and len(s) < 8 else s


def _demo_register() -> dict:
    return json.loads((config.FIXTURES_DIR / "registry.json").read_text())["companies_house"]


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _get(path: str, timeout: float = 6.0) -> tuple[int, dict | None]:
    req = urllib.request.Request(API + path)
    req.add_header("Authorization", "Basic " + base64.b64encode((key() + ":").encode()).decode())
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode() or "null")
    except urllib.error.HTTPError as e:
        return e.code, None


def _from_demo(number: str) -> dict:
    rec = _demo_register().get(number)
    if not rec:
        return {"number": number, "found": False, "source": "demo register (synthetic)", "checked_at": _now(), "note": "no entry on the demo register"}
    addr = rec.get("address", "")
    return {"number": number, "found": True, "legal_name": rec["name"], "status": rec["status"], "active": rec["status"] == "active", "type": rec.get("type", "ltd"),
            "incorporated": rec.get("incorporated"), "dissolved": rec.get("dissolved"), "address": addr, "source": "demo register (synthetic)", "checked_at": _now()}


def lookup(number: str | None) -> dict:
    """The register's record for a company number: {number, found, legal_name, status, active, address, source, checked_at}."""
    global _backoff_until
    number = normalise_number(number)
    if not number:
        return {"number": "", "found": False, "source": mode(), "checked_at": _now(), "note": "no company number given"}
    hit = _cache.get(number)
    if hit and time.time() - hit[0] < _TTL:
        return {**hit[1], "cached": True}
    if mode() == "live" and time.time() >= _backoff_until:
        try:
            status, body = _get(f"/company/{urllib.parse.quote(number)}")
            if status == 200 and isinstance(body, dict):
                ro = body.get("registered_office_address") or {}
                addr = ", ".join(x for x in (ro.get("address_line_1"), ro.get("address_line_2"), ro.get("locality"), ro.get("postal_code")) if x)
                out = {"number": number, "found": True, "legal_name": body.get("company_name"), "status": body.get("company_status"), "active": body.get("company_status") == "active",
                       "type": body.get("type"), "incorporated": body.get("date_of_creation"), "dissolved": body.get("date_of_cessation"), "address": addr, "source": "Companies House (live)", "checked_at": _now()}
            elif status == 404:
                out = {"number": number, "found": False, "source": "Companies House (live)", "checked_at": _now(), "note": "no company with this number on the register"}
            elif status == 429:
                _backoff_until = time.time() + 120
                out = {**_from_demo(number), "note": "Companies House rate limit reached; demo register answered"}
            else:
                out = {**_from_demo(number), "note": f"Companies House answered HTTP {status}; demo register answered"}
        except Exception as exc:  # noqa: BLE001
            out = {**_from_demo(number), "note": f"Companies House unreachable ({str(exc)[:80]}); demo register answered"}
    else:
        out = _from_demo(number)
        if mode() == "live":
            out["note"] = "Companies House rate limit reached earlier; demo register answered"
    _cache[number] = (time.time(), out)
    return out


def search(q: str) -> list[dict]:
    """Company search by name: a short list of {number, legal_name, status, address, source}."""
    q = (q or "").strip()
    if not q:
        return []
    global _backoff_until
    if mode() == "live" and time.time() >= _backoff_until:
        try:
            status, body = _get(f"/search/companies?q={urllib.parse.quote(q)}&items_per_page=6")
            if status == 200 and isinstance(body, dict):
                return [{"number": it.get("company_number"), "legal_name": it.get("title"), "status": it.get("company_status"), "address": (it.get("address_snippet") or ""), "source": "Companies House (live)"} for it in body.get("items", [])]
            if status == 429:
                _backoff_until = time.time() + 120   # the API's rate limit: fall back to the labelled synthetic register for two minutes
        except Exception:  # noqa: BLE001
            pass
    ql = q.lower()
    return [{"number": n, "legal_name": r["name"], "status": r["status"], "address": r.get("address", ""), "source": "demo register (synthetic)"} for n, r in _demo_register().items() if ql in r["name"].lower()][:6]


def names_match(filed: str | None, given: str | None) -> bool:
    norm = lambda s: re.sub(r"\b(limited|ltd\.?|plc)\b", "", str(s or "").lower()).replace(".", "").strip()  # noqa: E731
    return bool(filed) and norm(filed) == norm(given)
