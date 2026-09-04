/* Agent Passport — frontend-only prototype.
   Everything runs in the browser: the credential is a real JWT signed with
   WebCrypto (Ed25519, falling back to ES256), the gateway rules are plain
   ordered functions, cumulative totals and revocation live in a "registry"
   object (localStorage), and every decision is hash-chained with SHA-256.
   No server. Synthetic data only. */

'use strict';

// ───────────────────────── Synthetic data ─────────────────────────
const RULE_PACK = 'hmrc-rules-2026.09';
const ISSUER = 'uk-tax-authority-demo';
const OFFICER = 'M. Whitcombe';

const APPLICATION = {
  firm: {
    'Firm': { v: 'Fenland & Grey LLP', sub: 'Registered office: 14 Quayside, Cambridge CB5 8AB' },
    'Agent Reference Number (ARN)': { v: 'ARN4471220', mono: true, sub: 'Agent Services Account' },
    'MMTAR registration': { v: 'MMTAR-2026-8812', mono: true, sub: 'Mandatory tax-adviser registration, window 1' },
    'AML supervisor': { v: 'ICAEW', sub: 'Supervision ref. C0092331' },
    'Accountable person': { v: 'Margaret Osei, Head of Tax', sub: 'Appointment letter dated 12 Aug 2026' },
  },
  agent: {
    'Agent identifier': { v: 'fg-filing-agent-01', mono: true },
    'Purpose': { v: 'Prepare and submit VAT returns and MTD quarterly updates for authorised clients' },
    'Model provider': { v: 'Anthropic (Claude)', sub: 'Deployed by the firm; provider listed on the provider register' },
    'Human oversight': { v: 'Filings above the escalation threshold are held for a named reviewer' },
    'Logging': { v: 'Every call carries Gov-Client fraud-prevention headers and an internal case reference' },
  },
  scope: {
    'Actions requested': { v: 'submit_vat_return · submit_quarterly_update · view_client_records', mono: true },
    'Client coverage': { v: 'Clients on the firm’s 64-8 / digital-handshake list only' },
    'Per-filing limit': { v: '£5,000' },
    'Cumulative limit': { v: '£20,000 in any rolling 30-day window' },
    'Escalation threshold': { v: '£3,500 — anything above is held for human approval' },
    'Requested validity': { v: 'Until 31 January 2027' },
  },
};

const SCOPE = {
  type: 'uk_tax_filing',
  actions: ['submit_vat_return', 'submit_quarterly_update', 'view_client_records'],
  client_coverage: 'per-64-8-list',
  per_filing_limit: { amount: 5000, currency: 'GBP' },
  cumulative_limit: { amount: 20000, currency: 'GBP', window: 'P30D' },
  escalation_threshold: { amount: 3500, currency: 'GBP' },
};

const CHECKS = [
  ['1.1', 'Firm registration matches record', 'Registration extract'],
  ['1.2', 'ARN valid and active', 'ASA record'],
  ['1.3', 'MMTAR registration current', 'MMTAR register'],
  ['2.1', 'Accountable person named and evidenced', 'Appointment letter'],
  ['2.2', 'AML supervision confirmed — ICAEW', 'Supervisor register'],
  ['3.2', 'Model provider not restricted', 'Provider register'],
  ['4.1 / 4.4', 'Requested scopes and limits within policy ceilings', 'Policy table'],
];

// Beats: the seven demo moves, in order.
const BEATS = [
  { label: 'VAT return', sub: '£1,400 · client on 64-8 list', action: 'submit_vat_return', amount: 1400, onList: true, expect: 'ALLOW' },
  { label: 'Quarterly update', sub: '£4,200 · on list', action: 'submit_quarterly_update', amount: 4200, onList: true, expect: 'ESCALATE 4.5' },
  { label: 'VAT return', sub: '£900 · client NOT on 64-8 list', action: 'submit_vat_return', amount: 900, onList: false, expect: 'DENY 5.2' },
  { label: 'VAT return', sub: '£9,400 · on list', action: 'submit_vat_return', amount: 9400, onList: true, expect: 'DENY 4.2' },
  { label: 'View client records', sub: 'on list', action: 'view_client_records', amount: 0, onList: true, expect: 'ALLOW' },
  { label: 'VAT return', sub: '£3,400 · on list — repeat; the sixth breaches £20,000', action: 'submit_vat_return', amount: 3400, onList: true, expect: 'ALLOW → DENY 4.3' },
  { label: 'Amend prior return', sub: 'not a recognised action', action: 'amend_prior_return', amount: 500, onList: true, expect: 'DENY 4.1' },
];

