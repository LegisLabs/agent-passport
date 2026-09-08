"""The model at the edges.

Registration is a form the provider fills in by hand (a Prefill button exists for the demo); there is no
document extraction on the register. The model is used in two places only:
extract_invoice()   the AI agent reads an invoice into a payment instruction (verbatim-quote schema,
                    JSON mode, temperature 0; fixture stand-in when offline or on failure).
draft_file_note()   Gemini phrases the structured check results as a short note for the bank's
                    payments risk officer. Draft only; never a decision.
"""
from __future__ import annotations

import json
import re
import time

from . import config

SECTIONS = ("company", "principal", "insurance", "product", "assurance_evidence", "intended_use")


def fixture() -> dict:
    d = json.loads((config.FIXTURES_DIR / "registration_fixture.json").read_text())
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


def blank_fields() -> dict:
    """The registration form, empty. Same shape as the prefill fixture with every value null."""
    fx = fixture()
    return {sec: {k: {"value": None, "source_doc": None, "quote": None} for k in fx[sec]} for sec in SECTIONS}


def draft_file_note(ref: str, fields: dict, checks: list[dict]) -> tuple[str, str]:
    """A plain-English note for the bank's payments risk officer. Returns (text, mode)."""
    flagged = [c for c in checks if c["result"] != "pass"]
    if config.EXTRACTION_MODE != "gemini" or not config.GEMINI_API_KEY:
        return _fixture_note(ref, fields, checks, flagged), "fixture"
    summary = {
        "reference": ref,
        "provider": fields["company"]["legal_name"]["value"],
        "product": f"{fields['product']['product_name']['value']} ({fields['product']['model_provider']['value']} {fields['product']['model_version']['value']})",
        "assurance_evidence": {k: v["value"] for k, v in fields["assurance_evidence"].items()},
        "intended_use": {k: v["value"] for k, v in fields["intended_use"].items()},
        "checks": [{"id": c["id"], "title": c["title"], "result": c["result"], "detail": c["detail"]} for c in checks],
    }
    prompt = (
        "Write a file note for a bank's payments risk officer who is deciding whether to admit a registered AI product to the bank's list, in plain English, British spelling, sentence case, "
        "at most 120 words, no bullet points, no headings. State what was filed on the register, which filing checks passed, what the Independent Assurance Evidence covers, "
        "and name each flagged item and what it means. Do NOT recommend admitting or declining and do NOT use the words "
        "'approve', 'admit', 'decline', 'reject', 'recommend', 'should'. The decision belongs to the officer. Return JSON {\"note\": \"...\"}.\n\n"
        f"{json.dumps(summary, indent=1)}"
    )
    try:
        out = _generate_json(prompt)
        note = str(out.get("note", "")).strip()
        for banned in ("approve", "reject", "recommend", "admit", "decline"):
            if banned in note.lower():
                raise ValueError("verdict vocabulary in draft")
        return note, "gemini"
    except Exception:  # noqa: BLE001
        return _fixture_note(ref, fields, checks, flagged), "gemini-fallback"


def _fixture_note(ref, fields, checks, flagged) -> str:
    passed = sum(1 for c in checks if c["result"] == "pass")
    ae = fields.get("assurance_evidence", {})
    s = (f"Registration {ref} from {fields['company']['legal_name']['value']} files {fields['product']['product_name']['value']} "
         f"({fields['product']['model_provider']['value']}, {fields['product']['model_version']['value']}) for {fields['intended_use']['action_type']['value']}. "
         f"Independent Assurance Evidence at level {ae.get('level', {}).get('value')} from {ae.get('issuer', {}).get('value')} ({ae.get('reference', {}).get('value')}, {ae.get('date', {}).get('value')}) is attached for the same use case. "
         f"{passed} of {len(checks)} filing checks passed.")
    if flagged:
        s += " Flagged: " + "; ".join(f"{c['id']} {c['detail']}" for c in flagged) + "."
    return s


# ── Invoice reading by the AI agent (the visible manipulation moment) ──
INVOICE_FIELDS = ("supplier_name", "invoice_ref", "amount_gbp", "sort_code", "account_number", "due_date", "bank_details_changed")


def invoices() -> dict:
    """{invoice_id: text} for the synthetic invoices the AI agent can read."""
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
    """The AI agent reads one invoice into a payment instruction's facts. Returns (facts, mode)."""
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
