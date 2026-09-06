# Agent Passport (KY-A): V0 Field Schema & Technical Foundation — UK Tax-Filing Research Base

## TL;DR
- **The UK tax-agent trust chain already has three anchorable layers we build on** — AML supervision (professional body or HMRC), HMRC tax-adviser registration + Agent Services Account (ASA) with an Agent Reference Number, and per-client authorisation (form 64-8 / MTD digital handshake) — plus a mandatory API telemetry regime (fraud-prevention "Gov-Client" headers). **The Agent Passport is a fourth layer that recognises a *specific software agent* for *specific activities under specific conditions*; it must NOT be pitched as replacing any of these.**
- **The passport artifact should be assembled entirely from recognised standards**: a signed JWT (RFC 7519) using Ed25519 (alg `EdDSA`, RFC 8037), scope expressed as RFC 9396 `authorization_details`, holder binding via a `cnf` claim (RFC 7800) / DPoP (RFC 9449), and revocation via a W3C Bitstring Status List v1.0 or registry lookup — with a W3C Verifiable Credentials 2.0 wrapper as the "speaks-to-regulators" presentation format.
- **The single most important architectural finding**: cumulative/velocity limits CANNOT be enforced inside an immutable signed token — the token carries the LIMIT, but a stateful counter at the authority's gateway must track the running TOTAL. The verification flow must run in strict order: **signature/expiry → status → holder-binding → authorisation → scope → limits → escalation**, returning ALLOW / ESCALATE / DENY with a rule citation.

## Key Findings

1. **The trust chain is real, layered, and currently being hardened — giving us fresh statutory anchors.** As of September 2026, HMRC is mid-rollout of **Modernising and Mandating Tax Adviser Registration (MMTAR)**, a legal requirement in **Chapter 1 of Part 7 of the Finance (No. 2) Bill 2025-26** for all paid tax advisers who interact with HMRC on behalf of clients to register with HMRC and meet "minimum standards" before doing so. Registration **opened on 18 May 2026 in phases running to 31 March 2027** (the first window closed 18 August 2026; a second window ran to 18 November 2026; financial-services-linked firms deferred to end-March 2027), backed by a **£36 million** HMRC investment to replace fragmented, often paper-based registration with a single digital route via the ASA.
2. **HMRC already collects agent telemetry.** The mandatory fraud-prevention headers (`Gov-Client-*`, `Gov-Vendor-*`) on every VAT (MTD) and Income Tax Self Assessment (MTD) API call are, in effect, an existing "software-acting-on-behalf" telemetry precedent — the passport formalises and extends this idea rather than inventing it. HMRC states submitting this header data is required *by law* for these APIs.
3. **RFC 9396 (Rich Authorization Requests) is the single best standards hook** for expressing "what this agent may do" as structured, typed JSON rather than flat scope strings. It emerged from open banking precisely to express transaction-level detail — RFC 9396's own Figure 1 gives the verbatim example `{"type":"payment_initiation","instructedAmount":{"currency":"EUR","amount":"123.50"},"creditorName":"Merchant A"...}` — which maps directly onto per-filing and cumulative monetary limits for a tax agent.
4. **Ed25519 (`EdDSA`) is the right prototype signature; ES256 (P-256) the right fallback** for government PKI recognition. Both are approved under NIST FIPS 186-5 (effective 3 February 2023).
5. **The competitive field is self-declared and blockchain-anchored, not authority-issued.** AstraSync, Vouched (MCP-I) and HUMAN Security build KY-A registries, but none is an authority-issued, revocable, scope-bounded recognition of an agent by the regulator itself. **That is our differentiator.**

## Details

### (a) Plain-English map of the UK tax-agent trust chain today

**Who does what:**
- **Taxpayer (client):** Remains legally responsible for their own return, even when an agent files. Under the MTD digital handshake, the client authenticates directly with HMRC via their own Government Gateway credentials, must never share them with the agent, and the authorisation link is valid for a limited time (21 days for the MTD Income Tax handshake).
- **Accounting firm (agent):** Registers as a tax agent, holds the client relationship, files returns. Must be supervised for AML and (under MMTAR) registered with HMRC.
- **Professional body (ICAEW, ACCA, CIOT, ATT, AAT, ICAS, STEP):** Supervises members for AML and enforces **PCRT (Professional Conduct in Relation to Taxation)**, the code co-authored by all seven bodies. HMRC's updated **Standard for Agents (published 17 May 2024)** explicitly endorses PCRT — professional bodies described it as recognising PCRT as "the gold standard" and confirmed the Standard does not place further requirements on agents who already meet their body's code of ethics.
- **HMRC:** Runs the ASA, issues agent codes/references, checks AML supervision + tax compliance + fitness of "relevant individuals," maintains the recognised-software list, and collects mandatory API telemetry.