const RULES = [
  ['0.1', 'Passport status must be ACTIVE in the registry', 'registry'],
  ['0.2', 'Signature valid (Ed25519) and within nbf / exp', 'token'],
  ['5.2', 'Client must be on the firm’s 64-8 / handshake list', 'registry'],
  ['4.1', 'Action must be listed in authorization_details.actions — deny by default', 'token'],
  ['4.2', 'Amount must not exceed per_filing_limit', 'token'],
  ['4.3', 'Running 30-day total plus this amount must not exceed cumulative_limit', 'token limit · registry total'],
  ['4.5', 'Amount above escalation_threshold is held for a named human', 'token'],
];

// ───────────────────────── State ─────────────────────────
const LS = 'agent-passport-proto-v1';
let S = {
  application: null,   // {ref, submittedAt}
  passport: null,      // {id, jwt, header, payload, alg, verified}
  status: null,        // 'active' | 'revoked'
  filings: [],         // [{t, amount}] allowed filings only
  audit: [],           // gateway decisions
  actions: [],         // supervisory log
  keys: null,          // {alg, publicJwk, privateJwk}
  prevHash: 'genesis',
};
function save() { try { localStorage.setItem(LS, JSON.stringify(S)); } catch (_) {} }
function load() { try { const x = JSON.parse(localStorage.getItem(LS)); if (x && x.prevHash) S = x; } catch (_) {} }

// ───────────────────────── Crypto ─────────────────────────
const enc = new TextEncoder();
const b64u = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
const b64uStr = (s) => b64u(enc.encode(s));
const fromB64u = (s) => { s = s.replace(/-/g, '+').replace(/_/g, '/'); while (s.length % 4) s += '='; return Uint8Array.from(atob(s), c => c.charCodeAt(0)); };
async function sha256Hex(s) { const h = await crypto.subtle.digest('SHA-256', enc.encode(s)); return [...new Uint8Array(h)].map(b => b.toString(16).padStart(2, '0')).join(''); }

async function ensureKeys() {
  if (S.keys) return S.keys;
  let alg = 'EdDSA', pair;
  try {
    pair = await crypto.subtle.generateKey({ name: 'Ed25519' }, true, ['sign', 'verify']);
  } catch (_) {
    alg = 'ES256';
    pair = await crypto.subtle.generateKey({ name: 'ECDSA', namedCurve: 'P-256' }, true, ['sign', 'verify']);
  }
  S.keys = {
    alg,
    publicJwk: await crypto.subtle.exportKey('jwk', pair.publicKey),
    privateJwk: await crypto.subtle.exportKey('jwk', pair.privateKey),
  };
  save();
  return S.keys;
}
function algoParams(alg) { return alg === 'EdDSA' ? { name: 'Ed25519' } : { name: 'ECDSA', namedCurve: 'P-256' }; }
function signParams(alg) { return alg === 'EdDSA' ? { name: 'Ed25519' } : { name: 'ECDSA', hash: 'SHA-256' }; }
async function importKey(jwk, alg, usage) { return crypto.subtle.importKey('jwk', jwk, algoParams(alg), true, [usage]); }

