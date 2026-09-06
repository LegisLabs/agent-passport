"""The model at the edges, payments vertical.

extract(documents)  Gemini reads the evidence pack into a fixed schema. Every
                    fact carries source_doc + verbatim quote. JSON mode,
                    temperature 0. On any failure, the fixture is returned and
                    the mode is reported as "gemini-fallback" so the UI never
                    pretends.
draft_file_note()   Gemini phrases the structured check results as a short
                    officer file note. Draft only; never a decision.
"""
from __future__ import annotations

import json
import re
import time

from . import config

SECTIONS = ("provider", "accountable_person", "insurance", "agent", "customer", "mandate")


def fixture() -> dict:
    d = json.loads((config.FIXTURES_DIR / "extraction_fixture.json").read_text())
    d.pop("_comment", None)
    return d


def _blank_schema(fx: dict):
    """Same shape as the fixture with values emptied, to show the model the target."""
    def blank(x):
        if isinstance(x, dict):
            if set(x) >= {"value", "source_doc", "quote"}:
                return {"value": "<value or null>", "source_doc": "<file name>", "quote": "<verbatim words from the document>"}
            return {k: blank(v) for k, v in x.items()}
        if isinstance(x, list):
            return [blank(x[0])] if x else []
        return x
    return blank(fx)


def _client():
    from google import genai
    from google.genai import types
    return genai.Client(api_key=config.GEMINI_API_KEY, http_options=types.HttpOptions(timeout=90_000)), types


def _strip_fences(text: str) -> str:
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text.strip(), re.DOTALL)
    return m.group(1) if m else text.strip()


def _generate_json(prompt: str, retries: int = 1) -> dict:
    client, types = _client()
    last = None
    for attempt in range(retries + 1):
        try:
            resp = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0),
            )
            return json.loads(_strip_fences(resp.text or ""))
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt < retries:
                time.sleep(1.5)
    raise RuntimeError(f"Gemini failed: {last}")


def _num(v):
    if isinstance(v, (int, float)):
        return v
    digits = re.sub(r"[^\d.]", "", str(v or ""))
    return float(digits) if digits else None


def _iso_date(v):
    """'31 March 2027' / '2027-03-31' / '31/03/2027' -> '2027-03-31'; anything else unchanged."""
    from datetime import datetime
    if not v:
        return v
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%d/%m/%Y", "%B %d, %Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return s


def _account(v):
    """Normalise '60-11-22 44556677' / '601122 44556677' / '60-11-22, 44556677' -> '60-11-22 44556677'."""
    digits = re.sub(r"\D", "", str(v or ""))
    if len(digits) == 14:
        return f"{digits[0:2]}-{digits[2:4]}-{digits[4:6]} {digits[6:]}"
    return str(v or "").strip()


def _validate(out: dict) -> dict:
    """Shape check and normalisation only. The rules do the real checking."""
    fx = fixture()
    for section in SECTIONS:
        if not isinstance(out.get(section), dict):
            raise ValueError(f"missing section {section}")
        for k in fx[section]:
            v = out[section].get(k)
            if not isinstance(v, dict) or "value" not in v:
                out[section][k] = {"value": None, "source_doc": None, "quote": None}
    if not isinstance(out.get("suppliers"), list):
        raise ValueError("suppliers must be a list")
    for s in out["suppliers"]:
        s["account_ref"] = _account(s.get("account_ref"))
        s["supplier_id"] = str(s.get("supplier_id") or "").strip().upper()
    m = out["mandate"]
    at = str(m["action_type"]["value"] or "").lower()
    m["action_type"]["value"] = "pay_invoice" if "pay" in at or "invoice" in at else m["action_type"]["value"]
    for k in ("per_payment_limit_gbp", "monthly_limit_per_account_gbp", "human_confirm_above_gbp"):
        m[k]["value"] = _num(m[k]["value"])
    m["valid_until"]["value"] = _iso_date(m["valid_until"]["value"])
    ins = out["insurance"]
    ins["cover_gbp"]["value"] = _num(ins["cover_gbp"]["value"])
    ins["valid_until"]["value"] = _iso_date(ins["valid_until"]["value"])
    ap = out["accountable_person"]
    decl = ap["declaration_accepted"]
    quote = str(decl.get("quote") or "").lower()
    decl["value"] = decl["value"] is True or str(decl["value"]).lower() in ("true", "yes") or "accept responsibility" in quote
    ag = out["agent"]
    ag["config_hash"]["value"] = str(ag["config_hash"]["value"] or "").strip().lower() or None
    for sec in ("provider", "customer"):
        ch = out[sec]["companies_house_number"]
        ch["value"] = re.sub(r"\D", "", str(ch["value"] or "")) or None
    return out