**Artifacts that already exist:**
| Artifact | What it is | What it proves |
|---|---|---|
| AML supervision registration | Supervision by a professional body or (if none) HMRC's Economic Crime Unit | The firm is subject to money-laundering oversight |
| ASA + Agent Reference Number (ARN) | The firm's single digital account with HMRC; older Government Gateway agent accounts held agent codes per tax | The firm is a recognised HMRC agent |
| MMTAR registration | New mandatory tax-adviser registration (phased May 2026 → March 2027) | The firm meets HMRC minimum standards and is fit to interact |
| Form 64-8 / MTD digital handshake | Per-client authorisation; the handshake replaces paper 64-8 for MTD and is a separate service per tax | This firm may act for THIS client, for THESE taxes |
| OAuth 2.0 app credentials (`client_id` / `client_secret`) | Identifies the *software application* on the Developer Hub | This software is a registered application |
| Fraud-prevention headers (`Gov-Client-*`, `Gov-Vendor-*`) | Mandatory per-call device/network/software telemetry | Where and how a submission originated |
| "Recognised by HMRC" software listing | Technical recognition that a product can meet MTD requirements | The software can technically file — explicitly NOT an endorsement or quality rating |

Supporting technical facts for these anchors:
- **OAuth flows.** The Developer Hub uses OAuth 2.0 **Authorization Code Grant** for user-restricted endpoints (authorisation lasts up to 18 months before the refresh token expires; PKCE supported) and **Client Credentials Grant** for application-restricted endpoints (access token valid 4 hours). `client_id` is issued when an app is added; `client_secret` values are generated by the developer (up to 5 at a time).
- **MTD status.** MTD for VAT has been live since 2019 (all VAT-registered businesses from April 2022). MTD for Income Tax Self Assessment (ITSA) became mandatory from **6 April 2026 for qualifying income over £50,000**, dropping to **£30,000 from April 2027** and **£20,000 from April 2028**. Quarterly update deadlines are 7 August, 7 November, 7 February and 7 May; a Final Declaration replaces the old Self Assessment return.
- **Submission identifiers.** ITSA MTD submissions are keyed on a **National Insurance number (NINO), a Business ID, tax year and business type**; the final declaration is triggered via the *Trigger a Self Assessment Tax Calculation* endpoint (Final Declaration = true) and quotes a **calculation ID**. VAT submissions carry a **VRN**; agent context carries the **ARN**. HMRC's guidance explicitly contemplates "automated quarterly updates" but stresses the customer "remains legally responsible" and expects "appropriate safeguards to be built in" — directly relevant to our escalation design.

**The gaps an autonomous agent creates:**
- Every existing artifact identifies a *firm*, a *human client relationship*, or a *software product category* — none identifies and bounds a *specific autonomous agent instance* making unsupervised decisions.
- OAuth scopes and the "recognised software" listing say what the software *can technically do*, not what *this deployed agent is permitted to do* under conditions, limits and escalation rules.
- Client authorisation (64-8) proves the firm may act for the client; it says nothing about whether an *autonomous* process, rather than a named human, may execute a given action.
- Nothing is *instantly revocable at the action level* — authorisations can be withdrawn, but there is no real-time ALLOW/DENY gate keyed to a specific agent's permitted behaviour.

### (b) Recommended V0 Agent Passport field schema

**Group (i) — Identity & accountability**
| Field | Example value | Real-world anchor | V0 vs later |
|---|---|---|---|
| firm_legal_name | "Smith & Co Accountants LLP" | ASA business details | V0 |
| firm_arn | "ARN1234567" | HMRC Agent Reference Number | V0 |
| asa_ref / mmtar_ref | "XAML00001234567" | ASA / MMTAR registration | V0 |
| aml_supervisor | "ICAEW" | AML supervision precondition for ASA | V0 |
| aml_reg_number | "AML123456" | AML supervision registration number | V0 |
| accountable_person | "Jane Smith, Partner" | FCA SM&CR Senior Management Function + Statement of Responsibilities (Duty of Responsibility under FSMA); MMTAR "relevant individuals" | V0 |
| agent_id | "did:web:smithco.example/agents/filer-01" or a UUID | Per-instance identifier (novel to this system) | V0 |
| model_provider | "Anthropic" | AI provenance (model/system card; NIST AI RMF MAP function) | V0 |
| model_version | "claude-x.y" | EU AI Act provider-vs-deployer documentation (Art. 53/Annex IV technical docs) | Later rung |
| operator | "Smith & Co (deployer)" | EU AI Act deployer duty | V0 |
| sanctions_screen | "UK Sanctions List: clear, 2026-09-01" | UK Sanctions List (the OFSI Consolidated List closed 28 Jan 2026; UK Sanctions List is now the sole source) | Later rung |

