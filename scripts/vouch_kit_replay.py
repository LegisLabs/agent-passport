#!/usr/bin/env python3
"""Replay the vouch.finance hackathon kits through the Agent Passport verifier.

Not part of the app runtime. For each kit (kya-licence, agent-mandate) this script:
  1. reads the kit manifest (vendored copy in fixtures/pay/vouch_kits, or --kits-dir for a clone),
  2. builds a synthetic world in Agent Passport terms: every allowlisted merchant becomes a payee
     account on a customer-signed mandate, the kit's per-transaction cap becomes per_payment_limit,
     each actor's quota becomes monthly_limit_per_account, and each actor gets its own agent key,
     signed agent_identity, assurance and mandate (real Ed25519 signatures with this repo's keys),
  3. expands the kit's scenario templates (count × template, amount = unitPrice × qty, no jitter),
  4. runs every payment instruction through pay.rules.verify_action with a running per-account ledger,
     and applies mandate ops (revoke flips the registry status; delegation is out of scope for v1),
  5. scores our decisions against the scripted ground truth (violation vs compliant), the same labels
     run-stream.ts writes to labels.jsonl, and prints precision, recall and the gaps by violation type.

    python scripts/vouch_kit_replay.py                       # offline, vendored manifests, labels from the manifest
    python scripts/vouch_kit_replay.py --labels ../hackathon-kits/artifacts/runs/<runId>/labels.jsonl
    python scripts/vouch_kit_replay.py --json report.json

What the kit checks that a v1 passport mandate does not: merchant category, business hours and
transaction-count velocity. Those scenarios show up as recall gaps, on purpose. Delegation-depth
mandate ops are reported as out of scope.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PAY_DATA_DIR", tempfile.mkdtemp(prefix="ap-kit-replay-"))  # fresh signer keys, no app data touched

from pay import crypto, rules  # noqa: E402

GAP_NOTE = {
    "out_of_category": "merchant category is not a v1 mandate field",
    "out_of_hours": "no time-window constraint in v1",
    "split_payment_structuring": "count velocity is not a v1 mandate field; R.8 catches cumulative amount only",
    "delegation_chain_abuse": "no sub-agent delegation in v1 (mandate op)",
    "revoked_mandate_reuse": "mandate op: R.2 refuses a revoked assurance",
}


def load_manifest(kits_dir: Path, kit: str) -> dict:
    for p in (kits_dir / f"{kit}.json", kits_dir / "kits" / f"{kit}.json"):
        if p.exists():
            return json.loads(p.read_text())
    raise SystemExit(f"manifest for {kit} not found under {kits_dir}")


def allowlist_and_cap(m: dict) -> tuple[list[str], float | None]:
    """From the kit's pre-redemption rule hook: merchant.id in [...] and cart.total lte N."""
    refs, cap = [], None
    for h in m.get("hooks", []):
        if h.get("type") != "rule":
            continue
        for cond in (h.get("ruleConfig") or {}).get("all", []):
            if cond.get("field") == "merchant.id" and cond.get("op") == "in":
                refs = [x.get("$merchantRef") for x in cond.get("value", []) if isinstance(x, dict)]
            if cond.get("field") == "cart.total" and cond.get("op") in ("lte", "lt"):
                cap = float(cond["value"])
    return refs, cap


def account_for(ref: str) -> str:
    n = int("".join(ch for ch in ref if ch.isdigit()) or "0")
    return f"90-00-{n:02d} {10000000 + n:08d}"


