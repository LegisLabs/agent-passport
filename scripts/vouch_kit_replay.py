#!/usr/bin/env python3
"""Replay the vouch.finance hackathon kits (kya-licence, agent-mandate) against Agent Passport semantics.

Not part of the app runtime. It answers one question for the judges: if the scripted scenarios in
the sponsor's kits were presented to our bank-side verifier, which rule would fire?

Two inputs, both optional:
  --kits-dir   a clone of finternet-ecosystem/hackathon-kits (default: the vendored copies in fixtures/pay/vouch_kits)
  --labels     a labels.jsonl written by their run-stream.ts (artifacts/runs/<runId>/labels.jsonl); when given,
               our expected decision per scenario is scored against their ground-truth label.

    python scripts/vouch_kit_replay.py                       # offline, vendored manifests
    python scripts/vouch_kit_replay.py --labels ../hackathon-kits/artifacts/runs/my-run/labels.jsonl

Mapping (kit violationType -> Agent Passport rule):
  unapproved_counterparty     R.6 PAYEE_NOT_ON_MANDATE      payee not on the customer-signed allowlist
  over_limit_single_tx        R.7 PER_PAYMENT_LIMIT_EXCEEDED
  split_payment_structuring   R.8 MONTHLY_LIMIT_EXCEEDED    cumulative per-account total at the bank
  delegation_overspend        R.7 (child cap)               a narrower mandate's per-payment limit
  out_of_category             R.6 OUT_OF_SCOPE              action / category outside the mandate
  out_of_hours                out of scope v1               no time-window constraint in the v1 mandate
  delegation_chain_abuse      out of scope v1               no sub-agent delegation in v1
  revoked_mandate_reuse       R.2 ASSURANCE_NOT_ACTIVE      revoked authority reused
  (compliant)                 ALLOW WITHIN_MANDATE, or ESCALATE R.9 above the supervisor condition
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

MAP = {
    None: ("ALLOW", "—", "WITHIN_MANDATE"),
    "unapproved_counterparty": ("DENY", "R.6", "PAYEE_NOT_ON_MANDATE"),
    "over_limit_single_tx": ("DENY", "R.7", "PER_PAYMENT_LIMIT_EXCEEDED"),
    "split_payment_structuring": ("DENY", "R.8", "MONTHLY_LIMIT_EXCEEDED"),
    "delegation_overspend": ("DENY", "R.7", "PER_PAYMENT_LIMIT_EXCEEDED"),
    "out_of_category": ("DENY", "R.6", "OUT_OF_SCOPE"),
    "out_of_hours": ("OUT_OF_SCOPE_V1", "—", "no time-window constraint in v1"),
    "delegation_chain_abuse": ("OUT_OF_SCOPE_V1", "—", "no sub-agent delegation in v1"),
    "revoked_mandate_reuse": ("DENY", "R.2", "ASSURANCE_NOT_ACTIVE"),
}


def load_manifest(kits_dir: Path, kit: str) -> dict:
    p = kits_dir / f"{kit}.json"
    if not p.exists():
        p = kits_dir / "kits" / f"{kit}.json"
    return json.loads(p.read_text())


def expected_for(scn: dict, policy: dict) -> tuple[str, str, str]:
    vt = scn.get("violationType")
    if vt in MAP and vt is not None:
        return MAP[vt]
    # compliant: apply the supervisor condition to the scripted amount
    item = scn.get("item") or {}
    amount = float(item.get("unitPrice", 0)) * float(item.get("qty", 1))
    thr = policy.get("human_confirm_above", 5000)
    if amount > thr:
        return ("ESCALATE", "R.9", "HUMAN_CONFIRMATION_REQUIRED")
    return MAP[None]


def read_labels(path: Path) -> dict[str, dict]:
    out = {}
    for line in path.read_text().splitlines():
        if line.strip():
            rec = json.loads(line)
            out.setdefault(rec["kitScenarioId"], []).append(rec)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kits-dir", default=str(ROOT / "fixtures" / "pay" / "vouch_kits"))
    ap.add_argument("--kits", default="kya-licence,agent-mandate")
    ap.add_argument("--labels", default=None, help="labels.jsonl from run-stream.ts")
    ap.add_argument("--human-confirm-above", type=float, default=5000)
    args = ap.parse_args()
    labels = read_labels(Path(args.labels)) if args.labels else {}
    policy = {"human_confirm_above": args.human_confirm_above}
    total_scored = agree = 0
    for kit in args.kits.split(","):
        m = load_manifest(Path(args.kits_dir), kit.strip())
        print(f"\n== {m['kitId']} · {m['title']} ==")
        print(f"{'scenario':32} {'kind':11} {'violation':27} {'count':>5}  {'our decision':14} {'rule':5} code / note")
        for scn in m["violationScript"]:
            dec, rule, code = expected_for(scn, policy)
            print(f"{scn['id']:32} {scn.get('kind', 'payment'):11} {str(scn.get('violationType') or '—'):27} {scn.get('count', 1):>5}  {dec:14} {rule:5} {code}")
            if labels and scn["id"] in labels:
                for rec in labels[scn["id"]]:
                    total_scored += 1
                    ours_violation = dec in ("DENY", "ESCALATE")
                    theirs_violation = rec["label"] == "violation"
                    if dec == "OUT_OF_SCOPE_V1":
                        continue
                    agree += int(ours_violation == theirs_violation)
    if labels:
        print(f"\nScored against labels.jsonl: {agree} of {total_scored} scripted transactions classified the same way (violation vs compliant); out-of-scope v1 cases excluded from agreement.")
    else:
        print("\nNo labels.jsonl given: mapping only. Run their run-stream.ts, then pass --labels to score.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