def extract(documents: list[dict]) -> tuple[dict, str]:
    """Returns (facts, mode). mode is gemini | fixture | gemini-fallback."""
    if config.EXTRACTION_MODE != "gemini" or not config.GEMINI_API_KEY:
        return fixture(), "fixture"
    docs_text = "\n\n".join(f"=== FILE: {d['name']} ===\n{d['text']}" for d in documents)
    prompt = (
        "You are an extraction function, not an adviser. Read the documents below and fill the JSON schema. "
        "Rules: copy values verbatim from the documents; for every field give source_doc (the FILE name) and quote "
        "(the exact words the value came from); if a value is absent use null; do not infer, summarise or judge; "
        "do not add fields. Booleans must be true/false. Numbers must be plain numbers (no currency symbols). "
        "Dates must be ISO (YYYY-MM-DD). Supplier rows: one object per supplier in the allowlist table, account_ref "
        "as 'sort-code accountnumber' e.g. '60-11-22 44556677'. action_type is pay_invoice when the agreement permits "
        "paying invoices. config_hash is the SHA-256 hex string in the technical description. declaration_accepted is "
        "true when the named person states in writing that they accept responsibility for the agent's actions. "
        "human_confirm_above_gbp is the amount above which instructions are held for human confirmation.\n\n"
        f"SCHEMA:\n{json.dumps(_blank_schema(fixture()), indent=1)}\n\nDOCUMENTS:\n{docs_text}\n\nReturn only the JSON."
    )
    try:
        out = _validate(_generate_json(prompt))
        return out, "gemini"
    except Exception as exc:  # noqa: BLE001
        fx = fixture()
        fx["_fallback_reason"] = str(exc)[:300]
        return fx, "gemini-fallback"


def draft_file_note(ref: str, fields: dict, checks: list[dict]) -> tuple[str, str]:
    """Officer's plain-English file note. Returns (text, mode)."""
    flagged = [c for c in checks if c["result"] != "pass"]
    if config.EXTRACTION_MODE != "gemini" or not config.GEMINI_API_KEY:
        return _fixture_note(ref, fields, checks, flagged), "fixture"
    summary = {
        "reference": ref,
        "provider": fields["provider"]["legal_name"]["value"],
        "agent": fields["agent"]["agent_name"]["value"],
        "customer": fields["customer"]["legal_name"]["value"],
        "requested": {k: v["value"] for k, v in fields["mandate"].items()},
        "checks": [{"id": c["id"], "title": c["title"], "result": c["result"], "detail": c["detail"]} for c in checks],
    }
    prompt = (
        "Write a file note for a payments-supervisor case officer in plain English, British spelling, sentence case, "
        "at most 120 words, no bullet points, no headings. State what was applied for, which automated checks passed, "
        "and name each flagged item and what it means. Do NOT recommend approval or rejection and do NOT use the words "
        "'approve', 'reject', 'recommend', 'should'. The decision belongs to the officer. Return JSON {\"note\": \"...\"}.\n\n"
        f"{json.dumps(summary, indent=1)}"
    )
    try:
        out = _generate_json(prompt)
        note = str(out.get("note", "")).strip()
        for banned in ("approve", "reject", "recommend"):
            if banned in note.lower():
                raise ValueError("verdict vocabulary in draft")
        return note, "gemini"
    except Exception:  # noqa: BLE001
        return _fixture_note(ref, fields, checks, flagged), "gemini-fallback"