async function signJwt(payload) {
  const k = await ensureKeys();
  const header = { alg: k.alg, typ: 'JWT', kid: await keyThumb() };
  const signingInput = `${b64uStr(JSON.stringify(header))}.${b64uStr(JSON.stringify(payload))}`;
  const priv = await importKey(k.privateJwk, k.alg, 'sign');
  const sig = await crypto.subtle.sign(signParams(k.alg), priv, enc.encode(signingInput));
  return { jwt: `${signingInput}.${b64u(sig)}`, header };
}
async function verifyJwt(jwt) {
  const k = S.keys; if (!k || !jwt) return false;
  const [h, p, s] = jwt.split('.');
  const pub = await importKey(k.publicJwk, k.alg, 'verify');
  return crypto.subtle.verify(signParams(k.alg), pub, fromB64u(s), enc.encode(`${h}.${p}`));
}
async function keyThumb() { const k = await ensureKeys(); const j = k.publicJwk; const canon = j.kty === 'OKP' ? { crv: j.crv, kty: j.kty, x: j.x } : { crv: j.crv, kty: j.kty, x: j.x, y: j.y }; return (await sha256Hex(JSON.stringify(canon))).slice(0, 16); }

// ───────────────────────── Gateway rules ─────────────────────────
const gbp = (n) => '£' + n.toLocaleString('en-GB');
function windowTotal() { const cutoff = Date.now() - 30 * 864e5; return S.filings.filter(f => f.t > cutoff).reduce((a, f) => a + f.amount, 0); }

async function verify(req) {
  // Ordered, deny by default. Returns the first failing rule.
  const p = S.passport && S.passport.payload;
  if (!S.passport) return { decision: 'DENY', rule: '0.1', reason: 'no passport issued for this agent' };
  if (S.status !== 'active') return { decision: 'DENY', rule: '0.1', reason: 'passport not active — status is ' + S.status.toUpperCase() };
  const sigOk = await verifyJwt(S.passport.jwt);
  const now = Math.floor(Date.now() / 1000);
  if (!sigOk || now < p.nbf || now > p.exp) return { decision: 'DENY', rule: '0.2', reason: sigOk ? 'passport outside validity window' : 'signature does not verify against the authority key' };
  if (!req.onList) return { decision: 'DENY', rule: '5.2', reason: 'client not on the firm’s 64-8 authorisation list' };
  const ad = p.authorization_details[0];
  if (!ad.actions.includes(req.action)) return { decision: 'DENY', rule: '4.1', reason: `action "${req.action}" not in authorised scope (deny by default)` };
  const isFiling = req.action !== 'view_client_records';
  if (isFiling) {
    if (req.amount > ad.per_filing_limit.amount) return { decision: 'DENY', rule: '4.2', reason: `${gbp(req.amount)} exceeds per-filing limit ${gbp(ad.per_filing_limit.amount)}` };
    const total = windowTotal();
    if (total + req.amount > ad.cumulative_limit.amount) return { decision: 'DENY', rule: '4.3', reason: `${gbp(total)} already filed in 30 days; ${gbp(req.amount)} would exceed cumulative limit ${gbp(ad.cumulative_limit.amount)} — structuring caught` };
    if (req.amount > ad.escalation_threshold.amount) return { decision: 'ESCALATE', rule: '4.5', reason: `${gbp(req.amount)} above human-review threshold ${gbp(ad.escalation_threshold.amount)} — held for named reviewer` };
  }
  return { decision: 'ALLOW', rule: isFiling ? '4.1–4.5, 5.2' : '4.1', reason: isFiling ? 'within scope and limits' : 'read action within scope' };
}

async function appendAudit(entry) {
  const body = JSON.stringify(entry);
  const hash = (await sha256Hex(S.prevHash + body)).slice(0, 12);
  const rec = { ...entry, prev: S.prevHash.slice(0, 12), ref: hash };
  S.prevHash = hash;
  S.audit.push(rec);
  save();
  return rec;
}

// ───────────────────────── DOM helpers ─────────────────────────
const $ = (id) => document.getElementById(id);
const el = (tag, cls, html) => { const n = document.createElement(tag); if (cls) n.className = cls; if (html != null) n.innerHTML = html; return n; };
const esc = (s) => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const tstamp = (t = Date.now()) => new Date(t).toLocaleTimeString('en-GB', { hour12: false });
const dstamp = (t) => new Date(t).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });

function renderSummary(id, rows) {
  const dl = $(id); dl.innerHTML = '';
  for (const [k, r] of Object.entries(rows)) {
    const d = el('div');
    d.append(el('dt', null, esc(k)));
    const dd = el('dd', null, `<span class="${r.mono ? 'mono' : ''}">${esc(r.v)}</span>${r.sub ? `<span class="sub">${esc(r.sub)}</span>` : ''}`);
    d.append(dd); dl.append(d);
  }
}

// ───────────────────────── Views ─────────────────────────
function show(view) {
  document.querySelectorAll('.view').forEach(v => v.hidden = v.id !== 'view-' + view);
  document.querySelectorAll('.tabs__tab').forEach(t => t.setAttribute('aria-selected', String(t.dataset.view === view)));
  location.hash = view;
  window.scrollTo({ top: 0 });
}

function logAction(text) { S.actions.push({ t: Date.now(), text }); save(); renderActions(); }
function renderActions() {
  const ol = $('rg-log'); ol.innerHTML = '';
  if (!S.actions.length) { ol.append(el('li', 'log__empty', 'No actions recorded.')); return; }
  for (const a of [...S.actions].reverse()) ol.append(el('li', null, `<time>${tstamp(a.t)}</time><span>${esc(a.text)}</span>`));
}

function renderOperator() {
  renderSummary('op-firm', APPLICATION.firm);
  renderSummary('op-agent', APPLICATION.agent);
  renderSummary('op-scope', APPLICATION.scope);
  const done = !!S.application;
  $('op-submit').disabled = done;
  $('op-note').textContent = done ? `Submitted ${tstamp(S.application.submittedAt)} · reference ${S.application.ref}` : '';
  $('op-confirm').hidden = !done;
  if (done) $('op-ref').textContent = S.application.ref;
}

async function renderRegulator() {
  const has = !!S.application;
  $('rg-empty').hidden = has; $('rg-case').hidden = !has;
  $('rg-ref').textContent = has ? S.application.ref : '—';
  $('rg-pack').textContent = RULE_PACK; $('side-pack').textContent = RULE_PACK;
  $('side-id').textContent = S.passport ? S.passport.id : '—';
  $('side-status').innerHTML = S.status ? statusTag() : '—';
  $('side-key').textContent = S.keys ? `${S.keys.alg} · kid ${await keyThumb()}` : '—';
  if (!has) { renderActions(); return; }

  const tb = $('rg-checks').querySelector('tbody');
  if (!tb.children.length) {
    for (const [rule, check, src] of CHECKS) {
      const tr = el('tr', 'pending'); tr.innerHTML = `<td>${rule}</td><td>${esc(check)}</td><td>${esc(src)}</td><td>Checking…</td>`; tb.append(tr);
    }
    // Stagger the pass stamps so the officer sees them arrive.
    [...tb.children].forEach((tr, i) => setTimeout(() => { tr.classList.remove('pending'); tr.lastElementChild.innerHTML = '<span class="tag tag--green">Pass</span>'; }, S.passport ? 0 : 180 + i * 140));
  }
  $('rg-decide').hidden = !!S.passport;
  $('rg-issued').hidden = !S.passport;
  if (S.passport) await renderPassport();
  renderActions();
}

function statusTag() { return S.status === 'active' ? '<span class="tag tag--green">Active</span>' : '<span class="tag tag--red">Revoked</span>'; }