**Group (ii) — Authority & scope**
| Field | Example value | Real-world anchor | V0 vs later |
|---|---|---|---|
| permitted_actions | ["submit-quarterly-update", "trigger-final-declaration"] mapped to MTD ITSA endpoints | HMRC Income Tax (MTD) API operations | V0 |
| per_filing_limit | {"amount": 50000, "currency": "GBP"} | RFC 9396 `authorization_details` | V0 |
| cumulative_limit | {"amount": 250000, "window": "P1D"} | RFC 9396 + payment velocity controls | V0 |
| escalation_threshold | {"amount": 20000, "action": "ESCALATE"} | Human-in-loop; SM&CR escalation; HMRC "appropriate safeguards" expectation | V0 |
| client_coverage_ref | "64-8:client-UTR-hash" or handshake ref | Form 64-8 / MTD digital handshake (reference only, NOT replacement) | V0 |
| tax_regimes | ["MTD-ITSA", "MTD-VAT"] | MTD service scope | V0 |
| valid_from / valid_until | ISO 8601 datetimes | VC 2.0 `validFrom`/`validUntil`; JWT `nbf`/`exp` | V0 |
| delegation_allowed | false | Macaroon caveat / no-sub-delegation | Later rung |

**Group (iii) — Technical / credential**
| Field | Example value | Real-world anchor | V0 vs later |
|---|---|---|---|
| issuer (iss) | "did:web:hmrc-sandbox.example" | JWT RFC 7519 / VC 2.0 `issuer` | V0 |
| signature_alg | "EdDSA" (Ed25519) | RFC 8037 (JOSE); NIST FIPS 186-5 | V0 |
| cnf (key binding) | {"jkt": "<JWK SHA-256 thumbprint>"} | RFC 7800 `cnf` / DPoP RFC 9449 | V0 |
| status_pointer | Bitstring Status List entry URL | W3C Bitstring Status List v1.0 | V0 |
| rule_pack_version | "hmrc-rules-2026.09" | Versioned policy (RAR `type` namespace) | V0 |
| audit_anchor | hash of decision log | Tamper-evident audit (hash chain — explicitly NOT blockchain) | Later rung |
| jti | unique token id | RFC 7519 | V0 |

### (c) Verification decision flow

Ordered checks the relying service (authority gateway) runs on each proposed action:
1. **Signature & expiry** — verify the authority's Ed25519 signature; check `nbf`/`exp`. Data lives *in the token*. Fail → DENY ("invalid or expired passport").
2. **Status/revocation** — look up the Bitstring Status List / registry. Data lives *in a registry* (must be fresh; cannot be in the token). Revoked → DENY.
3. **Holder binding** — verify a DPoP proof signed by the agent's own key matches the `cnf` thumbprint. Data: token `cnf` + live proof. Mismatch → DENY ("possession not proven — possible stolen passport").
4. **Authorisation** — confirm `client_coverage_ref` corresponds to a live 64-8/handshake for this client + tax. Data: *registry*. Missing → DENY.
5. **Scope** — is the proposed action in `permitted_actions` and mapped to a real MTD endpoint? Data: *token*. Out of scope → DENY.
6. **Limits** — per-filing check is stateless (compare against token limit). Cumulative check is **stateful**: increment a counter at the gateway keyed by `agent_id` and window. Data: LIMIT in *token*, TOTAL in *gateway state store*. Over limit → DENY or ESCALATE.
7. **Escalation** — if action value ≥ `escalation_threshold`, return ESCALATE (route to a named human) rather than ALLOW.