def build_world(m: dict, human_confirm_above: float) -> dict:
    refs, cap = allowlist_and_cap(m)
    merchants = {x["ref"]: {**x, "account_ref": account_for(x["ref"])} for x in m["merchants"]}
    allow = [{"supplier_id": r, "name": merchants[r]["name"], "account_ref": merchants[r]["account_ref"]} for r in refs if r in merchants]
    actors = {}
    for a in m["actors"]:
        quota = float(((a.get("mandate") or {}).get("policy") or {}).get("quota", {}).get("totalCostUsd") or a.get("budget") or 0)
        priv, pub = crypto.generate_keypair()
        jwk = crypto.public_jwk(pub)
        ident_payload = {"iss": "kit-operator", "typ": "agent_identity", "sub": a["ref"], "iat": crypto.now_ts(),
                         "agent": {"name": a["label"], "agent_id": f"{m['kitId']}:{a['ref']}", "software": "kit", "software_version": "0"}, "cnf": {"jwk": jwk}}
        ident = crypto.sign_jwt("payrail", ident_payload, typ="agent-identity+jwt")
        pid = f"KIT-{m['kitId']}-{a['ref']}"
        assurance = crypto.sign_jwt("authority", {"iss": "payments-authority-demo", "typ": "assurance", "jti": pid, "iat": crypto.now_ts(), "valid_until": "2099-12-31",
                                                  "provider": {"legal_name": "Kit operator", "licence_ref": "KIT"}, "agent_id": a["ref"],
                                                  "condition": {"human_confirm_above": {"amount": human_confirm_above, "currency": m["program"]["currency"]}},
                                                  "binds": {"agent_identity_sha256": crypto.sha256_hex(ident)}}, typ="assurance+jwt")
        mandate = crypto.sign_jwt("northgate", {"iss": "kit-customer", "typ": "mandate", "passport_id": pid, "valid_until": "2099-12-31", "iat": crypto.now_ts(),
                                                "authorization_details": [{"type": "payment_initiation", "actions": ["pay_invoice"], "currency": m["program"]["currency"],
                                                                           "supplier_allowlist": allow,
                                                                           "per_payment_limit": {"amount": cap if cap is not None else quota, "currency": m["program"]["currency"]},
                                                                           "monthly_limit_per_account": {"amount": quota, "currency": m["program"]["currency"], "window": "P30D"}}]}, typ="mandate+jwt")
        actors[a["ref"]] = {"ref": a["ref"], "quota": quota, "private_pem": priv, "status": "active", "passport_id": pid,
                            "envelope": {"passport_id": pid, "assurance": assurance, "agent_identity": ident, "mandate": mandate}}
    return {"merchants": merchants, "allowlist": refs, "cap": cap, "actors": actors}


def expand(m: dict) -> list[dict]:
    out = []
    for t in m["violationScript"]:
        for k in range(int(t.get("count", 1))):
            out.append({**t, "k": k + 1, "txnRef": f"{m['kitId']}:{t['id']}:{k + 1}"})
    return out


def run_kit(m: dict, human_confirm_above: float, labels: dict | None) -> dict:
    world = build_world(m, human_confirm_above)
    ledger: dict[tuple[str, str], float] = defaultdict(float)
    rows, scored = [], []
    for inst in expand(m):
        actor = world["actors"][inst["actorRef"]]
        vt = inst.get("violationType")
        truth = "violation" if vt else "compliant"
        if labels is not None:
            recs = labels.get(inst["id"])
            if recs:
                truth = recs[0]["label"]
        if inst.get("kind") == "mandate_op":
            op = inst["mandateOp"]["op"]
            if op == "revoke":
                actor["status"] = "revoked"
                dec, rule, code = "REVOKED", "lifecycle", "registry status flipped; next instruction fails R.2"
            elif op == "get_ledger":
                dec, rule, code = "OK", "—", "re-verification read (no decision)"
            elif op in ("issue_child", "delegate_grandchild"):
                if actor["status"] != "active":
                    dec, rule, code = "DENY", "R.2", "ASSURANCE_NOT_ACTIVE"
                else:
                    dec, rule, code = "OUT_OF_SCOPE_V1", "—", "no sub-agent delegation in v1"
            else:
                dec, rule, code = "OUT_OF_SCOPE_V1", "—", f"unknown op {op}"
            rows.append({"scenario": inst["id"], "k": inst["k"], "kind": "mandate_op", "actor": inst["actorRef"], "merchant": "", "amount": None, "truth": truth, "violation_type": vt,
                         "decision": dec, "rule": rule, "code": code})
            if dec in ("DENY", "OUT_OF_SCOPE_V1") and vt:
                scored.append({"truth": truth, "ours": "violation" if dec == "DENY" else "unscored", "vt": vt})
            continue
        merchant = world["merchants"][inst["merchantRef"]]
        item = inst["item"]
        amount = float(item["unitPrice"]) * float(item.get("qty", 1))
        req = {"passport_id": actor["passport_id"], "action_type": "pay_invoice", "payee_account_ref": merchant["account_ref"], "supplier_name": merchant["name"],
               "amount": amount, "currency": m["program"]["currency"], "invoice_ref": inst["txnRef"], "nonce": inst["txnRef"]}
        req["agent_signature"] = crypto.sign_bytes(actor["private_pem"], rules.request_signing_input(req))
        key = (actor["ref"], merchant["ref"])
        res = rules.verify_action(actor["envelope"], actor["status"], req, ledger_total=ledger[key])
        if res["decision"] == "ALLOW":
            ledger[key] += amount
        rows.append({"scenario": inst["id"], "k": inst["k"], "kind": "payment", "actor": inst["actorRef"], "merchant": merchant["name"], "amount": amount, "truth": truth,
                     "violation_type": vt, "decision": res["decision"], "rule": res["rule"], "code": res["code"]})
        scored.append({"truth": truth, "ours": "violation" if res["decision"] in ("DENY", "ESCALATE") else "compliant", "vt": vt})
    tp = sum(1 for s in scored if s["truth"] == "violation" and s["ours"] == "violation")
    fp = sum(1 for s in scored if s["truth"] == "compliant" and s["ours"] == "violation")
    fn = sum(1 for s in scored if s["truth"] == "violation" and s["ours"] != "violation")
    tn = sum(1 for s in scored if s["truth"] == "compliant" and s["ours"] == "compliant")
    gaps = defaultdict(lambda: [0, 0])
    for s in scored:
        if s["truth"] == "violation":
            gaps[s["vt"]][1] += 1
            if s["ours"] == "violation":
                gaps[s["vt"]][0] += 1
    return {"kit": m["kitId"], "title": m["title"], "world": {"allowlist": world["allowlist"], "per_payment_cap": world["cap"], "actors": {r: a["quota"] for r, a in world["actors"].items()}},
            "rows": rows, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": (tp / (tp + fp)) if tp + fp else None, "recall": (tp / (tp + fn)) if tp + fn else None,
            "gaps": {vt: {"caught": c, "of": n, "note": GAP_NOTE.get(vt, "")} for vt, (c, n) in gaps.items()}}