async function renderPassport() {
  const p = S.passport.payload, ad = p.authorization_details[0];
  $('pp-id').textContent = p.jti;
  $('pp-agent').textContent = p.subject.agent_id;
  $('pp-firm').textContent = `${p.subject.operator.firm} · ${p.subject.operator.arn}`;
  $('pp-person').textContent = p.subject.accountable_person;
  $('pp-valid').textContent = `${dstamp(p.nbf * 1000)} → ${dstamp(p.exp * 1000)}`;
  $('pp-actions').textContent = ad.actions.join(' · ');
  $('pp-perfiling').textContent = gbp(ad.per_filing_limit.amount);
  $('pp-cum').textContent = gbp(ad.cumulative_limit.amount);
  $('pp-esc').textContent = gbp(ad.escalation_threshold.amount);
  const ok = await verifyJwt(S.passport.jwt);
  $('pp-sig').innerHTML = ok ? `<span class="tag tag--green">Verified</span> ${S.keys.alg === 'EdDSA' ? 'Ed25519' : 'ES256 (P-256)'} · kid ${esc(S.passport.header.kid)}` : '<span class="tag tag--red">Not verified</span>';
  $('rg-status').outerHTML = statusTag().replace('class="tag', 'id="rg-status" class="tag');
  $('rg-passport').classList.toggle('passport--revoked', S.status === 'revoked');
  $('rg-revoke').hidden = S.status !== 'active';
  $('rg-reactivate').hidden = S.status === 'active';
  $('jwt-header').textContent = JSON.stringify(S.passport.header, null, 2);
  $('jwt-payload').textContent = JSON.stringify(p, null, 2);
  $('jwt-compact').textContent = S.passport.jwt;
}

function renderRelying() {
  $('term-pack').textContent = RULE_PACK;
  $('st-id').textContent = S.passport ? S.passport.id : 'none';
  $('st-status').innerHTML = S.status ? statusTag() : '<span class="tag tag--grey">Not issued</span>';
  $('st-count').textContent = S.filings.length;
  const total = windowTotal(), cap = SCOPE.cumulative_limit.amount, pct = Math.min(100, total / cap * 100);
  $('st-cum').textContent = `${gbp(total)} of ${gbp(cap)} · ${Math.round(pct)}%`;
  const fill = $('st-fill'); fill.style.transform = `scaleX(${pct/100})`;
  fill.className = 'meter__fill' + (pct >= 100 ? ' over' : pct >= 75 ? ' warn' : '');

  const ol = $('beats');
  if (!ol.children.length) BEATS.forEach((b, i) => {
    const li = el('li');
    const btn = el('button', 'beat'); btn.type = 'button'; btn.dataset.i = i;
    btn.innerHTML = `<span class="beat__label"><span>${esc(b.label)}</span><small>${esc(b.sub)}</small></span><span class="beat__expect">${esc(b.expect)}</span>`;
    li.append(btn); ol.append(li);
  });
  const rules = $('rules');
  if (!rules.children.length) RULES.forEach(([id, txt, where]) => rules.append(el('li', null, `<code>${id}</code> ${esc(txt)} <span class="small">— ${esc(where)}</span>`)));

  const lines = $('term-lines'); lines.innerHTML = '';
  if (!S.audit.length) lines.append(el('li', 'terminal__hint', S.passport ? 'Waiting for a proposed action.' : 'No passport in the registry. Every request will be denied on rule 0.1.'));
  for (const r of S.audit) lines.append(termLine(r));
  lines.scrollTop = lines.scrollHeight;
}

function termLine(r) {
  const li = el('li');
  li.innerHTML = `<span class="t-time">${tstamp(r.t)}</span><span class="t-body">
    <span class="t-head"><span class="t-action">${esc(r.action)}${r.amount ? ' · ' + gbp(r.amount) : ''}${r.onList === false ? ' · client off-list' : ''}</span><span class="t-verdict t-verdict--${r.decision}">${r.decision}</span><span class="t-rule">rule ${esc(r.rule)}</span></span>
    <span class="t-reason">${esc(r.reason)}</span>
    <span class="t-meta">audit <b>${r.ref}</b> ← <b>${r.prev}</b> · rule pack <b>${RULE_PACK}</b> · decision replayable</span></span>`;
  return li;
}

// ───────────────────────── Actions ─────────────────────────
async function submitApplication() {
  if (S.application) return;
  S.application = { ref: 'AP-2026-0091', submittedAt: Date.now() };
  save(); renderOperator();
  logAction(`Application ${S.application.ref} received from Fenland & Grey LLP for agent fg-filing-agent-01.`);
}

