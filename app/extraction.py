"""The model at the edges.

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

SCHEMA_HINT = json.loads((config.FIXTURES_DIR / "extraction_fixture.json").read_text())
SCHEMA_HINT.pop("_comment", None)


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


def _client() :
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


def _validate(out: dict) -> dict:
    """Shape check only. The rules do the real checking; this stops a broken
    extraction reaching them."""
    fx = fixture()
    for section in ("firm", "accountable_person", "compliance", "requested_authority", "agent"):
        if not isinstance(out.get(section), dict):
            raise ValueError(f"missing section {section}")
        for k in fx[section]:
            v = out[section].get(k)
            if not isinstance(v, dict) or "value" not in v:
                out[section][k] = {"value": None, "source_doc": None, "quote": None}
    if not isinstance(out.get("clients"), list):
        raise ValueError("clients must be a list")
    for c in out["clients"]:
        c["utr"] = re.sub(r"\D", "", str(c.get("utr", "")))
        c["authorisation_confirmed"] = c.get("authorisation_confirmed") is True
        c["consent_automated_processing"] = c.get("consent_automated_processing") is True
    # normalise enums the rules compare on
    ra = out["requested_authority"]
    at = str(ra["action_type"]["value"] or "").lower()
    ra["action_type"]["value"] = "submit_and_amend" if "amend" in at else "submit_only"
    task = str(ra["task"]["value"] or "").lower()
    ra["task"]["value"] = "submit_sa100" if "sa100" in task or "self assessment" in task else ra["task"]["value"]
    thr = ra["escalation_threshold_gbp"]["value"]
    if isinstance(thr, str):
        digits = re.sub(r"[^\d.]", "", thr)
        ra["escalation_threshold_gbp"]["value"] = float(digits) if digits else None
    vu = ra["valid_until"]
    vu["value"] = _iso_date(vu["value"])
    ap = out["accountable_person"]
    decl = ap["declaration_accepted"]
    quote = str(decl.get("quote") or "").lower()
    decl["value"] = decl["value"] is True or str(decl["value"]).lower() in ("true", "yes") or "accept responsibility" in quote
    pb = str(ap["professional_body"]["value"] or "")
    for body in ("ICAEW", "ACCA", "CIOT", "ATT", "AAT", "ICAS", "STEP"):
        if body in pb.upper():
            ap["professional_body"]["value"] = body
            break
    return out


def _iso_date(v):
    """'31 January 2027' / '2027-01-31' / '31/01/2027' -> '2027-01-31'; anything else unchanged."""
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


def extract(documents: list[dict]) -> tuple[dict, str]:
    """Returns (facts, mode). mode is gemini | fixture | gemini-fallback."""
    if config.EXTRACTION_MODE != "gemini" or not config.GEMINI_API_KEY:
        return fixture(), "fixture"
    docs_text = "\n\n".join(f"=== FILE: {d['name']} ===\n{d['text']}" for d in documents)
    prompt = (
        "You are an extraction function, not an adviser. Read the documents below and fill the JSON schema. "
        "Rules: copy values verbatim from the documents; for every field give source_doc (the FILE name) and quote "
        "(the exact words the value came from); if a value is absent use null; do not infer, summarise or judge; "
        "do not add fields. Booleans must be true/false. Client rows: one object per client in the register. "
        "authorisation_confirmed is true only if the status says Confirmed. consent_automated_processing is true only "
        "if consent is recorded as Yes. action_type is submit_only or submit_and_amend. task is submit_sa100 when the "
        "task is submitting Self Assessment (SA100) returns. escalation_threshold_gbp is a number. "
        "declaration_accepted is true when the named person states in writing that they accept responsibility for the "
        "agent's actions. valid_until is an ISO date (YYYY-MM-DD).\n\n"
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
        "firm": fields["firm"]["name"]["value"],
        "agent": fields["agent"]["agent_id"]["value"],
        "requested": {k: v["value"] for k, v in fields["requested_authority"].items()},
        "checks": [{"id": c["id"], "title": c["title"], "result": c["result"], "detail": c["detail"]} for c in checks],
    }
    prompt = (
        "Write a file note for a tax-authority case officer in plain English, British spelling, sentence case, "
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
    ra = {k: v["value"] for k, v in fields["requested_authority"].items()}
    passed = sum(1 for c in checks if c["result"] == "pass")
    s = (f"Application {ref} from {fields['firm']['name']['value']} seeks recognition of agent "
         f"{fields['agent']['agent_id']['value']} to {ra['task'].replace('_', ' ')} for tax year {ra['tax_year']}, "
         f"{ra['action_type'].replace('_', ' ')}, with returns above £{float(ra['escalation_threshold_gbp'] or 0):,.0f} held for human review. "
         f"{passed} of {len(checks)} automated checks passed.")
    if flagged:
        s += " Flagged: " + "; ".join(f"{c['id']} {c['detail']}" for c in flagged) + "."
    return s
