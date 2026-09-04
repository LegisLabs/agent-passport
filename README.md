# Agent Passport — v1 skeleton

Regulator-issued, scoped, revocable credential for autonomous AI agents, demonstrated on a UK Self Assessment filing agent. Lexis Labs entry to the C:\>DIR Global 'Agentic Regulator' Hackathon, Know Your Agent problem space.

Live: **https://cdir.legislabs.uk** · API docs: `/api/docs` · Plan: `docs/PLAN.md` · Spec: `docs/Demo Vertical Alignment and Fields for Skeleton.pdf`

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -r deploy/requirements.txt
cp .env.example .env            # add GEMINI_API_KEY, or set EXTRACTION_MODE=fixture
.venv/bin/uvicorn app.main:app --reload --port 8013
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q
```

Self-seeds on first run: the authority's Ed25519 key is generated into `data/keys/`, the SQLite database into `data/`. Nothing else to configure.

## The path

1. **Apply** (`/operator`). Start an application: the firm's evidence pack (five synthetic documents) loads. "Read documents into facts" sends them to Gemini in JSON mode; every extracted value comes back with its source document and a verbatim quote. Correct anything, then generate the agent's key and have the agent sign the authority's challenge (proof of possession). Submit.
2. **Review & issue** (`/regulator`). Ten automated checks (A.1–A.10) run over the reviewed facts and the authority's synthetic registers, each with rule id, source and CURRENT/PROTOTYPE label. Optional model-drafted file note. Officer approves, requests information or rejects, with a required note. Approval mints an Ed25519-signed JWT: agent, operator, granted scope (`authorization_details`), validity, the agent's public key in `cnf`. No client list, no personal data. Lifecycle: suspend, reinstate, revoke, renew, each with a reason.
3. **Act & check** (`/relying`). Seven proposed actions. The simulated agent signs each request; the gateway runs R.1–R.6 in order and answers ALLOW / ESCALATE / DENY with rule, reason code and an authority-signed receipt. Beat 6 signs with a rogue key: a copied passport fails on R.3.
4. **Audit** (`/audit`). Hash chain over every event. Replay re-runs any verification from its stored inputs and must match.

## Rules (rule pack `hmrc-sa-2026.09`, data not code)

| Runtime, in order | Fails to |
|---|---|
| R.1 passport signature genuine | DENY `PASSPORT_SIGNATURE_INVALID` |
| R.2 passport active and unexpired (registry lookup) | DENY `PASSPORT_NOT_ACTIVE` |
| R.3 request signed by the passport's agent key | DENY `AGENT_SIGNATURE_INVALID` |
| R.4 action within scope: task, tax year, action type | DENY `OUT_OF_SCOPE` |
| R.5 client authorised for this firm, by UTR reference | DENY `CLIENT_NOT_AUTHORISED` |
| R.6 tax due above threshold | ESCALATE `HUMAN_APPROVAL_REQUIRED` |
| otherwise | ALLOW `WITHIN_SCOPE` |

Application checks A.1–A.10 are listed on `/about`. `fixtures/oracle.json` holds the deterministic test cases; `tests/test_rules.py` runs all of them offline.

## API (the real deliverable)

```
POST /api/applications                       start (loads the evidence pack)
POST /api/applications/{id}/extract          Gemini → structured facts with provenance
PUT  /api/applications/{id}/fields           operator corrections
POST /api/applications/{id}/agent-key        agent key pair + authority challenge
POST /api/applications/{id}/sign-challenge   agent signs; authority verifies possession
POST /api/applications/{id}/submit           runs A.* checks
POST /api/applications/{id}/decision         {decision: approve|request_info|reject, note}
POST /api/applications/{id}/file-note        model-drafted note (never a decision)
POST /api/passports/{jti}/status             {status: suspended|active|revoked, reason}
GET  /api/passports/{jti}                    full + minimal (relying-party) view
GET  /api/status/{jti}                       real-time status
POST /api/agent/act                          simulated agent signs and presents a request
POST /api/verify                             {passport, request} → decision + receipt
GET  /api/audit · POST /api/audit/{id}/replay · GET /api/receipt/verify?token=
```

## Where the model sits

Gemini (JSON mode, temperature 0) reads documents into a fixed schema and drafts the officer's file note. It never checks, scores or decides. `EXTRACTION_MODE=fixture` replaces both calls with deterministic stand-ins; on API failure the system falls back to the fixture and labels the result `gemini-fallback`.

## Deploy

```bash
bash deploy/publish.sh     # Docker build on the shared Hetzner box, Caddy drop-in, reload
```

## Layout

```
app/          main.py (routes) · rules.py · crypto.py · audit.py · extraction.py · db.py · fixtures.py · templates/ · static/
rulepacks/    hmrc-sa-2026.09.json
fixtures/     documents/ (evidence pack) · registry.json (authority records) · extraction_fixture.json · oracle.json
tests/        pytest, offline
deploy/       Dockerfile · docker-compose.yml · cdir-legislabs.caddy · publish.sh · requirements.txt
docs/         PLAN.md · Bernard's spec · BRIEF_v2 · tax research
context/      hackathon documents (see context/README.md)
archive/      static-prototype (the first frontend-only demo)
```

## Third-party components

FastAPI, Uvicorn, Jinja2, Pydantic (MIT) · cryptography (Apache-2.0/BSD) · PyJWT (MIT) · google-genai (Apache-2.0). No real personal data anywhere; all registers and documents are synthetic.

## Not claimed

That HMRC issues agent passports today; that the passport replaces tax-adviser registration or client authorisation; that a signature proves an agent is safe; that a valid passport compels a relying party; that this is production cryptographic infrastructure.