def read_labels(path: Path) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for line in path.read_text().splitlines():
        if line.strip():
            rec = json.loads(line)
            out[rec["kitScenarioId"]].append(rec)
    return out


def fmt(x):
    return "—" if x is None else f"{x:.0%}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kits-dir", default=str(ROOT / "fixtures" / "pay" / "vouch_kits"))
    ap.add_argument("--kits", default="kya-licence,agent-mandate")
    ap.add_argument("--labels", default=None, help="labels.jsonl from their run-stream.ts (matched by kitScenarioId)")
    ap.add_argument("--human-confirm-above", type=float, default=5000)
    ap.add_argument("--json", default=None, help="write the full report here")
    ap.add_argument("--verbose", action="store_true", help="print every instance, not one line per scenario")
    args = ap.parse_args()
    labels = read_labels(Path(args.labels)) if args.labels else None
    report = []
    for kit in args.kits.split(","):
        m = load_manifest(Path(args.kits_dir), kit.strip())
        r = run_kit(m, args.human_confirm_above, labels)
        report.append(r)
        print(f"\n== {r['kit']} · {r['title']}")
        print(f"   world: allowlist {', '.join(r['world']['allowlist'])} · per-payment cap {r['world']['per_payment_cap']} · actor quotas {r['world']['actors']}")
        print(f"   {'scenario':32} {'kind':10} {'actor':18} {'n':>3} {'truth':10} {'ours (decisions)':34} rule · code")
        by = defaultdict(list)
        for row in r["rows"]:
            by[row["scenario"]].append(row)
        for sid, rs in by.items():
            if args.verbose:
                for row in rs:
                    print(f"   {row['scenario']:32} {row['kind']:10} {row['actor']:18} {row['k']:>3} {row['truth']:10} {row['decision']:34} {row['rule']} · {row['code']}")
            else:
                decs = defaultdict(int)
                for row in rs:
                    decs[row["decision"]] += 1
                summary = ", ".join(f"{d}×{n}" for d, n in decs.items())
                last = rs[-1]
                print(f"   {sid:32} {last['kind']:10} {last['actor']:18} {len(rs):>3} {last['truth']:10} {summary:34} {last['rule']} · {last['code']}")
        print(f"   score: tp {r['tp']} fp {r['fp']} fn {r['fn']} tn {r['tn']} · precision {fmt(r['precision'])} · recall {fmt(r['recall'])}")
        for vt, g in r["gaps"].items():
            print(f"   {vt:28} caught {g['caught']}/{g['of']}  {g['note']}")
    src = f"labels from {args.labels}" if args.labels else "labels from the manifests (the same ground truth run-stream.ts writes)"
    print(f"\nScored against {src}. Every payment instruction was verified by pay.rules.verify_action with real Ed25519 envelopes.")
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=1))
        print(f"report written to {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