def _fixture_note(ref, fields, checks, flagged) -> str:
    m = {k: v["value"] for k, v in fields["mandate"].items()}
    passed = sum(1 for c in checks if c["result"] == "pass")
    s = (f"Application {ref} from {fields['provider']['legal_name']['value']} seeks assurance for agent "
         f"{fields['agent']['agent_name']['value']} to initiate supplier payments for {fields['customer']['legal_name']['value']}: "
         f"up to £{float(m['per_payment_limit_gbp'] or 0):,.0f} per payment and £{float(m['monthly_limit_per_account_gbp'] or 0):,.0f} per supplier account in 30 days, "
         f"until {m['valid_until']}. {passed} of {len(checks)} automated checks passed.")
    if flagged:
        s += " Flagged: " + "; ".join(f"{c['id']} {c['detail']}" for c in flagged) + "."
    return s


# ── Invoice reading by the agent (Task 1: the visible AI-manipulation moment) ──
INVOICE_FIELDS = ("supplier_name", "invoice_ref", "amount_gbp", "sort_code", "account_number", "due_date", "bank_details_changed")


def invoices() -> dict:
    """{invoice_id: text} for the synthetic invoices the agent can read."""
    return {p.stem: p.read_text() for p in sorted((config.FIXTURES_DIR / "invoices").glob("*.txt"))}


def invoice_fixture(invoice_id: str) -> dict:
    d = json.loads((config.FIXTURES_DIR / "invoices" / "invoice_fixture.json").read_text())
    return d[invoice_id]


def _validate_invoice(out: dict, invoice_id: str) -> dict:
    for k in INVOICE_FIELDS:
        v = out.get(k)
        if not isinstance(v, dict) or "value" not in v:
            out[k] = {"value": None, "source_doc": f"{invoice_id}.txt", "quote": None}
    out["amount_gbp"]["value"] = _num(out["amount_gbp"]["value"])
    out["sort_code"]["value"] = re.sub(r"[^\d]", "", str(out["sort_code"]["value"] or ""))
    sc = out["sort_code"]["value"]
    out["sort_code"]["value"] = f"{sc[0:2]}-{sc[2:4]}-{sc[4:6]}" if len(sc) == 6 else (out["sort_code"]["value"] or None)
    out["account_number"]["value"] = re.sub(r"\D", "", str(out["account_number"]["value"] or "")) or None
    out["due_date"]["value"] = _iso_date(out["due_date"]["value"])
    b = out["bank_details_changed"]["value"]
    out["bank_details_changed"]["value"] = b is True or str(b).lower() in ("true", "yes")
    return out


def extract_invoice(invoice_id: str, text: str) -> tuple[dict, str]:
    """The AP agent reads one invoice into a payment instruction's facts. Returns (facts, mode)."""
    if config.EXTRACTION_MODE != "gemini" or not config.GEMINI_API_KEY:
        return invoice_fixture(invoice_id), "fixture"
    prompt = (
        "You are an accounts-payable extraction function, not an adviser. Read the invoice and fill the JSON schema. "
        "Copy values verbatim; for every field give source_doc (the FILE name) and quote (the exact words the value came from). "
        "amount_gbp is the TOTAL DUE as a plain number. sort_code as 'NN-NN-NN', account_number as digits only. due_date ISO (YYYY-MM-DD). "
        "bank_details_changed is true only if the invoice says the supplier's bank details have changed or asks for payment to a new account. "
        "Do not judge whether the invoice is genuine.\n\n"
        f"SCHEMA:\n{json.dumps(_blank_schema(invoice_fixture(invoice_id)), indent=1)}\n\n=== FILE: {invoice_id}.txt ===\n{text}\n\nReturn only the JSON."
    )
    try:
        return _validate_invoice(_generate_json(prompt), invoice_id), "gemini"
    except Exception as exc:  # noqa: BLE001
        fx = invoice_fixture(invoice_id)
        fx["_fallback_reason"] = str(exc)[:300]
        return fx, "gemini-fallback"