**Statefulness analysis (critical, and a likely judge question):** A signed JWT is self-contained and immutable — the verifier checks signature + claims and, by design, holds no running state. The token can carry the LIMIT but cannot carry the running TOTAL, because updating "spent-so-far" would require re-signing on every transaction or mutating a signed object (breaking the signature). This is the same property that makes JWTs impossible to revoke statelessly: "stateless" means "no server-side control," so both revocation and cumulative limits require adding state back at the enforcement point. Therefore cumulative/velocity ceilings require a **stateful counter (e.g., Redis, or SQLite/in-memory for the prototype) at the gateway, incremented atomically per authorised action**. Use a **sliding-window counter** rather than a fixed window to avoid the boundary-burst exploit (spending the full limit at the end of one window and again at the start of the next → up to 2× the limit across the boundary). This mirrors how real payment systems implement velocity checks — e.g., Stripe uses per-identity token-bucket limiters backed by Redis, and Stripe Radar computes payment velocity via bucketed rolling-interval counters to catch card-testing — exactly the "LIMIT in policy, TOTAL in a stateful store at the resource server" model our gateway needs.

### (d) Standards crosswalk

| Passport part | Standard | Note |
|---|---|---|
| Container & claims | JWT (RFC 7519) | Simplest for a 5-day prototype |
| Presentation / "regulator language" | W3C Verifiable Credentials Data Model 2.0 (W3C Recommendation, 15 May 2025, Manu Sporny et al.) | `issuer`, `credentialSubject`, `validFrom`/`validUntil`, `credentialStatus`; published alongside Bitstring Status List v1.0 and "Securing Verifiable Credentials using JOSE and COSE" |
| Signature | EdDSA/Ed25519 (RFC 8037); ES256/P-256 (RFC 7518) fallback | Both NIST FIPS 186-5 approved; Ed25519 = 32-byte keys, 64-byte deterministic signatures |
| Scope / authority | RFC 9396 `authorization_details` (IETF Standards Track, May 2023) | Typed JSON: "what may be done, to which resource, up to what limit"; also surfaced via token introspection (RFC 7662) |
| Holder binding | `cnf` (RFC 7800) + DPoP (RFC 9449) | Binds credential to the agent's own keypair — a stolen/copied passport can't be replayed without the private key |
| Revocation/status | W3C Bitstring Status List v1.0; OAuth token introspection (RFC 7662) as alternate pattern | Registry, not token; flipping one bit revokes instantly |
| Cumulative limits | Stateful counter (token bucket / sliding-window) | Cannot be enforced statelessly |

Pitch line: **"Assembled from recognised standards — IETF RFCs and W3C Recommendations — not invented crypto."**

**Signature-algorithm recommendation (detail).** Use **Ed25519 (`alg: EdDSA`, registered by RFC 8037)** for the prototype: deterministic signatures (no per-signature random nonce, eliminating the ECDSA bad-RNG/nonce-reuse footgun), no curve/padding/hash configuration choices, smallest keys (32 bytes) and signatures (64 bytes) for compact tokens, and fastest sign/verify — and it is NIST-approved under FIPS 186-5 (effective 3 February 2023). Keep the design swappable to **ES256/P-256 (RFC 7518)**, which government and enterprise PKI most universally recognise today (the safe FIPS/legacy fallback; UK Open Banking is a precedent that started on PS256 then allowed ES256). In Python, PyJWT, the `cryptography` library and joserfc/Authlib all support EdDSA — note that PyJWT (and joserfc) require the optional `cryptography` package installed for *any* asymmetric algorithm, but EdDSA needs no extra steps beyond that vs ES256/RS256.

### (e) Gap table — what HMRC already knows vs what the passport adds

| Existing artifact | What it proves | What it CANNOT answer about an autonomous agent |
|---|---|---|
| ASA + ARN | Firm is a recognised agent | Whether a specific autonomous agent instance is permitted to act |
| AML supervision | Firm is under AML oversight | Whether this agent's actions are bounded/escalated |
| MMTAR registration | Firm meets minimum standards; accountable individuals named | Which software agent, doing what, under what limits |
| 64-8 / digital handshake | Firm may act for this client/tax | Whether an autonomous process (not a human) may execute the action |
| OAuth app credentials | Software is a registered application | What THIS deployment is permitted to do, with what caps |
| Fraud-prevention headers | Where/how a submission originated | Whether the action was pre-authorised against a policy in real time |
| "Recognised software" listing | Product can technically file | That a live agent is behaving within permitted scope right now |