async function approve() {
  if (S.passport) return;
  const now = Math.floor(Date.now() / 1000);
  const payload = {
    iss: ISSUER, jti: S.application.ref, nbf: now, exp: Math.floor(Date.UTC(2027, 0, 31, 23, 59, 59) / 1000),
    rule_pack_version: RULE_PACK,
    subject: {
      agent_id: 'fg-filing-agent-01',
      operator: { firm: 'Fenland & Grey LLP', arn: 'ARN4471220', aml_supervisor: 'ICAEW', mmtar_ref: 'MMTAR-2026-8812' },
      accountable_person: 'Margaret Osei, Head of Tax',
      model_provider: 'Anthropic (Claude)',
    },
    authorization_details: [SCOPE],
    cnf: null, // Rung 2: holder key binding (RFC 7800 / DPoP) — deliberately not implemented in this baseline
    status: { registry: `/api/status/${S.application.ref}` },
    issued_by: OFFICER,
  };
  const { jwt, header } = await signJwt(payload);
  S.passport = { id: payload.jti, jwt, header, payload };
  S.status = 'active'; save();
  logAction(`${OFFICER} approved ${payload.jti}; passport signed (${header.alg}) and entered in the registry as ACTIVE.`);
  await renderRegulator();
}

async function revoke() {
  if (S.status !== 'active') return;
  S.status = 'revoked'; save();
  logAction(`${OFFICER} revoked ${S.passport.id}. Registry status flipped; the next verification denies on rule 0.1.`);
  await renderRegulator();
}
async function reactivate() {
  S.status = 'active'; save();
  logAction(`${OFFICER} reactivated ${S.passport.id} (demo convenience).`);
  await renderRegulator();
}

async function fire(i) {
  const b = BEATS[i];
  const req = { action: b.action, amount: b.amount, onList: b.onList };
  const res = await verify(req);
  if (res.decision === 'ALLOW' && b.action !== 'view_client_records') S.filings.push({ t: Date.now(), amount: b.amount });
  const rec = await appendAudit({ t: Date.now(), agent: 'fg-filing-agent-01', ...req, ...res });
  renderRelying();
  const lines = $('term-lines'); lines.scrollTop = lines.scrollHeight;
  return rec;
}

function resetTotals() { S.filings = []; S.audit = []; S.prevHash = 'genesis'; save(); renderRelying(); }

// ───────────────────────── Boot ─────────────────────────
async function boot() {
  load();
  await ensureKeys();
  $('foot-pack').textContent = 'rule pack ' + RULE_PACK;
  $('foot-key').textContent = `issuer key ${S.keys.alg} · kid ${await keyThumb()}`;

  document.querySelectorAll('.tabs__tab').forEach(t => t.addEventListener('click', () => show(t.dataset.view)));
  document.addEventListener('click', (e) => { const g = e.target.closest('[data-goto]'); if (g) show(g.dataset.goto); });
  $('op-submit').addEventListener('click', submitApplication);
  $('rg-approve').addEventListener('click', approve);
  $('rg-reject').addEventListener('click', () => logAction(`${OFFICER} opened a rejection (stub): reasons would be recorded and returned to the operator.`));
  document.addEventListener('click', (e) => { if (e.target.id === 'rg-revoke') revoke(); if (e.target.id === 'rg-reactivate') reactivate(); });
  $('beats').addEventListener('click', (e) => { const b = e.target.closest('.beat'); if (b) fire(+b.dataset.i); });
  $('rl-reset').addEventListener('click', resetTotals);

  // hidden full reset: double-click the rule-pack label in the footer
  $('foot-pack').addEventListener('dblclick', () => { if (confirm('Reset the whole demo?')) { localStorage.removeItem(LS); location.reload(); } });

  renderOperator(); await renderRegulator(); renderRelying();
  const v = (location.hash || '#operator').slice(1);
  show(['operator', 'regulator', 'relying', 'about'].includes(v) ? v : 'operator');
}
boot();

// Debug handle for the team and for automated tests.
window.AP = { get S() { return S; }, show, fire, approve, revoke, reactivate, submitApplication, verifyJwt, windowTotal, RULE_PACK, BEATS };