### Competitive / adjacent landscape (brief)
- **AstraSync** is explicitly **blockchain-based**: each agent gets an ASTRA ID, a cryptographic keypair and a verified owner "minted once and anchored to a public blockchain," it "wraps ERC-8004" (agents as ERC-721 tokens), and it layers a KYD/KYO/KYA chain with continuously-updated "trust scores." **Vouched MCP-I** extends the Model Context Protocol with a W3C DID/Verifiable-Credential identity layer plus an Agent Reputation Directory. **HUMAN Security AgenticTrust** focuses on continuous behavioural analysis and dynamic trust scoring rather than one-time verification. All are **self-declared / developer- or vendor-verified**, not regulator-issued. None offers an authority that *issues, scopes, and instantly revokes* an agent's permission — the Agent Passport's core claim.
- **Government AI-agent precedents (UK):** DSIT/GDS published the **AI Playbook for the UK Government (10 Feb 2025)**; GDS's incubator (i.AI) has built 22 AI prototypes (11 at Alpha/Beta); the **AI Exemplars Programme** (Aug 2025) spans tax, NHS, justice and education; and GDS has procured a **GOV.UK Agentic AI "Companion"** and signalled that GOV.UK Chat will "evolve from providing answers to performing actions." These show the direction of travel but are user-facing/advisory, not a KY-A recognition regime — reinforcing the gap the passport fills.

### (f) Recommendations for V0 scope

**Demo-critical (must build):**
- Signed **Ed25519 JWT** passport carrying the Group (i)/(ii)/(iii) V0 fields.
- Scope expressed as **RFC 9396 `authorization_details`** mapped to at least one real MTD endpoint (e.g., `submit-quarterly-update`).
- The **gateway verifier** running the ordered flow and returning **ALLOW / ESCALATE / DENY with a rule citation**.
- **Stateful cumulative-limit counter** demonstrating the ESCALATE and DENY paths.
- **Instant revocation demo** (flip a status-list bit → next action DENY).
- **Holder binding** (`cnf` + a DPoP-style proof) to show a copied passport is useless without the agent's key.

**Deferrable:** VC 2.0 JSON-LD wrapper, sanctions auto-screening, delegation caveats, deeper model-version provenance, tamper-evident audit anchoring.

## Recommendations
- **Stage 1 (build now):** Ed25519 signed JWT + RFC 9396 scope + gateway verifier with the ordered checks + stateful cumulative counter + status-list revocation. This is the minimum that demonstrates the whole trust story end-to-end.
- **Stage 2 (if time):** Add the DPoP holder-binding proof and a VC 2.0 presentation view for the "standards language" pitch.
- **Stage 3 (roadmap slide only):** Sanctions screening against the UK Sanctions List, delegation caveats, richer AI provenance, tamper-evident audit.
- **Benchmarks that change the plan:** If judges prioritise standards-recognition over a working demo, promote the VC 2.0 wrapper into Stage 1. If they prioritise the autonomy/safety story, promote DPoP binding into Stage 1. If any regulator-PKI constraint surfaces, switch `alg` from `EdDSA` to `ES256` (design already anticipates this).

**Risks / credibility traps:**
1. **Implying we replace 64-8 or client authorisation** — always state the passport is a *third/fourth layer* that *references*, not *replaces*, existing authorisation. This is the single most likely way to lose regulator credibility.
2. **Overclaiming HMRC integration** — this is a sandbox prototype; do not imply HMRC issues or endorses it. Use "HMRC-like regulator" throughout.
3. **Using "blockchain"** — competitors lean on it; we deliberately do NOT, using plain signed credentials + a hash-chain audit. Say so explicitly as a design virtue.
4. **Confusing "recognised software" with endorsement** — HMRC recognition is a technical check, not a quality rating; do not conflate the two.
5. **Presenting cumulative limits as enforceable in the token** — a technically literate judge will catch this; be explicit that limits need gateway state (LIMIT in token, TOTAL in a stateful counter).

## Caveats
- MMTAR dates and mechanics come from a live, staged rollout (opened 18 May 2026, phased to 31 March 2027); the specific window and reference-number formats above are illustrative — confirm exact windows and identifier formats against GOV.UK before quoting them as settled.
- The passport is a research prototype; all HMRC references are to public documentation (GOV.UK, the HMRC Developer Hub), not to any integration or HMRC endorsement.
- Several standards are recent and still stabilising: W3C VCDM 2.0 and Bitstring Status List v1.0 reached Recommendation in May 2025, and RFC 9864 (Oct 2025) deprecates the polymorphic `EdDSA` identifier in favour of fully-specified alg values — treat these forward-looking items as roadmap, not established practice, for a 5-day build.
- Some secondary sources (accountancy-press and vendor blogs) were used for procedural colour; all load-bearing legal, API, and cryptographic claims are anchored to GOV.UK, the HMRC Developer Hub, IETF RFCs, W3C specs, the FCA Handbook, or NIST.