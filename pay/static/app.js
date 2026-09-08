/* Agent Passport, bank-first. View controllers. The server holds all state; this file renders it and calls the API. */
'use strict';

const AP = (() => {
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, html) => { const n = document.createElement(tag); if (cls) n.className = cls; if (html != null) n.innerHTML = html; return n; };
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const t = (iso) => iso ? new Date(iso).toLocaleTimeString('en-GB', { hour12: false }) : '';
  const d = (iso) => iso ? new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '';
  const gbp = (n) => '£' + Number(n || 0).toLocaleString('en-GB');
  async function api(method, url, body) {
    const r = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : (j.detail && j.detail.problems ? j.detail.message + ': ' + j.detail.problems.map(x => x.problem).join('; ') : (JSON.stringify(j.detail) || r.statusText)));
    if (j && Array.isArray(j.decisions)) lastDecisions = j.decisions;
    return j;
  }
  const statusTag = (s) => ({ pending: 'amber', active: 'green', admitted: 'green', registered: 'blue', info_requested: 'amber', suspended: 'amber', draft: 'grey', declined: 'red', revoked: 'red', lapsed: 'grey', expired: 'red', signed: 'green', unsigned: 'amber', OPEN: 'amber', INVESTIGATING: 'blue', RESOLVED: 'green' }[s] || 'grey');
  const tag = (s, label) => `<span class="tag tag--${statusTag(s)}">${esc(label || String(s).replace('_', ' '))}</span>`;
  const v = (f, ...path) => { let c = f; for (const p of path) { if (!c || typeof c !== 'object' || !(p in c)) return undefined; c = c[p]; } return (c && typeof c === 'object' && 'value' in c) ? c.value : c; };
  const NUMERIC = new Set(['hold_above_gbp', 'cover_gbp']);
  const jwtPayload = (tok) => { try { const b = tok.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'); return JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(b), c => c.charCodeAt(0)))); } catch (e) { return null; } };
  const rows = (id, list, cols, empty = 'None yet.') => { const tb = $(id).querySelector('tbody'); tb.innerHTML = ''; const numCols = [...$(id).querySelectorAll('thead th')].map(th => th.classList.contains('num')); list.forEach(x => { const tr = el('tr', null, x.cells.map((c, i) => `<td${numCols[i] ? ' class="num"' : ''}>${c}</td>`).join('')); if (x.attrs) Object.assign(tr.dataset, x.attrs); tb.append(tr); }); if (!list.length) tb.append(el('tr', null, `<td class="empty-row" colspan="${cols}">${esc(empty)}</td>`)); };
  const admissionTag = (a) => a.admission_status ? tag(a.admission_status, { admitted: 'admitted', suspended: 'suspended', revoked: 'removed', declined: 'declined', info_requested: 'information requested' }[a.admission_status] || a.admission_status) : (a.status === 'registered' ? tag('grey', 'not yet decided') : tag('grey', '—'));
  const regTag = (a) => a.status === 'registered' ? tag('active', 'on the register') : tag('draft', 'draft');
  const modeLabel = (m) => m === 'gemini' ? 'Gemini (live)' : m === 'fixture' ? 'fixture (deterministic stand-in)' : 'fixture after Gemini failed';
  const holdOf = (a) => (((a && a.condition) || {}).hold_above || {}).amount;
  const LEVELS = { 'self-declared': ['Self-declared', 'grey'], 'independently-verified': ['Independently verified', 'blue'], 'independently-audited': ['Independently audited', 'green'] };
  // one assurance badge everywhere: neutral tint, the level's name; used on /provider, the bank register and admission view, the customer picker
  const levelTag = (id) => { const l = LEVELS[id]; return l ? `<span class="tag tag--level" title="assurance level declared by the provider with its evidence, not certified by anyone">${l[0]}</span>` : '<span class="tag tag--level">no level declared</span>'; };
  // Exactly two refusal classes (the mapping itself lives in the rule pack next to the rules). Agent error is deliberately calm: grey, never red.
  const CLASSES = { fraud: ['Fraud indicator', 'red'], agent_error: ['Agent error', 'grey'] };
  const CLASS_LEGEND = { fraud: 'Fraud indicator: something the customer never authorised (a wrong account, an invalid signature, a passport not in force, a replayed instruction). For the bank\'s risk team.', agent_error: 'Agent error: the AI agent\'s own mistake inside its remit (amount, currency, action, frequency, an expired mandate). A quality signal for its owner, not a report to anyone.' };
  const LEGEND_LINE = 'Fraud indicator: something the customer never authorised. Agent error: the agent\'s own mistake inside its remit; a quality signal for its owner, not a report to anyone.';
  const classId = (c) => { const id = typeof c === 'string' ? c : (c && c.id); return CLASSES[id] ? id : 'agent_error'; };
  const chip = (kind, label, title) => `<span class="tag tag--${kind}"${title ? ` title="${esc(title)}"` : ''}>${esc(label)}</span>`;
  const classTag = (c) => { const id = classId(c); return chip(CLASSES[id][1], CLASSES[id][0], CLASS_LEGEND[id]); };
  // every instruction resolves to one status: Processed, Held, or Refused with its class; a decided hold shows what the person decided
  let lastDecisions = [];
  const FIRST = 'FIRST_PAYMENT_CONFIRMATION_REQUIRED';
  const decisionFor = (auditId) => lastDecisions.find(x => x.entry.held_audit_id === auditId);
  const statusChip = (r) => {
    const e = r.entry || {};
    if (e.decision === 'ALLOW') return chip('green', 'Processed', 'all nine checks passed; money moved');
    if (e.decision === 'ESCALATE') {
      const dd = decisionFor(r.id), first = e.code === FIRST;
      if (!dd) return first ? chip('amber', 'Held · first payment', 'the first payment under this mandate version waits for the customer to review and confirm it once') : chip('amber', 'Held', 'inside the mandate, above the bank\'s hold condition; a named person decides');
      if (dd.entry.outcome === 'RELEASED') return chip('green', first ? 'Processed · confirmed by the customer' : 'Processed · released by approver', first ? 'the customer reviewed and confirmed its first payment under this mandate; recorded in the chain' : 'held, then released by a named person; recorded in the chain');
      return chip('grey', first ? 'Refused · by the customer' : 'Refused · by approver', first ? 'the customer refused the first payment under this mandate; recorded in the chain' : 'held, then refused by a named person; recorded in the chain');
    }
    const id = classId(e.failure_class); return chip(CLASSES[id][1], 'Refused · ' + CLASSES[id][0].toLowerCase(), CLASS_LEGEND[id]);
  };

  const LABELS = {
    company: { title: 'Provider', legal_name: 'Legal name', companies_house_number: 'Companies House number', website: 'Website' },
    principal: { title: 'Accountable principal', name: 'Name', role: 'Role', declaration_ref: 'Declaration reference' },
    insurance: { title: 'Insurance', insurer: 'Insurer', policy_ref: 'Policy reference', cover_gbp: 'Cover (£)', expires: 'In force until' },
    product: { title: 'The AI product', product_name: 'Product name', product_id: 'Product identifier', release: 'Release', model_provider: 'Foundation model provider', model_version: 'Foundation model version (pinned)', documentation_url: 'Documentation (URL)' },
    assurance_evidence: { title: 'Independent Assurance Evidence', level: 'Assurance level', issuer: 'Issuer', reference: 'Reference', date: 'Date', use_case: 'Use case covered', summary: 'What it covers', report_url: 'Report (URL)' },
    intended_use: { title: 'Registered use', payment_intent: 'Payment intent', description: 'Description' },
    data_protection: { title: 'UK data protection', uk_gdpr_compliant: 'Complies with UK GDPR and the Data Protection Act 2018', ico_registration: 'ICO registration number', retention_period: 'Personal data retention period', dpia_reference: 'Data protection impact assessment (reference)' },
  };
  const ENUMS = (state) => ({ payment_intent: (state.payment_intents || []).map(x => [x.id, x.label]), retention_period: (state.retention_periods || []).map(x => [x.id, x.label]), uk_gdpr_compliant: [['yes', 'Yes, declared by the accountable principal'], ['no', 'No']] });
  const SECTION_HINTS = {
    principal: 'The person who declares this filing accurate, as for a Companies House filing. Accountable for the filing, not for what any AI agent later does.',
    intended_use: 'One payment intent per filing. The bank admits the product for that intent, and every customer mandate on it is limited to that intent; anything else is refused at R.6.',
    data_protection: 'What the provider declares about personal data the AI agent processes (invoice and payee details): compliance with UK GDPR and the Data Protection Act 2018, its ICO registration, and how long personal data is kept. The register records the declaration; it verifies nothing about compliance.',
    assurance_evidence: 'An independent benchmark or audit that the product meets the minimum assurance requirements for its use case, and the assurance level you declare with it: self-declared, independently verified, independently audited. The level describes the evidence you provide; the register does not grade it. Each bank assesses it against its own requirements.',
  };

  function checksTable(id, checks) {
    const cb = $(id).querySelector('tbody'); cb.innerHTML = '';
    (checks || []).forEach(c => cb.append(el('tr', null, `<td>${esc(c.id)}</td><td>${esc(c.title)} <span class="tag tag--${c.status === 'CURRENT' ? 'green' : 'grey'}">${esc(c.status)}</span><br><span class="small">${esc(c.detail)}</span></td><td>${esc(c.source)}<br><span class="small">${esc(c.evidence)}</span></td><td>${c.result === 'pass' ? '<span class="tag tag--green">Pass</span>' : '<span class="tag tag--amber">Flag</span>'}</td>`)));
  }

  // ───────────── Provider: register an AI product ─────────────
  async function provider() {
    let state = await api('GET', '/api/state');
    const ref0 = new URLSearchParams(location.search).get('ref');
    let a = state.registrations.find(x => x.ref === ref0) || null;
    render();

    async function refresh() { state = await api('GET', '/api/state'); a = state.registrations.find(x => x.id === (a && a.id)) || null; render(); }

    function render() {
      const regs = state.registrations, prior = state.register || [];
      rows('pv-products', [
        ...regs.map(x => ({ cells: [`<a href="/provider?ref=${x.ref}">${esc(x.ref)}</a>`, esc(v(x.fields, 'product', 'product_name') || 'Untitled'), esc(v(x.fields, 'company', 'legal_name') || ''), levelTag(v(x.fields, 'assurance_evidence', 'level')), d(x.submitted_at), regTag(x), admissionTag(x)] })),
        ...prior.map(m => ({ cells: [esc(m.registration), esc(m.product), esc(m.provider), levelTag(m.assurance_level), d(m.registered), tag(m.status, m.status === 'active' ? 'on the register' : m.status), m.bank ? tag('admitted', 'admitted') : '<span class="small">no decision</span>'] })),
      ], 7);
      const has = !!a, draft = has && a.status === 'draft';
      $('pv-form').hidden = !has;
      if (has) { $('pv-ref').textContent = a.ref; $('pv-status').innerHTML = regTag(a); }
      $('btn-prefill').hidden = !draft;
      $('pv-submit').hidden = !draft;
      if (has) { renderFacts(a.fields, draft); } else { $('facts').innerHTML = ''; $('btn-save-fields').hidden = true; }
      const filed = has && a.status !== 'draft';
      $('confirm').hidden = !filed; $('pv-checks-wrap').hidden = !filed;
      if (filed) { $('confirm-ref').textContent = a.ref; checksTable('pv-checks', a.checks); $('pv-receipt').textContent = a.registration_jwt || ''; $('pv-receipt-payload').textContent = JSON.stringify(jwtPayload(a.registration_jwt || ''), null, 2); }
    }

    function renderFacts(f, editable) {
      const box = $('facts'); box.innerHTML = ''; box.className = 'facts';
      for (const [sec, labels] of Object.entries(LABELS)) {
        box.append(el('h3', null, esc(labels.title)));
        if (SECTION_HINTS[sec]) box.append(el('p', 'hint', esc(SECTION_HINTS[sec])));
        const dl = el('dl');
        for (const [k, label] of Object.entries(labels)) {
          if (k === 'title') continue;
          const fact = (f[sec] || {})[k] || { value: null };
          const enums = ENUMS(state);
          const input = k === 'level'
            ? `<select class="input" data-sec="${sec}" data-key="${k}" ${editable ? '' : 'disabled'} aria-label="${esc(label)}">${Object.entries(LEVELS).map(([id, l]) => `<option value="${id}" ${fact.value === id ? 'selected' : ''}>${l[0]}</option>`).join('')}</select>`
            : enums[k]
            ? `<select class="input" data-sec="${sec}" data-key="${k}" ${editable ? '' : 'disabled'} aria-label="${esc(label)}"><option value="" ${fact.value ? '' : 'selected'}>Choose</option>${enums[k].map(([id, l]) => `<option value="${id}" ${fact.value === id ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>`
            : `<input class="input" data-sec="${sec}" data-key="${k}" value="${esc(fact.value ?? '')}" ${editable ? '' : 'disabled'} aria-label="${esc(label)}">`;
          const extra = k === 'companies_house_number' ? `<span class="prov" id="pv-ch"></span>` : '';
          dl.append(el('div', 'fact', `<dt>${esc(label)}</dt><dd>${input}${extra}</dd>`));
        }
        box.append(dl);
      }
      $('btn-save-fields').hidden = !editable;
      const chIn = document.querySelector('#facts [data-key="companies_house_number"]');
      if (chIn) { const showCh = async () => { if (!chIn.value) return; const r = await api('GET', `/api/companies/${encodeURIComponent(chIn.value)}`); $('pv-ch').innerHTML = r.found ? `${esc(r.source)}: ${esc(r.legal_name)}, ${esc(r.status)}, ${esc(r.address)}` : `${esc(r.source)}: no company with this number`; }; chIn.onblur = showCh; showCh(); }
    }

    function collectFields() {
      const f = JSON.parse(JSON.stringify(a.fields));
      document.querySelectorAll('#facts [data-sec]').forEach(inp => {
        const cur = f[inp.dataset.sec][inp.dataset.key] || (f[inp.dataset.sec][inp.dataset.key] = {});
        cur.value = inp.value === '' ? null : (NUMERIC.has(inp.dataset.key) && !isNaN(inp.value) ? Number(inp.value) : inp.value);
      });
      return f;
    }

    if ($('btn-new')) $('btn-new').onclick = async () => { a = await api('POST', '/api/registrations'); history.replaceState(null, '', `?ref=${a.ref}`); await refresh(); };
    $('btn-prefill').onclick = () => { $('pv-context').hidden = false; $('pv-context').scrollIntoView({ behavior: 'smooth', block: 'center' }); };
    $('btn-prefill-go').onclick = async () => { $('pv-context').hidden = true; a = await api('POST', `/api/registrations/${a.id}/prefill`); await refresh(); };
    $('btn-prefill-cancel').onclick = () => { $('pv-context').hidden = true; };
    $('btn-save-fields').onclick = async () => { a = await api('PUT', `/api/registrations/${a.id}/fields`, { fields: collectFields() }); $('save-note').textContent = 'Saved ' + t(new Date().toISOString()); await refresh(); };
    $('btn-submit').onclick = async () => { await api('PUT', `/api/registrations/${a.id}/fields`, { fields: collectFields() }); a = await api('POST', `/api/registrations/${a.id}/submit`); await refresh(); $('confirm').scrollIntoView({ behavior: 'smooth', block: 'start' }); };
  }

  // ───────────── Bank console ─────────────
  function envelopePanels(full) {
    const pl = full, ver = full.verification.parts, a = pl.admission, i = pl.agent_identity, m = pl.mandate, mp = pl.mandate_proposed;
    const ad = (m || mp).authorization_details[0];
    const sig = (ok, who) => ok == null ? (full.status === 'pending' && who === 'bank' ? `<span class="tag tag--amber">Not issued yet</span>` : `<span class="tag tag--amber">Unsigned</span>`) : ok ? `<span class="tag tag--green">Verified · Ed25519</span>` : `<span class="tag tag--red">Signature fails</span>`;
    const kv = (rws) => `<dl class="envelope__kv">${rws.map(([k, val]) => `<div><dt>${k}</dt><dd>${val}</dd></div>`).join('')}</dl>`;
    return `
      <section>
        <span class="envelope__who">Signed by the bank · from its admission decision, when the customer signs</span>
        <h3 class="envelope__title">Admission ${sig(ver.admission, 'bank')}</h3>
        ${kv([['Product', `${esc(a.product_ref.product_name)} <span class="mono">${esc(a.product_ref.product_id)}</span> · ${esc(a.product_ref.provider)} · register <span class="mono small">${esc(a.product_ref.registration)}</span>`], ['Filing checks', `${a.admission.filing_checks_passed} passed${a.admission.filing_checks_flagged.length ? ', flagged ' + esc(a.admission.filing_checks_flagged.join(', ')) : ''}`], ['Hold condition', `hold above ${gbp(a.condition.hold_above.amount)}`], ['Ceilings', `≤ ${gbp(a.ceilings.per_payment_ceiling.amount)} per payment · ≤ ${gbp(a.ceilings.monthly_per_account_ceiling.amount)} per account in 30 days`], ['Accountable principal', `${esc(a.accountable_principal.name)}, ${esc(a.accountable_principal.role)} · ${esc(a.accountable_principal.covers)}`], ['Assurance evidence', `${esc(a.assurance_evidence.issuer)} <span class="mono small">${esc(a.assurance_evidence.reference)}</span>`], ['Valid until', esc(a.valid_until)], ['Bound to', `agent identity <span class="mono small">${esc(a.binds.agent_identity_sha256.slice(0, 12))}…</span>`]])}
      </section>
      <section>
        <span class="envelope__who">Signed by the customer · its deployment of the product</span>
        <h3 class="envelope__title">Agent identity ${sig(ver.agent_identity)}</h3>
        ${kv([['AI agent', `${esc(i.agent.name)} · <span class="mono">${esc(i.agent.agent_id)}</span>`], ['Public key', `<span class="mono small">kid ${esc(full.minimal.agent_kid)}</span> · possession ${i.deployment && i.deployment.proof_of_possession ? 'proven' : 'not proven'}`], ['Product', `${esc(i.agent.product_name)} · ${esc(i.agent.model_provider)} <span class="mono small">${esc(i.agent.model_version)}</span>`], ['Config SHA-256', `<span class="mono small">${esc((i.agent.config_sha256 || '').slice(0, 16))}…</span>`], ['Key custody', esc((i.deployment || {}).key_storage || '')]])}
      </section>
      <section>
        <span class="envelope__who">Signed by the customer · in its bank's app</span>
        <h3 class="envelope__title">Mandate ${sig(ver.mandate)}</h3>
        <span class="small">OAuth 2.0 RFC 9396 authorization_details · written by the customer within the admission ceilings</span>
        ${kv(m ? [['Customer', esc((mp.customer || {}).legal_name || '')], ['Signed by', `${esc((mp.authorising_officer || {}).name || '')}, ${esc((mp.authorising_officer || {}).role || '')}`], ['Payees', `${ad.supplier_allowlist.length} accounts`], ['Limits', `${gbp(ad.per_payment_limit.amount)} per payment · ${gbp(ad.monthly_limit_per_account.amount)} per account in 30 days`], ['Expires', esc(mp.valid_until)], ['Containment', '<span class="tag tag--green">within the ceilings</span>']]
                : [['Ceilings', `per payment ≤ ${gbp(a.ceilings.per_payment_ceiling.amount)} · per account in 30 days ≤ ${gbp(a.ceilings.monthly_per_account_ceiling.amount)} · expiry ≤ ${esc(a.ceilings.max_validity)}`], ['Actions', esc(a.ceilings.action_types.join(', '))]])}
        ${m ? '' : `<p class="envelope__pending">Awaiting the customer's signature in <a href="/customer">its banking app</a>. The passport is issued when the customer signs; until then the verifier refuses every instruction at R.1.</p>`}
      </section>`;
  }

  async function bank() {
    let state = await api('GET', '/api/bank/state');
    const q = new URLSearchParams(location.search);
    const issued = () => state.passports.filter(x => x.status !== 'pending');
    let p = q.get('passport') ? issued().find(x => x.passport_id === q.get('passport')) || null : null;
    let a = p ? state.registrations.find(x => x.id === p.registration_id) : (q.get('ref') ? state.registrations.find(x => x.ref === q.get('ref') && x.status !== 'draft') || null : null);
    const mode = p ? 'agent' : a ? 'case' : 'dash';
    let selectedVid = null;
    render();

    async function refresh() { state = await api('GET', '/api/bank/state'); if (a) a = state.registrations.find(x => x.id === a.id) || a; render(); }
    function passportFor() { return p ? (state.passports.find(x => x.passport_id === p.passport_id) || p) : null; }
    const who = () => state.cast ? `${state.cast.officer}, ${state.cast.team}` : '';

    function render() {
      $('bk-dash').hidden = mode !== 'dash'; $('bk-case').hidden = mode !== 'case'; $('bk-agent').hidden = mode !== 'agent';
      p = passportFor();
      $(mode === 'agent' ? 'bk-agent-anomaly' : 'bk-dash-anomaly').append($('bk-anomaly'));
      $(mode === 'agent' ? 'bk-agent-history' : 'bk-case-history').append($('bk-history-wrap'));
      $('bk-anomaly').hidden = mode === 'case'; $('bk-history-wrap').hidden = mode === 'dash';
      if (mode === 'dash') $('bk-anomaly').hidden = true;
      if (mode === 'dash') { renderDash(); return; } else if (mode === 'agent') renderAgent(); else renderCase();
      renderExceptions();
      renderIncidents();
      renderHistory();
    }
    let auditRows = [], seenIds = null, expandedId = null, expandedAtt = null, timer = null, simTimer = null, logFilter = 'all', logAll = false, pendingDecide = null;
    const pause = (ms) => new Promise(res => setTimeout(res, ms));
    const num = (n) => Number(n || 0).toLocaleString('en-GB');
    const agentName = (pid) => { const x = issued().find(y => y.passport_id === pid); return x ? (((x.agent_identity || {}).agent || {}).name || pid) : pid; };
    // arrivals are paced: a new instruction shows its checks ticking through, rule by rule, before the status lands
    const arriving = new Map();   // audit id → { step }
    const revealQueue = []; let revealing = false;
    const paced = () => $('bd-pace') && $('bd-pace').checked && !(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    function tickHtml(r) { const st = arriving.get(r.id) || { step: 0 }; const trace = r.entry.trace || []; return `<span class="bd-tick" data-tick="${r.id}">${trace.slice(0, st.step).map(x => `<i class="${x.ok ? 'ok' : (r.entry.decision === 'ESCALATE' ? 'hold' : 'fail')}">${esc(x.rule)}</i>`).join('')}<em>verifying</em></span>`; }
    const ruleHtml = (e) => e.decision === 'ALLOW' ? '<span class="small">all nine</span>' : `<b class="rule">${esc(e.rule)}</b> <span class="small">${esc((e.code || '').toLowerCase().replace(/_/g, ' '))}</span>`;
    function queueReveal(r) { revealQueue.push(r); if (!revealing) runReveals(); }
    async function runReveals() {
      revealing = true;
      while (revealQueue.length) {
        const r = revealQueue.shift(); const st = arriving.get(r.id); if (!st) continue;
        const trace = r.entry.trace || []; const beat = Math.max(70, Math.min(150, Math.round(1100 / Math.max(1, trace.length))));
        await pause(350);
        for (let i = 0; i < trace.length; i++) { st.step = i + 1; document.querySelectorAll(`[data-tick="${r.id}"]`).forEach(c => { c.outerHTML = tickHtml(r); }); await pause(beat); }
        await pause(260);
        arriving.delete(r.id);
        document.querySelectorAll(`[data-tick="${r.id}"]`).forEach(c => { c.outerHTML = statusChip(r); });
        document.querySelectorAll(`[data-tickrule="${r.id}"]`).forEach(c => { c.innerHTML = ruleHtml(r.entry); });
        document.querySelectorAll(`tr[data-arrive="${r.id}"]`).forEach(tr => tr.classList.add('is-landed'));
      }
      revealing = false;
    }
    const statusCell = (r) => arriving.has(r.id) ? tickHtml(r) : statusChip(r);
    const ruleCell = (r) => `<span data-tickrule="${r.id}">${arriving.has(r.id) ? '<span class="small bd-tick__wait">checking</span>' : ruleHtml(r.entry)}</span>`;
    const isFirst = (e) => e.decision === 'ESCALATE' && e.code === FIRST;

    async function renderDash() {
      const data = await api('GET', '/api/bank/audit'); auditRows = data.rows;
      const regs = state.registrations.filter(x => x.status !== 'draft'), live = issued(), viol = state.violations || [];
      const todo = regs.filter(x => !x.admission_status || x.admission_status === 'info_requested');
      const verifies = auditRows.filter(r => r.kind === 'verify');
      // anything that arrived since the last render is revealed check by check (oldest first)
      if (seenIds && paced()) verifies.filter(r => !seenIds.has('a' + r.id)).reverse().forEach(r => { if (!arriving.has(r.id)) { arriving.set(r.id, { step: 0 }); queueReveal(r); } });
      const vById = {}; viol.forEach(x => { if (x.audit_id) vById[x.audit_id] = x; });
      const heldOpen = verifies.filter(r => r.entry.decision === 'ESCALATE' && !decisionFor(r.id));
      const nFraud = viol.filter(x => x.failure_class === 'fraud').length, nErr = viol.filter(x => x.failure_class !== 'fraud').length;
      const pays = state.payments || [], value = pays.reduce((s, x) => s + Number(x.amount || 0), 0);
      // at a glance: the bank's whole agent channel. Totals carried forward from before the session plus this session's rows; the seam is stated
      const o = state.opening || {};
      $('bk-stats').innerHTML = [[num((o.processed || 0) + pays.length), 'Payments processed'], [gbp((o.value_gbp || 0) + value), 'Value moved'], [num(heldOpen.length), 'Awaiting a person'], [num((o.refused_fraud || 0) + nFraud), 'Refused · fraud indicator'], [num((o.refused_agent_error || 0) + nErr), 'Refused · agent error'], [num((o.agents_on_list || 0) + live.filter(x => x.status === 'active').length), 'AI agents on the list']].map(([n, l]) => `<li><b class="mono">${n}</b><span>${l}</span></li>`).join('');
      $('bd-seam').innerHTML = o.processed ? `Totals for ${esc(o.label || 'the agent channel before this session')}: <b class="mono">${num(o.processed)}</b> payments and <b class="mono">${gbp(o.value_gbp)}</b> carried forward as figures, <b class="mono">${num(pays.length)}</b> processed in this session. Every row on this console is this session's; nothing carried forward is shown as a row.` : '';
      $('bk-todo').hidden = !todo.length;
      $('bk-todo').innerHTML = todo.map(x => `<span><strong>${esc(v(x.fields, 'product', 'product_name') || x.ref)}</strong> by ${esc(v(x.fields, 'company', 'legal_name') || '')} is on the register and awaits your admission decision.</span><a class="btn btn--small" href="/bank?ref=${x.ref}">Open ${esc(x.ref)}</a>`).join('');
      // needs attention: every held instruction awaiting a person and every fraud-class refusal, newest first; agent errors never appear here
      const fraudRows = viol.filter(x => x.failure_class === 'fraud').map(x => auditRows.find(r => r.id === x.audit_id)).filter(Boolean);
      const attention = [...heldOpen, ...fraudRows].sort((a, b) => (a.ts < b.ts ? 1 : -1));
      const at = $('bd-attention-list').querySelector('tbody'); at.innerHTML = '';
      attention.slice(0, 5).forEach(r => {
        const e = r.entry, i = e.instruction || {}; const held = e.decision === 'ESCALATE', firstPay = isFirst(e);
        const action = !held ? `<span class="small">${esc(e.rule)} ${esc((e.code || '').toLowerCase().replace(/_/g, ' '))}</span> · <a href="/api/evidence/violations/${esc(String((vById[r.id] || {}).id || ''))}" target="_blank" rel="noopener">evidence</a>`
          : firstPay ? `<span class="small">first payment under the mandate: the customer confirms it in its app</span> · <a href="/customer?ref=${esc(r.subject)}">Customer dashboard</a>`
          : `<button class="btn btn--small" type="button" data-decide="release" data-audit="${r.id}">Approve and release</button> <button class="btn btn--small btn--warning" type="button" data-decide="refuse" data-audit="${r.id}">Refuse and record</button>`;
        const tr = el('tr', 'bd-log__row bd-att__row' + (held ? ' bd-att__row--held' : ' bd-att__row--fraud'), `<td class="mono small">${t(r.ts)}</td><td>${esc(agentName(r.subject))}<br><span class="mono small">${esc(r.subject || '')}</span></td><td>${esc(i.supplier_name || '')} <span class="mono small">${esc(i.payee_account_ref || '')}</span></td><td class="num mono">${gbp(i.amount)}</td><td>${statusCell(r)}</td><td class="bd-att__act">${action}</td>`);
        tr.tabIndex = 0; tr.setAttribute('role', 'button'); tr.setAttribute('aria-expanded', String(expandedAtt === r.id)); tr.dataset.arrive = r.id;
        if (seenIds && !seenIds.has('a' + r.id)) tr.classList.add('is-new');
        const open = () => { expandedAtt = expandedAtt === r.id ? null : r.id; if (expandedAtt !== r.id) pendingDecide = null; renderDash(); };
        tr.onclick = (ev) => { if (ev.target.closest('a, button')) return; open(); }; tr.onkeydown = (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); open(); } };
        at.append(tr);
        if (expandedAtt === r.id) at.append(el('tr', 'bd-detail', `<td colspan="6">${detailHtml(r, vById[r.id])}</td>`));
      });
      $('bd-attention-more').textContent = attention.length > 5 ? `and ${attention.length - 5} more in the full log` : '';
      $('bd-attention-meta').textContent = attention.length ? `${heldOpen.length} held · ${fraudRows.length} fraud indicator${fraudRows.length === 1 ? '' : 's'}` : '';
      $('bd-attention-list').hidden = !attention.length; $('bd-attention-empty').hidden = !!attention.length;
      // active agents: the bank's access dashboard for AI agents
      const lastBy = {}; verifies.forEach(r => { if (!lastBy[r.subject]) lastBy[r.subject] = r; });
      const box = $('bk-agents'); box.innerHTML = '';
      $('bd-agents-meta').textContent = `${live.filter(x => x.status === 'active').length} active`;
      live.forEach(x => {
        const ag = (x.agent_identity || {}).agent || {}, mp = x.mandate_proposed || {}, m = x.mandate || {}, ad = ((m.authorization_details || mp.authorization_details) || [{}])[0];
        const per = Number((ad.per_payment_limit || {}).amount || 0), monthly = Number((ad.monthly_limit_per_account || {}).amount || 0);
        const nv = viol.filter(y => y.passport_id === x.passport_id); const last = lastBy[x.passport_id];
        const heldN = verifies.filter(r => r.subject === x.passport_id && r.entry.decision === 'ESCALATE' && !decisionFor(r.id)).length;
        const card = el('a', 'agent-row', `<div class="agent-row__head"><span class="agent-row__name">${esc(ag.name || x.passport_id)}</span>${tag(x.status)}</div>
          <div class="small agent-row__counts">${esc((mp.customer || {}).legal_name || '')} · <b class="mono">${x.payments || 0}</b> processed · <b class="mono">${heldN}</b> held · <b class="mono">${nv.length}</b> refused${nv.filter(y => y.failure_class === 'fraud').length ? ` <span class="bad">(${nv.filter(y => y.failure_class === 'fraud').length} fraud)</span>` : ''}</div>`);
        card.href = x.synthetic ? '#bk-agents-pane' : `/bank?passport=${x.passport_id}`; void per; void last;
        box.append(card);
      });
      if (!live.length) box.append(el('p', 'small', 'No AI agent holds a passport on this bank yet.'));
      // recent activity (the full log one click away)
      renderLog(verifies, viol);
      // admissions, register, supervisory access
      rows('bk-products', [
        ...regs.filter(x => x.admission_status && x.admission_status !== 'declined' && x.admission_status !== 'info_requested').map(x => { const pr = (state.products || []).find(y => y.registration_id === x.id) || { passports: [] }; return { cells: [`<a href="/bank?ref=${x.ref}">${esc(v(x.fields, 'product', 'product_name') || x.ref)}</a> ${levelTag(v(x.fields, 'assurance_evidence', 'level'))}`, esc(v(x.fields, 'company', 'legal_name') || ''), holdOf(x) != null ? gbp(holdOf(x)) : '—', String(pr.passports.length), admissionTag(x)] }; }),
        ...(state.register || []).filter(m => m.bank).map(m => ({ cells: [`${esc(m.product)} ${levelTag(m.assurance_level)}`, esc(m.provider), gbp(m.bank.hold_above_gbp), '0', tag('admitted', 'admitted')] })),
      ], 5, 'No product admitted yet.');
      rows('bk-register', [
        ...regs.map(x => ({ cells: [`<a href="/bank?ref=${x.ref}">${esc(v(x.fields, 'product', 'product_name') || x.ref)}</a>`, esc(v(x.fields, 'company', 'legal_name') || ''), levelTag(v(x.fields, 'assurance_evidence', 'level')), d(x.submitted_at), admissionTag(x)] })),
        ...(state.register || []).map(m => ({ cells: [esc(m.product), esc(m.provider), levelTag(m.assurance_level), d(m.registered), m.bank ? tag('admitted', 'admitted') : `<span class="small">${m.status === 'active' ? 'not on your list' : esc(m.status)}</span>`] })),
      ], 5);
      renderTrail(data);
      const ev = $('bk-evidence'); ev.innerHTML = '';
      live.filter(x => !x.synthetic).forEach(x => ev.append(el('li', null, `<span>Passport <span class="mono">${esc(x.passport_id)}</span>, the complete bundle</span><a href="/api/evidence/passports/${esc(x.passport_id)}" target="_blank" rel="noopener">Export</a>`)));
      viol.filter(x => !x.synthetic).slice(0, 5).forEach(x => ev.append(el('li', null, `<span>Refusal #${x.id}, ${esc(x.rule)} at ${t(x.ts)}</span><a href="/api/evidence/violations/${x.id}" target="_blank" rel="noopener">Export</a>`)));
      if (!live.length && !viol.length) ev.append(el('li', 'small', 'Nothing to export yet.'));
      seenIds = new Set([...verifies.map(r => 'a' + r.id), ...viol.map(x => 'v' + x.id)]);
      $('bd-legend').textContent = LEGEND_LINE;
      renderStats(verifies, viol, live);
      $('bd-live-label').textContent = 'Live · ' + t(new Date().toISOString());
    }
    // statistics: this session's instructions per agent, and the carried-forward totals as one clearly separate line
    let volChart = null;
    function renderStats(verifies, viol, live) {
      const pays = state.payments || []; const value = pays.reduce((s, x) => s + Number(x.amount || 0), 0); const o = state.opening || {};
      const held = verifies.filter(r => r.entry.decision === 'ESCALATE').length, nFraud = viol.filter(x => x.failure_class === 'fraud').length, nErr = viol.filter(x => x.failure_class !== 'fraud').length;
      $('bd-stats-meta').textContent = `this session · ${verifies.length} instruction${verifies.length === 1 ? '' : 's'}`;
      $('bd-stats-totals').innerHTML = [[num(verifies.length), 'Instructions'], [num(pays.length), 'Processed'], [gbp(value), 'Value processed'], [num(held), 'Held'], [num(nFraud), 'Refused, fraud indicator'], [num(nErr), 'Refused, agent error']].map(([n, l]) => `<li><b class="mono">${n}</b><span>${l}</span></li>`).join('');
      // volume per minute across the session, from the first instruction to now
      const minute = (iso) => iso.slice(0, 16);
      const first = verifies.length ? verifies[verifies.length - 1].ts : (pays.length ? pays[pays.length - 1].ts : new Date().toISOString());
      const labels = [], data = []; const start = new Date(minute(first) + ':00Z'), now = new Date(); const span = Math.max(1, Math.min(120, Math.round((now - start) / 60000) + 1));
      const byMin = {}; pays.forEach(x => { const k = minute(x.ts); byMin[k] = (byMin[k] || 0) + Number(x.amount || 0); });
      for (let i = 0; i < span; i++) { const dt = new Date(start.getTime() + i * 60000); const k = dt.toISOString().slice(0, 16); labels.push(k.slice(11)); data.push(byMin[k] || 0); }
      if (window.Chart && $('chart-volume')) {
        if (!volChart) {
          Chart.defaults.font.family = getComputedStyle(document.body).fontFamily; Chart.defaults.font.size = 13; Chart.defaults.color = '#505a5f';
          volChart = new Chart($('chart-volume'), { type: 'bar', data: { labels, datasets: [{ data, backgroundColor: '#0f6b73', borderWidth: 0, maxBarThickness: 28 }] },
            options: { animation: { duration: 300 }, responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => gbp(c.parsed.y) } } },
              scales: { x: { grid: { display: false }, border: { color: '#b1b4b6' }, ticks: { color: '#0b0c0c', maxTicksLimit: 12 } }, y: { beginAtZero: true, grid: { color: '#e5e7e8' }, border: { display: false }, ticks: { color: '#505a5f', callback: (v_) => gbp(v_) } } } } });
        } else { volChart.data.labels = labels; volChart.data.datasets[0].data = data; volChart.update('none'); }
      }
      const tb = $('bd-stats-agents').querySelector('tbody'); tb.innerHTML = '';
      live.forEach(x => {
        const ag = (x.agent_identity || {}).agent || {}; const mine = pays.filter(y => y.passport_id === x.passport_id); const nv = viol.filter(y => y.passport_id === x.passport_id);
        tb.append(el('tr', null, `<td>${esc(ag.name || x.passport_id)}<br><span class="mono small">${esc(x.passport_id)} · this session</span></td><td class="num mono">${mine.length}</td><td class="num mono">${gbp(mine.reduce((s, y) => s + Number(y.amount || 0), 0))}</td><td class="num mono">${verifies.filter(r => r.subject === x.passport_id && r.entry.decision === 'ESCALATE').length}</td><td class="num mono">${nv.filter(y => y.failure_class === 'fraud').length}</td><td class="num mono">${nv.filter(y => y.failure_class !== 'fraud').length}</td>`));
      });
      if (!live.length) tb.append(el('tr', null, '<td colspan="6" class="empty-row">No AI agent holds a passport on this bank yet.</td>'));
      if (o.processed) tb.append(el('tr', 'bd-stats__carry', `<td>Other AI agents on the bank's list, ${num(o.agents_on_list)} of them<br><span class="small">carried forward as totals, ${esc((o.period || {}).from || '')} to the start of this session · no rows</span></td><td class="num mono">${num(o.processed)}</td><td class="num mono">${gbp(o.value_gbp)}</td><td class="num mono">${num(o.held)}</td><td class="num mono">${num(o.refused_fraud)}</td><td class="num mono">${num(o.refused_agent_error)}</td>`));
    }
    // the evidence trail: every chain entry, verifications replayable from their recorded inputs
    let trailRun = 0, trailSame = 0, trailBound = false; const trailState = {};
    async function replayOne(id) { const rp = await api('POST', `/api/audit/${id}/replay`); trailRun++; if (rp.identical) trailSame++; trailState[id] = rp.identical ? 'same' : 'differs'; }
    function renderTrail(data) {
      const tb = $('au-table').querySelector('tbody'); tb.innerHTML = '';
      $('au-summary').innerHTML = `<b>${data.rows.length}</b> entries · chain ${data.chain.ok ? '<b class="ok">intact</b>' : `<b class="bad">broken at #${data.chain.broken_at}</b>`} · head <span class="mono">${esc((data.chain.head || '').slice(0, 12))}</span>${trailRun ? ` · <b class="${trailSame === trailRun ? 'ok' : 'bad'}">${trailSame} of ${trailRun}</b> replayed identically` : ''}`;
      const subjects = [...new Set(data.rows.filter(r => r.subject && r.subject.startsWith('AP-')).map(r => r.subject))];
      $('au-evidence').innerHTML = subjects.map(s => `<a href="/api/evidence/passports/${esc(s)}" target="_blank" rel="noopener">Export the evidence bundle for ${esc(s)}</a>`).join(' · ');
      data.rows.slice(0, 200).forEach(r => tb.append(el('tr', null, `<td class="mono small">${t(r.ts)}</td><td>${plainEvent(r)}</td><td class="mono small">${esc(r.subject || '')}</td><td class="small" id="au-r-${r.id}"><span class="hash">#${r.id} ${esc(r.hash.slice(0, 10))}</span>${r.receipt ? ' · receipt' : ''}${r.kind === 'verify' && !r.synthetic ? (trailState[r.id] ? ` · <span class="${trailState[r.id] === 'same' ? 'ok' : 'bad'}">${trailState[r.id] === 'same' ? 'replayed identically' : 'REPLAY DIFFERS'}</span>` : ` · <button class="link" data-replay="${r.id}" type="button">replay</button>`) : ''}</td>`)));
      if (!trailBound) {
        trailBound = true;
        tb.addEventListener('click', async (e) => { const b = e.target.closest('[data-replay]'); if (b) { await replayOne(+b.dataset.replay); renderTrail({ rows: auditRows, chain: data.chain }); } });
        $('btn-replay-all').onclick = async () => { for (const r of auditRows.filter(x => x.kind === 'verify' && !x.synthetic)) if (!trailState[r.id]) await replayOne(r.id); $('replay-note').textContent = trailRun ? `${trailSame} of ${trailRun} replayed identically` : 'no verifications yet'; renderTrail({ rows: auditRows, chain: data.chain }); };
      }
    }
    function renderLog(verifies, viol) {
      const tb = $('bd-log').querySelector('tbody'); tb.innerHTML = '';
      const vById = {}; viol.forEach(x => { if (x.audit_id) vById[x.audit_id] = x; });
      const shown = verifies.filter(r => logFilter === 'all' || r.entry.decision === logFilter);
      const limit = logAll ? 200 : 6;
      $('bd-log-meta').textContent = `${verifies.length} instructions`;
      $('bd-log-title').textContent = logAll ? 'Transaction log' : 'Recent activity';
      $('bd-log-toggle').textContent = logAll ? 'Recent activity only' : `Full log (${verifies.length})`;
      $('bd-log-hint').hidden = logAll; $('bd-recent').classList.toggle('bd-col--full', logAll);
      shown.slice(0, limit).forEach(r => {
        const e = r.entry, i = e.instruction || {};
        const tr = el('tr', 'bd-log__row', `<td class="mono small">${t(r.ts)}</td><td>${statusCell(r)}</td><td>${esc(i.supplier_name || '')} <span class="mono small">${esc(i.payee_account_ref || '')}</span><br><span class="mono small">${esc(r.subject || '')}</span></td><td class="num mono">${gbp(i.amount)}</td><td>${ruleCell(r)}</td><td class="small"><span class="hash">#${r.id} ${esc(r.hash.slice(0, 10))}</span>${r.receipt ? ' · receipt' : ''}</td>`);
        tr.tabIndex = 0; tr.setAttribute('role', 'button'); tr.setAttribute('aria-expanded', String(expandedId === r.id)); tr.dataset.arrive = r.id;
        if (seenIds && !seenIds.has('a' + r.id)) tr.classList.add('is-new');
        const open = () => { expandedId = expandedId === r.id ? null : r.id; renderLog(verifies, viol); };
        tr.onclick = open; tr.onkeydown = (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); open(); } };
        tb.append(tr);
        if (expandedId === r.id) tb.append(el('tr', 'bd-detail', `<td colspan="6">${detailHtml(r, vById[r.id])}</td>`));
      });
      if (!shown.length) tb.append(el('tr', null, `<td colspan="6" class="empty-row">${verifies.length ? 'Nothing in this filter.' : 'No instruction yet. Turn on simulated traffic or run the Action Terminal.'}</td>`));
      else if (!logAll && shown.length > limit) tb.append(el('tr', 'bd-log__more', `<td colspan="6" class="small">${shown.length - limit} earlier instruction${shown.length - limit === 1 ? '' : 's'} in the <button class="link" type="button" data-log-all>full log</button></td>`));
    }
    $('bd-log-toggle').onclick = () => { logAll = !logAll; renderLog(auditRows.filter(r => r.kind === 'verify'), state.violations || []); };
    function heldHtml(r) {
      const e = r.entry, i = e.instruction || {}; const x = issued().find(y => y.passport_id === r.subject) || {};
      const ad = (((x.mandate || x.mandate_proposed || {}).authorization_details) || [{}])[0]; const hold = (((x.admission || {}).condition || {}).hold_above || {}).amount;
      const ap = (x.mandate || {}).signed_by || (x.mandate_proposed || {}).authorising_officer || {}; const dd = decisionFor(r.id); const firstPay = isFirst(e);
      const kv = (pairs) => `<dl class="kv">${pairs.map(([k, val]) => `<div><dt>${k}</dt><dd>${val}</dd></div>`).join('')}</dl>`;
      const armed = pendingDecide && pendingDecide.audit === r.id ? pendingDecide.decision : null;
      const confirmBox = armed ? `<div class="bd-confirm" role="group" aria-label="Confirm the decision"><p><strong>${armed === 'release' ? 'Release' : 'Refuse'} ${gbp(i.amount)} to ${esc(i.supplier_name || '')}</strong> <span class="mono small">${esc(i.payee_account_ref || '')}</span>${i.invoice_ref ? ` · invoice <span class="mono">${esc(i.invoice_ref)}</span>` : ''}.<br>Decided for ${esc(ap.name || '')}, ${esc(ap.role || '')}, the customer's named approver. Recorded as <strong>${esc(who())}</strong> at ${t(new Date().toISOString())}, signed by the bank into the evidence chain${armed === 'release' ? '; the payment executes' : '; nothing moves'}.</p><div class="actions"><button class="btn btn--small${armed === 'refuse' ? ' btn--warning' : ''}" type="button" data-confirm="${armed}" data-audit="${r.id}">${armed === 'release' ? 'Confirm and release the payment' : 'Confirm and record the refusal'}</button><button class="btn btn--secondary btn--small" type="button" data-cancel-decide="${r.id}">Cancel</button></div></div>` : '';
      const why = firstPay ? `${gbp(i.amount)} is inside the mandate and the hold condition; it is the first payment under mandate version ${esc(String((x.mandate || {}).version || 1))}, so the verifier returned ESCALATE at R.9 for the customer's own confirmation` : `${gbp(i.amount)} is inside the mandate (up to ${gbp((ad.per_payment_limit || {}).amount)} a payment) and above the bank's hold condition of ${gbp(hold)}; the verifier returned ESCALATE at R.9`;
      const whoDecides = firstPay ? `${esc(ap.name || '')}, ${esc(ap.role || '')}, in the customer's own banking app. The bank does not decide this one.` : `${esc(ap.name || '')}, ${esc(ap.role || '')} (the customer's named approver), recorded by ${esc(who())}`;
      const decision = dd ? `<b>${dd.entry.outcome === 'RELEASED' ? (firstPay ? 'Confirmed' : 'Released') : 'Refused'}</b> at ${t(dd.ts)} by ${esc(dd.entry.officer)} · ${esc(dd.entry.reason)} · chain entry <span class="mono small">#${dd.id} ${esc(dd.hash.slice(0, 10))}</span>${dd.receipt ? ' · receipt signed by the bank' : ''}`
        : firstPay ? `<span class="small">awaiting the customer · <a href="/customer?ref=${esc(r.subject)}">open the customer dashboard</a></span>`
        : armed ? '<span class="small">confirm below</span>' : `<span class="bd-hold__act"><button class="btn btn--small" type="button" data-decide="release" data-audit="${r.id}">Approve and release</button> <button class="btn btn--small btn--warning" type="button" data-decide="refuse" data-audit="${r.id}">Refuse and record</button> <span class="small">either way the chain records who decided, when, and on what</span></span>`;
      return `<div class="bd-hold"><h3 class="h4">${firstPay ? 'Held for the customer: first payment under the mandate' : 'Held for a person'}</h3>${kv([['Why', why], ['Mandate', `${esc(ap.name || '')} signed version ${esc(String((x.mandate || {}).version || 1))} · up to ${gbp((ad.per_payment_limit || {}).amount)} a payment · ${gbp((ad.monthly_limit_per_account || {}).amount)} per account in 30 days · ${(ad.supplier_allowlist || []).length} payee accounts`], ['Who decides', whoDecides], ['Decision', decision]])}${confirmBox}</div>`;
    }
    async function decideHeld(auditId, decision) {
      let out = null;
      try { out = await api('POST', `/api/audit/${auditId}/decide`, { decision }); } catch (e) { alert(e.message); }
      pendingDecide = null; expandedAtt = null;
      if (out) { const done = $('bd-attention-done'); done.hidden = false; done.innerHTML = `<b>${out.outcome === 'RELEASED' ? 'Released' : 'Refused'}</b> by ${esc(out.officer)} for ${esc((out.approver || {}).name || '')} · chain entry <span class="mono">#${out.audit_id} ${esc(out.hash.slice(0, 10))}</span>, receipt signed by the bank${out.settlement ? ` · ${esc(out.settlement.rail_reason || 'executed')}` : ' · nothing moved'}. Now in recent activity, the statistics and the evidence trail.`; setTimeout(() => { done.hidden = true; }, 12000); }
      await refresh();
    }
    document.addEventListener('click', (ev) => {
      const arm = ev.target.closest('[data-decide]'); if (arm) { ev.stopPropagation(); pendingDecide = { audit: +arm.dataset.audit, decision: arm.dataset.decide }; expandedAtt = +arm.dataset.audit; renderDash().then(() => { const c = document.querySelector('.bd-confirm'); if (c) { const rc = c.getBoundingClientRect(); window.scrollBy({ top: rc.top - window.innerHeight / 2 + rc.height / 2, behavior: 'smooth' }); } }); return; }
      const go = ev.target.closest('[data-confirm]'); if (go && !go.disabled) { ev.stopPropagation(); go.disabled = true; decideHeld(+go.dataset.audit, go.dataset.confirm); return; }
      const cancel = ev.target.closest('[data-cancel-decide]'); if (cancel) { ev.stopPropagation(); pendingDecide = null; renderDash(); return; }
      const all = ev.target.closest('[data-log-all]'); if (all) { ev.stopPropagation(); logAll = true; renderLog(auditRows.filter(r => r.kind === 'verify'), state.violations || []); }
    });
    function detailHtml(r, vio) {
      const e = r.entry, i = e.instruction || {}; const env = e.presented_envelope || {};
      const trace = (e.trace || []).map(s => `<li class="${s.ok ? 'ok' : (e.decision === 'ESCALATE' && s.rule === e.rule ? 'hold' : 'fail')}"><b>${esc(s.rule)}</b> ${esc(s.title)}<span>${esc(s.note)}</span></li>`).join('');
      const kv = (pairs) => `<dl class="kv">${pairs.map(([k, val]) => `<div><dt>${k}</dt><dd>${val}</dd></div>`).join('')}</dl>`;
      return `<div class="bd-detail__grid">
        <div><h3 class="h4">The instruction, as signed</h3>${kv([['Passport', `<span class="mono">${esc(i.passport_id || '')}</span> · list status ${esc(e.passport_status || e.registry_status || '')}`], ['Action', esc(i.action_type || '')], ['Payee', `${esc(i.supplier_name || '')} · <span class="mono">${esc(i.payee_account_ref || '')}</span>`], ['Amount', `${gbp(i.amount)} ${esc(i.currency || '')}`], ['Invoice', esc(i.invoice_ref || '—')], ['Nonce', `<span class="mono small">${esc(i.nonce || '—')}</span>${e.nonce_seen_before ? ' <span class="small">already spent: this instruction had been accepted before</span>' : ''}`], ['Instruction hash', `<span class="mono small" title="${esc(e.instruction_hash || '')}">${esc((e.instruction_hash || '').slice(0, 16))}…</span>`], ['30-day total before', gbp(e.ledger_total_before)]])}${vio && vio.evidence ? `<h3 class="h4">What the AI agent read</h3>${kv([['Invoice', esc(vio.evidence.invoice)], ['Declared before reading', `<span class="mono">${esc((vio.evidence.intent || {}).declared_payee || '—')}</span>`], ['Attempted after reading', `<span class="mono wrong">${esc(vio.evidence.instruction_payee || '')}</span>`], ['Read by', esc(modeLabel(vio.evidence.extraction_mode))]])}` : ''}</div>
        <div><h3 class="h4">The nine checks, in order</h3><ol class="bd-trace">${trace}</ol><p class="bd-verdict bd-verdict--${e.decision}${e.failure_class === 'agent_error' ? ' bd-verdict--quiet' : ''}"><b>${esc(e.decision)}</b> ${esc(e.rule)} · ${esc(e.code)} <span>${esc(e.reason)}</span>${e.decision === 'DENY' ? `<span>${classTag(e.failure_class)} ${esc(((state.failure_classes || {})[classId(e.failure_class)] || {}).note || '')}</span>` : ''}</p>${e.decision === 'ESCALATE' ? heldHtml(r) : ''}</div>
        <div><h3 class="h4">Proof</h3>${kv([['Chain entry', `#${r.id} <span class="mono small" title="${esc(r.hash)}">${esc(r.hash.slice(0, 16))}…</span>`], ['Previous', `<span class="mono small" title="${esc(r.prev_hash)}">${esc(r.prev_hash.slice(0, 16))}…</span>`], ['Rule pack', `<span class="mono">${esc(e.rule_pack || '')}</span>`], ['Receipt', r.receipt ? `signed by the bank · <span class="mono small">${esc(r.receipt.slice(0, 40))}…</span>` : 'none'], ['Envelope', `admission ${env.admission ? '✓' : '✗'} · agent identity ${env.agent_identity ? '✓' : '✗'} · mandate ${env.mandate ? '✓' : '✗'}`]])}
          <div class="actions">${r.synthetic ? '' : `<button class="btn btn--secondary btn--small" type="button" data-replay="${r.id}">Replay this decision</button>`}${r.synthetic ? '' : vio ? `<a class="btn btn--secondary btn--small" href="/api/evidence/violations/${vio.id}" target="_blank" rel="noopener">Export the evidence bundle</a>` : `<a class="btn btn--secondary btn--small" href="/api/evidence/passports/${esc(r.subject)}" target="_blank" rel="noopener">Export the passport bundle</a>`}<span class="actions__note" id="bd-replay-${r.id}"></span></div></div>
      </div>`;
    }
    document.querySelectorAll('.bd-filter').forEach(bt => { bt.onclick = () => { logFilter = bt.dataset.filter; document.querySelectorAll('.bd-filter').forEach(x => x.setAttribute('aria-pressed', String(x === bt))); renderLog(auditRows.filter(r => r.kind === 'verify'), state.violations || []); }; });
    $('bd-log').addEventListener('click', async (ev) => { const b = ev.target.closest('[data-replay]'); if (!b) return; ev.stopPropagation(); const id = +b.dataset.replay; const rp = await api('POST', `/api/audit/${id}/replay`); $(`bd-replay-${id}`).innerHTML = rp.identical ? '<b class="ok">Replayed identically</b> from the stored inputs' : '<b class="bad">Replay differs</b>'; });
    // simulated traffic: the customer's AI agent keeps paying invoices; most are fine, a few are not. Every instruction is a real
    // verification with a chain entry; the mix is deliberately quiet so the rows on screen stay few
    async function simTick() {
      if (!$('bd-sim').checked) return;
      const pass = issued().find(x => x.status === 'active' && x.mandate_signed); if (!pass) return;
      const ad = ((pass.mandate || {}).authorization_details || [{}])[0]; const sup = ad.supplier_allowlist || []; if (!sup.length) return;
      const roll = Math.random(); const pick = sup[Math.floor(Math.random() * sup.length)];
      const inv = () => 'INV-' + (9100 + Math.floor(Math.random() * 800));
      try {
        if (roll < 0.72) await api('POST', '/api/agent/act', { passport_id: pass.passport_id, supplier_name: pick.name, payee_account_ref: pick.account_ref, amount: 150 + Math.floor(Math.random() * 38) * 100, invoice_ref: inv() });
        else if (roll < 0.84) await api('POST', '/api/agent/act', { passport_id: pass.passport_id, supplier_name: pick.name, payee_account_ref: pick.account_ref, amount: 10500 + Math.floor(Math.random() * 20) * 100, invoice_ref: inv() });
        else if (roll < 0.90) await api('POST', '/api/agent/act', { passport_id: pass.passport_id, supplier_name: pick.name, payee_account_ref: pick.account_ref, amount: 5200 + Math.floor(Math.random() * 30) * 100, invoice_ref: inv() });
        else if (roll < 0.96) await api('POST', '/api/agent/invoice', { passport_id: pass.passport_id, invoice_id: 'INV-9001-poisoned' });
        else await api('POST', '/api/agent/act', { passport_id: pass.passport_id, supplier_name: pick.name, payee_account_ref: pick.account_ref, amount: 900, invoice_ref: inv(), signer: 'rogue' });
      } catch (e) { /* the log shows what happened */ }
      await refresh();
    }
    // the bank dashboard is still: no polling, no simulated traffic; it re-renders only after an action on it
    void timer; void simTimer; void simTick;
    function renderCase() {
      $('bk-ref').textContent = a.ref;
      $('bk-status').innerHTML = admissionTag(a);
      const f = a.fields;
      $('bk-summary').innerHTML = [
        ['Provider', `${esc(v(f, 'company', 'legal_name'))} · Companies House <span class="mono">${esc(v(f, 'company', 'companies_house_number'))}</span> · ${esc(v(f, 'company', 'website'))}`],
        ['Accountable principal', `${esc(v(f, 'principal', 'name'))}, ${esc(v(f, 'principal', 'role'))} · declaration <span class="mono">${esc(v(f, 'principal', 'declaration_ref'))}</span> · accountable for the accuracy of the filing`],
        ['Insurance', `${esc(v(f, 'insurance', 'insurer'))} · policy <span class="mono">${esc(v(f, 'insurance', 'policy_ref'))}</span> · cover ${gbp(v(f, 'insurance', 'cover_gbp'))} · in force until ${esc(v(f, 'insurance', 'expires'))}`],
        ['AI product', `<strong>${esc(v(f, 'product', 'product_name'))}</strong> <span class="mono">${esc(v(f, 'product', 'product_id'))}</span> · release ${esc(v(f, 'product', 'release'))} · ${esc(v(f, 'product', 'model_provider'))} <span class="mono">${esc(v(f, 'product', 'model_version'))}</span> · <a href="${esc(v(f, 'product', 'documentation_url'))}">documentation</a>`],
        ['Independent Assurance Evidence', `${levelTag(v(f, 'assurance_evidence', 'level'))} ${esc(v(f, 'assurance_evidence', 'issuer'))} · <span class="mono">${esc(v(f, 'assurance_evidence', 'reference'))}</span> · ${esc(v(f, 'assurance_evidence', 'date'))} · use case <span class="mono">${esc(v(f, 'assurance_evidence', 'use_case'))}</span><span class="sub">${esc(v(f, 'assurance_evidence', 'summary'))} · <a href="${esc(v(f, 'assurance_evidence', 'report_url'))}">report</a> · the level is declared by the provider with its evidence; this bank admits at ${esc((LEVELS[(state.policy || {}).min_assurance_level_for_admission] || ['?'])[0]).toLowerCase()} or above</span>`],
        ['Registered use', `<strong>${esc((((state.payment_intents || []).find(x => x.id === v(f, 'intended_use', 'payment_intent')) || {}).label) || v(f, 'intended_use', 'payment_intent') || 'no intent')}</strong> · ${esc(v(f, 'intended_use', 'description'))} · no customer named: each customer writes its own mandate within your ceilings`],
        ['UK data protection', `${v(f, 'data_protection', 'uk_gdpr_compliant') === 'yes' ? '<span class="tag tag--green">declared</span>' : '<span class="tag tag--red">not declared</span>'} UK GDPR and DPA 2018 · ICO <span class="mono">${esc(v(f, 'data_protection', 'ico_registration') || 'none')}</span> · personal data retained ${esc((((state.retention_periods || []).find(x => x.id === v(f, 'data_protection', 'retention_period')) || {}).label || 'not declared').toLowerCase())}${v(f, 'data_protection', 'dpia_reference') ? ` · DPIA <span class="mono">${esc(v(f, 'data_protection', 'dpia_reference'))}</span>` : ''} · declared by the provider; the register verifies nothing about compliance`],
        ['Register receipt', a.registration_jwt ? `signed by the register <span class="mono small">${esc(a.registration_jwt.slice(0, 24))}…</span> · filed ${d(a.submitted_at)}` : '—'],
      ].map(([k, val]) => `<div><dt>${k}</dt><dd>${val}</dd></div>`).join('');
      const pol = state.policy || {};
      const lv = (pol.assurance_levels || []).find(x => x.id === v(f, 'assurance_evidence', 'level')) || { ceiling_factor: 1, label: 'no level' };
      $('bk-ceilings').innerHTML = `per payment ≤ ${gbp(pol.per_payment_ceiling_gbp * lv.ceiling_factor)} · per account in 30 days ≤ ${gbp(pol.monthly_per_account_ceiling_gbp * lv.ceiling_factor)} · up to ${pol.velocity_ceiling_per_day} payments a day · expiry ≤ ${esc(pol.max_validity)} · actions ${esc((pol.action_types || []).join(', '))}<br><span class="small">policy ceilings scaled by the declared assurance level (${esc(lv.label.toLowerCase())}, ×${lv.ceiling_factor}); each customer mandate is further capped by its account type: ${Object.values(pol.account_tiers || {}).map(tr => `${esc(tr.label)} ${gbp(tr.per_payment_gbp)}`).join(' · ')}</span>`;
      checksTable('bk-checks', a.checks);
      $('bk-filenote').value = a.file_note || '';
      $('btn-bk-prefill').onclick = () => { $('bk-context').hidden = false; $('bk-context').scrollIntoView({ behavior: 'smooth', block: 'center' }); };
      $('btn-bk-prefill-cancel').onclick = () => { $('bk-context').hidden = true; };
      $('btn-bk-prefill-go').onclick = () => { $('bk-context').hidden = true; $('bk-condition').value = pol.hold_above_gbp || 5000; $('bk-condition').dataset.touched = '1'; if (!$('bk-officer-note').value.trim()) $('bk-officer-note').value = `Six filing checks pass. Independent Assurance Evidence covers invoice payment. Admitted with the ${gbp(pol.hold_above_gbp || 5000)} hold condition.`; };
      if (a.review) renderReview(a.review); else if (!a._reviewing) { a._reviewing = true; runReview(true); }
      $('bk-decide').hidden = !(!a.admission_status || a.admission_status === 'info_requested' || a.admission_status === 'declined');
      renderProduct();
    }
    function renderProduct() {
      const box = $('bk-product'); const ok = a && a.admission_status && !['declined', 'info_requested'].includes(a.admission_status); box.hidden = !ok; if (!ok) return;
      const m = (state.products || []).find(x => x.registration_id === a.id) || { passports: [] };
      const ms = a.admission_status;
      $('pd-status').innerHTML = admissionTag(a);
      const pol = state.policy || {};
      $('pd-summary').innerHTML = [['Product', `<strong>${esc(m.product_name || '')}</strong> <span class="mono">${esc(m.product_id || '')}</span> · ${esc(m.provider || '')}`], ['Admitted', `${d(a.admitted_at)} by ${esc(a.officer || '')}`], ['Ceilings', `per payment ≤ ${gbp(pol.per_payment_ceiling_gbp)} · per account in 30 days ≤ ${gbp(pol.monthly_per_account_ceiling_gbp)} · expiry ≤ ${esc(pol.max_validity)}`], ['Hold condition', `hold instructions above ${gbp(holdOf(a))}`], ['Officer note', esc(a.officer_note || '')]].map(([k, val]) => `<div><dt>${k}</dt><dd>${val}</dd></div>`).join('');
      $('btn-pd-suspend').hidden = ms !== 'admitted'; $('btn-pd-reinstate').hidden = ms !== 'suspended'; $('btn-pd-revoke').hidden = ms === 'revoked';
      const ul = $('pd-passports'); ul.innerHTML = '';
      const mine = issued().filter(x => x.registration_id === a.id);
      mine.forEach(x => ul.append(el('li', null, `<a href="/bank?passport=${x.passport_id}" class="mono">${esc(x.passport_id)}</a> ${tag(x.status)} <span class="small">${esc(((x.agent_identity || {}).agent || {}).name || '')} · ${esc(((x.mandate_proposed || {}).customer || {}).legal_name || '')}</span>`)));
      if (!mine.length) ul.append(el('li', 'small', 'None yet: an AI agent appears here when a customer chooses this product and signs its mandate.'));
    }
    async function productLife(status) {
      const reason = $('pd-reason').value.trim(); $('pd-error').hidden = true;
      try { await api('POST', `/api/registrations/${a.id}/admission/status`, { status, reason }); $('pd-reason').value = ''; await refresh(); }
      catch (e) { $('pd-error').textContent = e.message; $('pd-error').hidden = false; }
    }
    $('btn-pd-suspend').onclick = () => productLife('suspended');
    $('btn-pd-reinstate').onclick = () => productLife('active');
    $('btn-pd-revoke').onclick = () => productLife('revoked');

    function renderAgent() {
      const ag = (p.agent_identity || {}).agent || {}, mp = p.mandate_proposed || {};
      $('ag-meta').innerHTML = `<strong>${esc(ag.name || '')}</strong> · customer ${esc((mp.customer || {}).legal_name || '')} · on ${esc(ag.product_name || '')} <span class="mono">${esc(ag.model_version || '')}</span> by ${esc(ag.provider || '')}, register <a href="/bank?ref=${esc(a.ref)}" class="mono">${esc(a.ref)}</a> · issued ${d(p.issued_at)} when the customer signed its mandate`;
      $('btn-evidence').href = `/api/evidence/passports/${p.passport_id}`;
      renderPassport(p);
    }
    function renderIncidents() {
      const inc = $('bk-incidents'); inc.innerHTML = '';
      const mine = (state.incidents || []).filter(i => !p || i.subject === p.passport_id);
      mine.forEach(i => inc.append(el('li', null, `<time>${t(i.ts)}</time><span>${tag('revoked', 'Incident')} <a href="/bank?passport=${esc(i.subject)}" class="mono">${esc(i.subject)}</a> ${esc(i.entry.event)}: ${esc(i.entry.reason)} · last refusal ${esc(i.entry.last_rule)} ${esc(i.entry.last_code)} · evidence #${i.id} <span class="mono small">${esc(i.hash.slice(0, 12))}</span></span>`)));
      if (!mine.length) inc.append(el('li', 'log__empty', 'No incidents.'));
    }
    function renderHistory() {
      const hist = $('bk-history'); hist.innerHTML = '';
      if (!a) return;
      const lines = [];
      if (a.submitted_at) lines.push([a.submitted_at, `${a.ref} filed on the register by the provider; accountable principal declared it accurate; checks F.1 to F.6 recorded; receipt signed by the register.`]);
      if (a.officer_note) lines.push([a.admitted_at || a.submitted_at, `${a.officer}: ${String(a.admission_status || '').replace('_', ' ')}. “${a.officer_note}”`]);
      if (p && p.mandate_signed_at) lines.push([p.mandate_signed_at, `${(p.mandate.signed_by || {}).name}, ${(p.mandate.signed_by || {}).role} (customer): wrote and signed the mandate in the bank's app; within the ceilings. Passport issued.`]);
      (p ? p.history : []).forEach(h => lines.push([h.ts, `${h.officer}: ${h.from ? h.from + ' → ' : ''}${h.to}. ${h.reason}`]));
      lines.sort((x, y) => x[0] < y[0] ? -1 : 1).reverse().forEach(([ts, txt]) => hist.append(el('li', null, `<time>${t(ts)}</time><span>${esc(txt)}</span>`)));
      if (!lines.length) hist.append(el('li', 'log__empty', 'Nothing yet.'));
    }

    function renderReview(r) {
      const ol = $('review'); ol.hidden = false; ol.innerHTML = '';
      const kv = (o) => `<dl class="kv">${Object.entries(o).map(([k, v_]) => `<div><dt>${esc(k.replace(/_/g, ' '))}</dt><dd>${Array.isArray(v_) ? v_.map(esc).join('<br>') : esc(String(v_ ?? '—'))}</dd></div>`).join('')}</dl>`;
      for (const st of r.steps) {
        let body = '', stt = 'done', badge = '';
        if (st.id === 'filing') body = `<p class="small">The provider filed</p>${kv(st.data.provider_filed || {})}<p class="small">The register says</p>${kv(st.data.register_says || {})}<p class="small">The bank decides</p>${kv(st.data.bank_decides || {})}<p class="small">${esc(st.data.registration || '')}</p>`;
        if (st.id === 'rule_map') { badge = `<span class="tag tag--blue">${esc(r.assistant)}</span> <span class="mono small">${esc(st.data.rule_pack)}</span>`; body = `<table class="rulemap"><thead><tr><th>Rule</th><th>Requirement</th><th>Evidence</th><th>Result</th></tr></thead><tbody>${st.data.rules.map(x => `<tr><td>${esc(x.id)}</td><td>${esc(x.title)} <span class="tag tag--${x.status === 'CURRENT' ? 'green' : 'grey'}">${esc(x.status)}</span></td><td>${x.evidence ? `<span class="mono small">${esc(String(x.evidence.value))}</span>` : '<span class="tag tag--red">uncovered</span>'}</td><td>${x.result === 'pass' ? '<span class="tag tag--green">Pass</span>' : '<span class="tag tag--amber">Flag</span>'}</td></tr>`).join('')}</tbody></table>${st.data.uncovered.length ? `<p class="error">Uncovered: ${esc(st.data.uncovered.join(', '))}</p>` : '<p class="small">Every filing check maps to cited evidence.</p>'}`; }
        if (st.id === 'tests') body = `<div class="cards">${st.data.map(x => `<div><strong>${esc(x.id)} · ${esc(x.title)}</strong><span class="small">${esc(x.instruction.supplier_name)} · ${esc(x.instruction.payee_account_ref)} · ${gbp(x.instruction.amount)}${x.variant !== 'normal' ? ' · ' + esc(x.variant) : ''}</span><span class="small">expect <b>${esc(x.expect)} ${esc(x.expect_rule)}</b></span></div>`).join('')}</div>`;
        if (st.id === 'sandbox') { const ok = st.data.filter(x => x.pass).length; badge = `<span class="tag tag--${ok === st.data.length ? 'green' : 'red'}">${ok} of ${st.data.length} as expected</span> <span class="small">same code path as the payment check</span>`; body = `<div class="cards">${st.data.map(x => `<div data-pass="${x.pass}"><strong>${esc(x.id)} ${x.pass ? 'PASS' : 'FAIL'}</strong><span>${esc(x.decision)} <span class="mono">${esc(x.rule)} · ${esc(x.code)}</span></span><span class="small">${esc(x.reason)}</span></div>`).join('')}</div>`; }
        if (st.id === 'recommendation') { const dd = st.data; badge = `<span class="tag tag--blue">${esc(dd.label)}</span>`; body = `<p class="verdict verdict--${dd.verdict.startsWith('ADMIT') ? 'approve' : 'refer'}">${esc(dd.verdict)}</p><ul>${dd.reasons.map(x => `<li>${esc(x)}</li>`).join('')}</ul><p class="small">Draft note (${esc(modeLabel(dd.narrative_mode))}): ${esc(dd.narrative)}</p>`; }
        if (st.id === 'signoff') { stt = a.admission_status === 'admitted' ? 'done' : 'human'; body = `<p>${esc(st.data.who)} decides below. ${esc(st.data.note)}.${a.admission_status === 'admitted' ? ' <span class="tag tag--green">admitted</span>' : a.admission_status === 'declined' ? ' <span class="tag tag--red">declined</span>' : ''}</p>`; }
        const li = el('li', null, `<div class="stepper__title">${esc(st.title)} ${badge}</div><div class="stepper__body">${body}</div>`); li.dataset.state = stt; ol.append(li);
      }
    }
    async function runReview(auto) {
      const b = $('btn-review'); b.disabled = true; b.textContent = 'Running…';
      try { const r = await api('POST', `/api/registrations/${a.id}/review`, { hold_above: $('bk-condition').dataset.touched ? Number($('bk-condition').value) : null }); a.review = r.review; renderReview(r.review); $('review-note').textContent = (auto ? 'ran on opening · ' : '') + 'deterministic; the model only phrases the draft note'; }
      catch (e) { $('review-note').textContent = e.message; }
      finally { b.disabled = false; b.textContent = 'Run the six steps again'; }
    }
    $('btn-review').onclick = () => runReview(false);

    function renderExceptions() {
      const pt = state.pattern_threshold || { count: 2, window_hours: 24 };
      const mine = (state.violations || []).filter(x => !p || x.passport_id === p.passport_id);
      const alerts = (state.alerts || []).filter(x => !p || x.passport_id === p.passport_id);
      const al = $('bk-alert');
      if (alerts.length) { al.hidden = false; al.innerHTML = alerts.map(x => `ALERT · <a href="/bank?passport=${esc(x.passport_id)}">${esc(x.passport_id)}</a> · ${x.n} refusals at ${esc(x.rule)} ${esc(x.code)} within ${pt.window_hours}h <span>(threshold ${pt.count} in ${pt.window_hours}h, rule pack policy) · a pattern, not a single error · <a href="#exception">open the passport</a></span>`).join('<br>'); }
      else al.hidden = true;
      if ($('ex-meta')) $('ex-meta').textContent = mine.length ? `${mine.length} refusals · ${mine.filter(x => x.status === 'OPEN').length} open` : 'no refusals';
      const tb = $('bk-violations').querySelector('tbody'); tb.innerHTML = '';
      mine.forEach(x => { const tr = el('tr', null, `<td>${t(x.ts)}</td><td>${esc(x.instruction.supplier_name || '')} · <span class="mono">${esc(x.instruction.payee_account_ref || '')}</span> · ${gbp(x.instruction.amount)}${x.instruction.action_type !== 'pay_invoice' ? ' · ' + esc(x.instruction.action_type) : ''}${x.evidence ? ` · <span class="small">invoice ${esc(x.evidence.invoice)}</span>` : ''}${p ? '' : ` <span class="small">· <a href="/bank?passport=${esc(x.passport_id)}">${esc(x.passport_id)}</a></span>`}</td><td><b class="rule">${esc(x.rule)}</b> <span class="small">${esc(x.code.toLowerCase().replace(/_/g, ' '))}</span><br>${classTag(x.failure_class)}</td><td>${tag(x.status, x.status.toLowerCase())}${x.resolution ? ` <span class="small">${esc(x.resolution)}</span>` : ''}</td>`); tr.dataset.vid = x.id; tr.setAttribute('aria-selected', String(x.id === selectedVid)); tr.onclick = () => { selectedVid = x.id; renderEvidence(x); renderExceptions(); }; tb.append(tr); });
      if (!mine.length) tb.append(el('tr', null, '<td colspan="4" class="empty-row">Nothing refused yet.</td>'));
      const ex = $('exception'); ex.hidden = !p; if (!p) return;
      const inv = p.investigation === 'investigating';
      $('ex-state').innerHTML = `<span class="stamp stamp--${p.status === 'active' ? 'green' : p.status === 'suspended' ? 'amber' : 'red'}">${esc(p.status)}</span>${inv ? '<span class="stamp stamp--amber">investigating</span>' : ''}<span class="small">${p.status === 'suspended' ? 'payments blocked at R.2 while you look' : p.status === 'revoked' ? 'closed; passport list REVOKED, vouch voucher revoked' : 'payments flow; the verifier reads the list on every instruction'}${inv ? ' · investigating blocks nothing by itself; the list status does' : ''}</span>`;
      const act = $('ex-actions'); act.innerHTML = '';
      const btn = (label, cls, fn, guard) => { const b = el('button', 'btn btn--small ' + cls, label); b.type = 'button'; b.onclick = async () => { const r = $('bk-reason').value.trim(); if (!r) { $('ex-error').textContent = 'Give a reason first; it is recorded in the chain with your name.'; $('ex-error').hidden = false; $('bk-reason').focus(); return; } if (guard && b.dataset.armed !== '1') { b.dataset.armed = '1'; b.textContent = guard; setTimeout(() => { if (b.isConnected) { b.dataset.armed = ''; b.textContent = label; } }, 6000); return; } await fn(); }; act.append(b); };
      const reason = () => $('bk-reason').value.trim();
      if (p.status === 'active') btn('Suspend', 'btn--secondary', () => lifeFrom('suspended', reason()));
      if (p.status !== 'revoked' && !inv) btn('Open investigation', 'btn--secondary', async () => { await api('POST', `/api/passports/${p.passport_id}/investigation`, { action: 'open', note: reason() }); await refresh(); });
      if (p.status !== 'revoked') btn('Revoke', 'btn--warning', () => lifeFrom('revoked', reason()), `Confirm revoke: closes ${p.passport_id}${p.vouch_voucher_id ? ' and its voucher' : ''}`);
      if (p.status === 'suspended') btn('Reinstate (false positive)', '', () => lifeFrom('active', reason()));
      if (inv && p.status === 'active') btn('Close investigation, no change', 'btn--secondary', async () => { await api('POST', `/api/passports/${p.passport_id}/investigation`, { action: 'close', note: reason() }); await refresh(); });
    }
    async function lifeFrom(status, reason) {
      $('ex-error').hidden = true;
      try { await api('POST', `/api/passports/${p.passport_id}/status`, { status, reason }); $('bk-reason').value = ''; await refresh(); }
      catch (e) { $('ex-error').textContent = e.message; $('ex-error').hidden = false; }
    }
    function renderEvidence(x) {
      const ev = $('ex-evidence'); ev.hidden = false;
      const e = x.evidence;
      ev.innerHTML = `<strong>Refusal #${x.id} · ${esc(x.rule)} ${esc(x.code)} · ${t(x.ts)} · ${classTag(x.failure_class)}</strong><div>Instruction: ${esc(x.instruction.action_type)} · ${esc(x.instruction.supplier_name || '')} · <span class="mono">${esc(x.instruction.payee_account_ref || '')}</span> · ${gbp(x.instruction.amount)} ${esc(x.instruction.currency || '')} · invoice ${esc(x.instruction.invoice_ref || '—')} · nonce <span class="mono">${esc(x.instruction.nonce || '—')}</span> · evidence entry #${x.audit_id} · <a href="/api/evidence/violations/${x.id}" target="_blank" rel="noopener">export bundle</a></div>` +
        (e ? `<div>Extraction evidence (${esc(e.invoice)}, read by ${esc(modeLabel(e.extraction_mode))}): the AI agent read account <span class="${e.instruction_payee === e.registered_payee ? 'right' : 'wrong'}">${esc(e.instruction_payee)}</span>; the customer signed for <span class="mono">${esc(e.registered_payee || '—')}</span>.</div><dl class="kv">${Object.entries(e.facts || {}).filter(([k]) => !k.startsWith('_')).map(([k, f]) => `<div><dt>${esc(k.replace(/_/g, ' '))}</dt><dd>${esc(String(f.value))} <span class="prov"><q>${esc(f.quote || '')}</q></span></dd></div>`).join('')}</dl>` : '<div class="small">No document evidence: the instruction came straight from the AI agent.</div>');
    }

    async function renderPassport(p) {
      $('pp-id').textContent = p.passport_id;
      $('pp-status').innerHTML = tag(p.status);
      $('btn-suspend').hidden = p.status !== 'active'; $('btn-reinstate').hidden = p.status !== 'suspended'; $('btn-revoke').hidden = p.status === 'revoked';
      const full = await api('GET', `/api/passports/${p.passport_id}`);
      const env = $('envelope');
      env.innerHTML = envelopePanels(full);
      env.classList.toggle('envelope--incomplete', !full.mandate_signed);
      const stamp = $('envelope-stamp'); if (stamp) { const ok = full.verification.ok; stamp.innerHTML = ok ? `<span class="stamp stamp--green">ALL THREE VERIFY</span> <span class="small">bank and customer signatures checked with real Ed25519 calls just now · register receipt ${full.registration_receipt_verified ? 'verified' : 'not verified'}</span>` : `<span class="stamp stamp--amber">${esc(String(full.verification.failure || '').replace('_', ' '))}</span> <span class="small">the envelope is not complete</span>`; }
      env.classList.toggle('envelope--revoked', p.status === 'revoked');
      renderRail(p, null);
      $('jwt-panels').innerHTML = ['admission', 'agent_identity', 'mandate'].map(k => full.envelope[k] ? `<h4 class="h4">${k} <span class="small">JWT · header ${esc(JSON.stringify(full.headers[k]))}</span></h4><pre class="code">${esc(JSON.stringify(full[k], null, 2))}</pre><pre class="code code--wrap">${esc(full.envelope[k])}</pre>` : `<h4 class="h4">${k}</h4><p class="small">not yet signed</p>`).join('');
    }

    function renderRail(p, live) {
      const r = $('rail');
      const st = live ? live.status : p.vouch_status;
      const stTag = st === 'ACTIVE' ? tag('active', 'active on rail') : st === 'REVOKED' ? tag('revoked', 'revoked on rail') : tag('grey', st || 'unknown');
      r.innerHTML = `<div><span class="rail__k">Voucher</span><span class="rail__v mono">${esc(p.vouch_voucher_id || '—')}</span></div><div><span class="rail__k">Mode</span><span class="rail__v">${esc(p.vouch_mode || state.vouch_mode)}${p.vouch_mode === 'live-fallback' ? ' <span class="small">(fixture)</span>' : ''}</span></div><div><span class="rail__k">Status</span><span class="rail__v">${stTag}${live ? ` <span class="small">${esc(live.detail)}</span>` : ''}</span></div><button class="btn btn--secondary btn--small" id="btn-rail" type="button">Re-check on rail</button>`;
      $('btn-rail').onclick = async () => { const x = await api('GET', `/api/passports/${p.passport_id}/vouch`); renderRail(p, x.live); };
    }

    async function decide(decision) {
      const note = $('bk-officer-note').value.trim();
      $('decide-error').hidden = true;
      if (decision === 'admit' && !($('bk-condition').value && Number($('bk-condition').value) > 0)) { $('decide-error').textContent = 'Enter the hold condition, or prefill the demo data.'; $('decide-error').hidden = false; return; }
      try { await api('POST', `/api/registrations/${a.id}/admission`, { decision, note, hold_above: Number($('bk-condition').value) }); await refresh(); }
      catch (e) { $('decide-error').textContent = e.message; $('decide-error').hidden = false; }
    }
    async function life(status) {
      const reason = $('bk-reason').value.trim(); $('life-error').hidden = true;
      try { await api('POST', `/api/passports/${p.passport_id}/status`, { status, reason }); $('bk-reason').value = ''; await refresh(); }
      catch (e) { $('life-error').textContent = e.message; $('life-error').hidden = false; }
    }
    $('bk-condition').oninput = () => { $('bk-condition').dataset.touched = '1'; };
    $('btn-admit').onclick = () => decide('admit');
    $('btn-info').onclick = () => decide('request_info');
    $('btn-decline').onclick = () => decide('decline');
    $('btn-suspend').onclick = () => life('suspended');
    $('btn-reinstate').onclick = () => life('active');
    $('btn-revoke').onclick = () => life('revoked');
    $('btn-note').onclick = async () => { const b = $('btn-note'); b.disabled = true; b.textContent = 'Drafting…'; try { const r = await api('POST', `/api/registrations/${a.id}/file-note`); $('bk-filenote').value = r.note; $('note-mode').textContent = `drafted by ${modeLabel(r.mode)}`; } finally { b.disabled = false; b.textContent = 'Draft file note'; } };
  }

  // ───────────── Customer dashboard: the business account ─────────────
  const ACCOUNT_OPENING = 84213.50;
  const STATIC_TXNS = [   // synthetic September activity for Northgate Joinery Ltd, newest first; `manual` = a person made the payment in the app
    { d: '2026-09-08', desc: 'Ashby Ironmongery Ltd · invoice AI-3298 · paid by Helen Marsh', out: 2180.00, manual: true },
    { d: '2026-09-07', desc: 'Kiln Lane Estates Ltd · workshop rent', out: 3850.00 },
    { d: '2026-09-07', desc: 'Norfolk Hardwoods Ltd · invoice NH-772 · paid by Helen Marsh', out: 4120.00, manual: true },
    { d: '2026-09-06', desc: 'Fenwick Timber Ltd · invoice FT-1038 · paid by Helen Marsh', out: 1975.00, manual: true },
    { d: '2026-09-05', desc: 'HMRC PAYE and NIC · August', out: 6421.18 },
    { d: '2026-09-05', desc: 'Card · Screwfix, King\'s Lynn', out: 218.40 },
    { d: '2026-09-04', desc: 'Received · Harbourside Developments Ltd · invoice NJ-2287', in: 14200.00 },
    { d: '2026-09-03', desc: 'Salaries · 9 employees', out: 21740.00 },
    { d: '2026-09-02', desc: 'Received · Mrs P. Okafor · staircase deposit', in: 2600.00 },
    { d: '2026-09-01', desc: 'EDF Energy · direct debit', out: 612.73 },
    { d: '2026-09-01', desc: 'Received · Coastline Hotels Ltd · invoice NJ-2281', in: 9870.00 },
  ];
  async function customer() {
    const STATIC = !new URLSearchParams(location.search).get('live');
    let snap = STATIC ? await api('GET', '/api/customer/snapshot').catch(() => null) : null;
    const loadState = async () => snap ? snap.state : api('GET', '/api/bank/state');
    const loadAudit = async () => snap ? snap.audit : api('GET', '/api/bank/audit');
    let state = await loadState();
    if (snap && snap.state.decisions) lastDecisions = snap.state.decisions;
    const ref = new URLSearchParams(location.search).get('ref');
    const eventId = Number(new URLSearchParams(location.search).get('event')) || null;
    const qp = new URLSearchParams(location.search);
    const subpage = ref ? 'agent' : eventId ? 'event' : qp.get('trail') ? 'trail' : qp.get('tab') === 'transactions' ? 'transactions' : qp.get('new') ? 'new' : 'overview';
    document.body.dataset.cupage = subpage;
    let p = state.passports.find(x => x.passport_id === ref) || null;
    if (ref && !p && snap) { snap = null; state = await api('GET', '/api/bank/state'); p = state.passports.find(x => x.passport_id === ref) || null; }   // a live agent the snapshot does not hold
    const d0 = state.mandate_draft || { customer: {}, authorising_officer: {} };
    // the mandate form starts empty: the account holder and signatory are known, everything else is the customer's to write (or to prefill for the demo)
    const emptyDraft = () => ({ customer: d0.customer, authorising_officer: d0.authorising_officer, actions: d0.actions || ['pay_invoice'], currency: 'GBP', supplier_allowlist: [], per_payment_limit: '', monthly_limit_per_account: '', max_payments_per_day: '', valid_until: '' });
    const draft = emptyDraft(); let checkTimer = null, searchTimer = null, searchSeq = 0;
    let amending = new URLSearchParams(location.search).get('amend') === '1';
    const fromMandate = (m) => { const ad = (m.authorization_details || [{}])[0]; return { per_payment_limit: (ad.per_payment_limit || {}).amount, monthly_limit_per_account: (ad.monthly_limit_per_account || {}).amount, max_payments_per_day: ad.max_payments_per_day, valid_until: m.valid_until, supplier_allowlist: (ad.supplier_allowlist || []).map(s => ({ supplier_id: s.supplier_id, name: s.name, account_ref: s.account_ref, companies_house_number: s.companies_house_number || '' })) }; };
    let acRows = [], trailAll = subpage === 'trail', knownIds = null, pendingConfirm = null, toastTimer = null;
    let dismissed = new Set(); try { dismissed = new Set(JSON.parse(sessionStorage.getItem('ap-dismissed') || '[]')); } catch (e) { /* no storage */ }
    const remember = () => { try { sessionStorage.setItem('ap-dismissed', JSON.stringify([...dismissed])); } catch (e) { /* no storage */ } };
    // what matters to the customer: refusals, holds, decisions by a person, the mandate; never a routine processed payment
    const SIG_KINDS = new Set(['decision', 'mandate', 'incident', 'lifecycle', 'issue', 'exception']);
    const significant = (r) => r.kind === 'verify' ? (r.entry || {}).decision !== 'ALLOW' : SIG_KINDS.has(r.kind);
    const passOf = (subject) => state.passports.find(x => x.passport_id === subject || x.passport_id === String(subject || '').replace('AG-', 'AP-')) || null;
    const agentOf = (subject) => { const x = passOf(subject); return x ? (((x.agent_identity || {}).agent || {}).name || subject) : subject; };
    const approverOf = (subject) => { const x = passOf(subject) || {}; return (x.mandate || {}).signed_by || (x.mandate_proposed || {}).authorising_officer || (d0.authorising_officer || {}); };
    render(); renderAccount();
    // tabs: the split view on desktop, one section at a time below 900px
    const wide = () => window.innerWidth >= 900;
    function setTab(name) { if (ref || eventId) return; document.body.dataset.actab = name; document.querySelectorAll('.acct__tab').forEach(bt => bt.setAttribute('aria-selected', String(bt.dataset.tab === name))); $('ac-live').hidden = name === 'transactions'; $('ac-transactions').hidden = name !== 'transactions'; }
    document.querySelectorAll('.acct__tab').forEach(bt => { bt.onclick = () => setTab(bt.dataset.tab); });
    setTab(subpage === 'transactions' ? 'transactions' : 'live');
    window.addEventListener('resize', () => { const cur = document.body.dataset.actab; if (wide() && (cur === 'agents' || cur === 'trail')) setTab('live'); if (!wide() && cur === 'live') setTab('agents'); });
    // live: the trail, the notifications and the agents refresh while the page is open
    let acTimer = setInterval(async () => { if (document.hidden || snap) return; state = await api('GET', '/api/bank/state'); if (p) p = state.passports.find(x => x.passport_id === p.passport_id) || p; await renderAccount(); renderCards(); }, 3000);

    async function renderAccount() {
      const data = await loadAudit();
      const mine = data.rows.filter(r => r.subject && (r.subject.startsWith('AP-') || r.subject.startsWith('AG-'))); acRows = mine;
      const live = mine.filter(r => r.kind === 'verify').map(r => { const e = r.entry, i = e.instruction || {}; const dd = e.decision === 'ESCALATE' ? decisionFor(r.id) : null; const moved = e.decision === 'ALLOW' || (dd && dd.entry.outcome === 'RELEASED'); const word = moved ? '' : (e.decision === 'ESCALATE' ? (dd ? 'Refused' : 'Held') : 'Refused'); const byWhom = e.code === FIRST ? 'you' : 'your approver'; return { ai: { supplier: i.supplier_name || '', agent: agentOf(r.subject), invoice: i.invoice_ref, amount: Number(i.amount || 0), word, tone: e.decision === 'DENY' ? (classId(e.failure_class) === 'fraud' ? 'fraud' : 'error') : '', audit: r.id }, d: r.ts, desc: `${word ? `<b class="txn-blocked">${word}</b> · ` : ''}<b class="txn-ai">AI agent</b> ${esc(agentOf(r.subject))} · ${esc(i.supplier_name || '')} · <span class="mono">${esc(i.payee_account_ref || '')}</span> · invoice ${esc(i.invoice_ref || '')}${word ? ` · <span class="small">${e.decision === 'ESCALATE' ? (dd ? 'by ' + byWhom : 'for ' + byWhom) : 'Agent Passport ' + esc(e.rule)}</span>` : (dd ? ` · <span class="small">${e.code === FIRST ? 'first payment, confirmed by you' : 'released by your approver'}</span>` : '')}`, out: moved ? Number(i.amount || 0) : null, blocked: !moved, ts: r.ts }; });
      const all = [...live, ...STATIC_TXNS.map(x => ({ ...x, ts: x.d + 'T12:00:00Z' }))].sort((a, b) => (a.ts < b.ts ? 1 : -1));
      // running balance from the opening figure, newest first
      let bal = ACCOUNT_OPENING; const spent = live.reduce((s, x) => s + (x.out || 0), 0); bal -= spent;
      $('ac-balance').textContent = gbp2(bal); $('ac-avail').textContent = gbp2(bal - 4500);
      renderTxLog(live, all);
      const tb = $('ac-txns').querySelector('tbody'); tb.innerHTML = '';
      let running = bal;
      for (const x of all) {
        tb.append(el('tr', x.blocked ? 'txn--blocked' : null, `<td class="small">${d(x.ts)}</td><td>${x.desc.includes('<b') ? x.desc : esc(x.desc)}</td><td class="num">${x.out ? gbp2(x.out) : ''}</td><td class="num">${x.in ? gbp2(x.in) : ''}</td><td class="num small">${x.blocked ? '' : gbp2(running)}</td>`));
        if (!x.blocked) running = running + (x.out || 0) - (x.in || 0);
      }
      const fresh = knownIds ? new Set(mine.filter(r => !knownIds.has(r.id)).map(r => r.id)) : new Set();
      const shown = trailAll ? mine.slice(0, 60) : mine.filter(significant).slice(0, 12);
      trailRows($('ac-audit').querySelector('tbody'), shown, { newIds: fresh });
      $('cu-trail-toggle').textContent = trailAll ? 'Significant only' : `Show full trail (${mine.length})`;
      $('cu-trail-hint').hidden = trailAll;
      renderNotes(fresh);
      knownIds = new Set(mine.map(r => r.id));
      renderCards();
      if (eventId) renderEvent();
    }
    function renderEvent() {
      let r = acRows.find(x => x.id === eventId); const box = $('cu-event-body');
      if (!r) { box.innerHTML = '<p class="error">No record with that number on your account.</p>'; return; }
      // a decision points back at the instruction it decided: trace that one, with the decision as its last step
      if (r.kind === 'decision' && r.entry.held_audit_id) r = acRows.find(x => x.id === r.entry.held_audit_id) || r;
      const e = r.entry || {}, i = e.instruction || {}; const n = noteFor(r) || { tone: 'slate', label: r.kind, text: plainEvent(r) };
      const ap = approverOf(r.subject), sup = esc(i.supplier_name || 'a payee'), amt = gbp(i.amount), ag = esc(agentOf(r.subject)), bank = esc(String((state.cast || {}).bank || 'Your bank').replace(/\s*\(demo\)/i, ''));
      const x = passOf(r.subject) || {}; const ad = (((x.mandate || x.mandate_proposed || {}).authorization_details) || [{}])[0]; const hold = (((x.admission || {}).condition || {}).hold_above || {}).amount;
      const vio = (state.violations || []).find(v => v.audit_id === r.id); const ev = (vio || {}).evidence || null;
      const intentRow = ev && ev.intent ? acRows.find(y => y.id === ev.intent.audit_id) : null;
      const agentRow = intentRow ? acRows.find(y => y.kind === 'agent' && y.entry.intent_audit_id === intentRow.id) : null;
      const dd = decisionFor(r.id); const inc = acRows.find(y => y.kind === 'incident' && y.ts >= r.ts && y.subject === r.subject);
      const acct = (v) => `<span class="mono">${esc(v || '')}</span>`;
      const proof = () => '';
      const steps = [];
      if (r.kind === 'verify') {
        if (intentRow) steps.push({ who: 'agent', t: intentRow.ts, title: 'Your AI agent said what it was about to do', body: `Pay invoice ${esc(intentRow.entry.invoice_ref || '')} from ${esc(intentRow.entry.supplier_name || '')} to ${acct(intentRow.entry.declared_payee)}, the account you approved for them.`, proof: proof(intentRow) });
        if (agentRow) { const facts = (ev && ev.facts) || {}; const changed = (facts.bank_details_changed || {}).value; steps.push({ who: 'invoice', t: agentRow.ts, title: agentRow.entry.matches_intent ? 'It read the invoice, which matched' : 'The invoice said something different', body: agentRow.entry.matches_intent ? `The invoice asked for ${acct(agentRow.entry.attempted_payee)}, the same account.` : `The invoice asked for ${acct(agentRow.entry.attempted_payee)}${changed ? ' and claimed the bank details had changed' : ''}. Your agent followed the document.`, quote: (facts.account_number || {}).quote ? `“${esc((facts.bank_details_changed || {}).quote || (facts.account_number || {}).quote)}”` : '', proof: proof(agentRow) }); }
        steps.push({ who: 'agent', t: r.ts, title: `Your AI agent sent the payment`, body: `<b>${amt}</b> to ${sup} ${acct(i.payee_account_ref)}${i.invoice_ref ? `, invoice ${esc(i.invoice_ref)}` : ''}, signed with its own key.`, proof: '' });
        const trace = e.trace || []; const stopAt = trace.findIndex(st => !st.ok); const passed = stopAt < 0 ? trace.length : stopAt;
        const why = e.decision === 'ALLOW' ? 'It matched your mandate.' : e.code === 'PAYEE_NOT_ON_MANDATE' ? `The account on the invoice is not the one you approved for ${sup}.` : e.code === FIRST ? 'It is the first payment under your new mandate, so it waits for you.' : e.code === 'HUMAN_CONFIRMATION_REQUIRED' ? `It is above the ${gbp(hold)} you asked the bank to check with ${esc(ap.name || 'your approver')}.` : e.code === 'PER_PAYMENT_LIMIT_EXCEEDED' ? `It is more than the ${gbp((ad.per_payment_limit || {}).amount)} a payment you allow.` : e.code === 'MONTHLY_LIMIT_EXCEEDED' ? `It would take ${sup} past the ${gbp((ad.monthly_limit_per_account || {}).amount)} you allow in 30 days.` : e.code === 'CURRENCY_NOT_PERMITTED' ? 'It was not in pounds.' : e.code === 'REPLAY_DETECTED' ? 'This exact payment had already been made.' : e.code === 'AGENT_SIGNATURE_INVALID' ? 'It was not signed by your agent\'s own key.' : 'It did not match your mandate.';
        steps.push({ who: 'bank', t: r.ts, title: e.decision === 'DENY' ? `${bank} stopped it` : e.decision === 'ESCALATE' ? `${bank} is holding it` : `${bank} paid it`, body: why, proof: '' });
        if (e.decision === 'DENY') { const fraud = classId(e.failure_class) === 'fraud'; steps.push({ who: 'you', t: r.ts, title: 'Nothing left your account', body: fraud ? 'The bank\'s fraud team has the record. Nothing for you to do.' : 'If this keeps happening, raise it with your provider.', proof: '' }); }
        else if (e.decision === 'ESCALATE') {
          const first = e.code === FIRST;
          if (dd) { const who = esc(((dd.entry.decided_by || dd.entry.approver) || {}).name || 'Your approver'); const rel = dd.entry.outcome === 'RELEASED'; steps.push({ who: 'you', t: dd.ts, title: `${who} ${rel ? (first ? 'confirmed it' : 'released it') : 'refused it'}`, body: rel ? `Paid ${amt} to ${sup}.${first ? ' Payments inside the mandate now go through without confirmation.' : ''}` : 'Nothing left your account.', proof: proof(dd) }); }
          else steps.push({ who: 'you', t: null, title: first ? 'Waiting for you' : `Waiting for ${esc(ap.name || 'your approver')}`, body: first ? 'Review it and confirm or refuse. Nothing moves until you do.' : 'Nothing moves until they decide, in the bank dashboard.', act: first ? `<button class="btn" type="button" data-review="${r.id}">${pendingConfirm === r.id ? 'Hide the review' : 'Review and confirm'}</button>${pendingConfirm === r.id ? confirmHtml(n) : ''}` : '', proof: '' });
        } else steps.push({ who: 'you', t: r.ts, title: 'Paid', body: `${amt} left your account for ${sup}.`, proof: '' });
      } else if (r.kind === 'mandate' || r.kind === 'lifecycle' || r.kind === 'incident') {
        steps.push({ who: r.kind === 'mandate' ? 'you' : 'bank', t: r.ts, title: n.label, body: n.text, proof: proof(r) });
      } else steps.push({ who: 'bank', t: r.ts, title: n.label, body: plainEvent(r), proof: proof(r) });
      const WHO = { agent: 'Your AI agent', invoice: 'The invoice', bank: bank, you: 'You' };
      box.innerHTML = `<div class="cu-event__hero cu-event__hero--${n.tone}"><span class="tag tag--${n.tone === 'red' ? 'red' : n.tone === 'amber' ? 'amber' : 'grey'}">${esc(n.label)}</span><h2 class="cu-event__title">${n.text}</h2><p class="small">${d(r.ts)} · every step below is on the record, in the order it happened</p></div>
        <ol class="tl">${steps.map((st, k) => `<li class="tl__step tl__step--${st.who}${k === steps.length - 1 ? ' tl__step--last' : ''}"><span class="tl__dot" aria-hidden="true"></span><div class="tl__meta"><b>${esc(WHO[st.who])}</b>${st.t ? `<span class="mono small">${t(st.t)}</span>` : '<span class="small">now</span>'}</div><h3 class="tl__title">${st.title}</h3><p class="tl__body">${st.body}</p>${st.quote ? `<p class="tl__quote">${st.quote}</p>` : ''}${st.strip ? `<div class="tl__strip">${st.strip}</div>` : ''}${st.act ? `<div class="tl__act">${st.act}</div>` : ''}${st.proof}</li>`).join('')}</ol>
        <details class="cu-event__details"><summary>The full record</summary><h4 class="h4">The bank's checks, as run</h4><ol class="bd-trace">${(e.trace || []).map(st => `<li class="${st.ok ? 'ok' : (e.decision === 'ESCALATE' && st.rule === e.rule ? 'hold' : 'fail')}"><b>${esc(st.rule)}</b> ${esc(st.title)}<span>${esc(st.note)}</span></li>`).join('')}</ol><dl class="kv kv--card"><div><dt>Record</dt><dd>#${r.id} <span class="mono small">${esc(r.hash)}</span></dd></div><div><dt>Rule pack</dt><dd><span class="mono">${esc(e.rule_pack || '')}</span></dd></div><div><dt>Receipt</dt><dd>${r.receipt ? `signed by the bank · <span class="mono small">${esc(r.receipt.slice(0, 40))}…</span>` : 'none'}</dd></div></dl><div class="actions"${snap ? ' hidden' : ''}>${vio ? `<a class="btn btn--secondary btn--small" href="/api/evidence/violations/${vio.id}" target="_blank" rel="noopener">Export the evidence</a>` : `<a class="btn btn--secondary btn--small" href="/api/evidence/passports/${esc(String(r.subject || '').replace('AG-', 'AP-'))}" target="_blank" rel="noopener">Export the record</a>`}${r.kind === 'verify' ? `<button class="btn btn--secondary btn--small" type="button" id="cu-event-replay">Replay the decision</button><span class="actions__note" id="cu-event-replay-note"></span>` : ''}</div></details>`;
      const rb = $('cu-event-replay'); if (rb) rb.onclick = async () => { const rp = await api('POST', `/api/audit/${r.id}/replay`); $('cu-event-replay-note').innerHTML = rp.identical ? '<b class="ok">Replayed identically</b> from the stored inputs' : '<b class="bad">Replay differs</b>'; };
    }
    const gbp2 = (n) => '£' + Number(n || 0).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const dayLabel = (iso) => { const dd = new Date(iso), now = new Date(); const same = (a, b) => a.toDateString() === b.toDateString(); const y = new Date(now); y.setDate(now.getDate() - 1); return same(dd, now) ? 'Today' : same(dd, y) ? 'Yesterday' : dd.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' }); };
    const initials = (name) => String(name || '').split(/[\s·]+/).filter(w => /^[A-Za-z]/.test(w)).slice(0, 2).map(w => w[0].toUpperCase()).join('') || '·';
    function renderTxLog(live, all) {
      const ol = $('cu-tx'); if (!ol) return; ol.innerHTML = '';
      const rowsById = new Map(acRows.map(r => [r.ts + (r.entry.instruction || {}).invoice_ref, r]));
      let lastDay = null;
      all.slice(0, 14).forEach(x => {
        const day = dayLabel(x.ts); if (day !== lastDay) { ol.append(el('li', 'tx__day', esc(day))); lastDay = day; }
        const ai = x.ai; const name = ai ? (ai.supplier || 'AI agent payment') : x.desc.split(' · ')[0];
        const sub = ai ? `<span class="tx__who tx__who--ai">AI agent</span> ${esc(ai.agent)} · invoice ${esc(ai.invoice || '')}` : x.manual ? `<span class="tx__who">Manual</span> ${esc(x.desc.split(' · ').slice(1).join(' · '))}` : esc(x.desc.split(' · ').slice(1).join(' · ') || 'Account');
        const status = ai && ai.word ? `<span class="tag tag--${ai.word === 'Held' ? 'amber' : ai.tone === 'fraud' ? 'red' : 'grey'}">${esc(ai.word)}${ai.word === 'Refused' && ai.tone === 'fraud' ? ' · fraud indicator' : ai.word === 'Refused' && ai.tone === 'error' ? ' · agent error' : ''}</span>` : '';
        const amt = x.in ? `<span class="tx__amt in">+${gbp2(x.in)}</span>` : `<span class="tx__amt${x.blocked ? ' blocked' : ''}">${x.blocked ? gbp2(ai ? ai.amount : 0) : '−' + gbp2(x.out)}</span>`;
        const li = el('li', 'tx__row' + (ai ? ' tx__row--ai' : '') + (x.blocked ? ' tx__row--blocked' : ''), `<span class="tx__avatar${ai ? ' tx__avatar--ai' : ''}">${esc(initials(name))}</span><span class="tx__main"><b>${esc(name)}</b><small>${sub}${status ? ' ' + status : ''}</small></span>${amt}`);
        if (ai && ai.audit) { li.tabIndex = 0; li.setAttribute('role', 'link'); li.dataset.event = ai.audit; li.onclick = () => { location.href = `/customer?event=${ai.audit}`; }; li.onkeydown = (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); li.onclick(); } }; }
        ol.append(li);
      });
      if (!all.length) ol.append(el('li', 'small', 'No transactions yet.'));
    }
    if ($('cu-tx-all')) $('cu-tx-all').onclick = () => setTab('transactions');
    $('cu-trail-toggle').onclick = () => { if (subpage !== 'trail') { location.href = '/customer?trail=1'; return; } trailAll = !trailAll; renderAccount(); };

    // notifications: one sentence in the class's tone, the evidence one click away
    function noteFor(r) {
      const e = r.entry || {}, i = e.instruction || {}; const ag = esc(agentOf(r.subject)), sup = esc(i.supplier_name || 'a payee'), amt = gbp(i.amount); const ap = approverOf(r.subject);
      const base = { id: 'n' + r.id, audit: r.id, subject: r.subject, ts: r.ts, vio: null };
      if (r.kind === 'verify' && e.decision === 'DENY') {
        const vio = (state.violations || []).find(x => x.audit_id === r.id); base.vio = vio ? vio.id : null;
        if (classId(e.failure_class) === 'fraud') {
          const text = e.code === 'PAYEE_NOT_ON_MANDATE' ? `${ag} tried to pay ${sup} ${amt} to an account not on your mandate. The payment was refused. Nothing left your account.`
            : e.code === 'REPLAY_DETECTED' ? `A payment ${ag} had already made, ${sup} ${amt}, was presented again. The repeat was refused. Nothing left your account.`
            : e.code === 'AGENT_SIGNATURE_INVALID' ? `Something presented the passport of ${ag} without its key, to pay ${sup} ${amt}. The payment was refused. Nothing left your account.`
            : `An instruction for ${sup} ${amt} on the passport of ${ag} failed the bank's check at ${esc(e.rule)}. The payment was refused. Nothing left your account.`;
          return { ...base, tone: 'red', label: 'Refused · fraud indicator', text, sub: 'Stopped by the bank. Recorded for its risk team; a supervisor can request the evidence.' };
        }
        const how = e.code === 'CURRENCY_NOT_PERMITTED' ? 'in the wrong currency' : e.code === 'OUT_OF_SCOPE' ? 'for an action it is not permitted' : e.code === 'DAILY_COUNT_EXCEEDED' ? 'past its daily count' : ['MANDATE_EXPIRED', 'MANDATE_REVOKED', 'MANDATE_NOT_SIGNED'].includes(e.code) ? 'without a mandate in force' : 'outside its limits';
        return { ...base, tone: 'slate', label: 'Refused · agent error', text: `${ag} sent a payment ${how} (${sup}, ${amt}). It was refused. This may point to an agent quality issue worth raising with your provider.`, sub: 'Nothing left your account. A quality signal for you, not a report to anyone.' };
      }
      if (r.kind === 'verify' && e.decision === 'ESCALATE') {
        if (decisionFor(r.id)) return null;   // the decision entry tells the story
        if (e.code === FIRST) return { ...base, tone: 'amber', label: 'Your confirmation needed', first: true, text: `${ag} is about to make its first payment under mandate version ${esc(String(e.instruction ? ((passOf(r.subject) || {}).mandate || {}).version || 1 : 1))}: ${sup} ${amt}. Review and confirm it before it goes.`, sub: 'One confirmation for the first payment; after it, payments inside the mandate flow on their own.' };
        return { ...base, tone: 'amber', label: 'Held', text: `A payment above your approval threshold is waiting for ${esc(ap.name || 'your approver')}.`, sub: `${sup}, ${amt}, held at the bank. Nothing moves until ${esc(ap.name || 'your approver')} decides.` };
      }
      if (r.kind === 'decision') {
        const name = esc(((e.decided_by || e.approver) || {}).name || 'your approver'); const released = e.outcome === 'RELEASED';
        if (e.first_payment) return { ...base, tone: 'slate', label: released ? 'First payment confirmed' : 'First payment refused', text: released ? `${name} confirmed the first payment under mandate version ${esc(String(e.mandate_version || 1))}: ${sup} ${amt} was paid. Payments inside the mandate now flow without confirmation.` : `${name} refused the first payment under this mandate (${sup} ${amt}). Nothing left your account; the next attempt will ask again.`, sub: 'Recorded in the evidence chain with a receipt signed by the bank.' };
        return { ...base, tone: 'slate', label: released ? 'Released by approver' : 'Refused by approver', text: released ? `${name} released the held payment of ${amt} to ${sup}.` : `${name} refused the held payment of ${amt} to ${sup}. Nothing left your account.`, sub: `Recorded as ${esc(e.officer || '')} in the evidence chain.` };
      }
      if (r.kind === 'mandate') {
        if (e.revoked) return { ...base, tone: 'amber', label: 'Mandate revoked', text: `You revoked the mandate for ${ag}. It can no longer pay; the bank refuses from the next instruction.`, sub: 'The signed versions stay on record.' };
        if ((e.version || 1) > 1) return { ...base, tone: 'slate', label: 'Mandate amended', text: `You amended the mandate for ${ag}: version ${esc(String(e.version))} is in force. Its first payment under this version will wait for your confirmation.`, sub: (e.changes || []).map(c => c.added ? `added ${esc(c.added.name)}` : c.removed ? `removed ${esc(c.removed.name)}` : `${esc(c.field.replace(/_/g, ' '))} ${esc(String(c.from))} to ${esc(String(c.to))}`).join(', ') || 'no field changed' };
        return null;
      }
      if (r.kind === 'incident') return { ...base, tone: 'red', label: 'Incident', text: `The bank raised an incident on ${ag} after ${esc(String(e.denies))} refused instructions.`, sub: 'Its payments risk team is looking. Nothing left your account.' };
      if (r.kind === 'lifecycle') return { ...base, tone: 'amber', label: 'Passport status', text: `${esc(e.event)}${e.reason ? ': ' + esc(e.reason) : ''}.`, sub: `By ${esc(e.officer || 'the bank')}.` };
      return null;
    }
    function allNotes() {
      const notes = acRows.filter(significant).map(noteFor).filter(Boolean);
      // expiring soon is a state, not an event: read off the passport
      const soon = new Date(Date.now() + 14 * 864e5).toISOString().slice(0, 10);
      state.passports.filter(x => x.mandate_signed && !x.mandate_revoked_at && (x.mandate_proposed || {}).valid_until && x.mandate_proposed.valid_until <= soon).forEach(x => notes.push({ id: 'exp' + x.passport_id, subject: x.passport_id, ts: new Date().toISOString(), tone: 'amber', label: 'Mandate expiring', text: `The mandate for ${esc(agentOf(x.passport_id))} expires on ${d(x.mandate_proposed.valid_until)}.`, sub: 'Amend it to extend; nothing changes until you do.' }));
      return notes.sort((a, b) => (a.ts < b.ts ? 1 : -1));
    }
    function renderNotes(fresh) {
      const visible = allNotes().filter(n => !dismissed.has(n.id));
      const box = $('cu-notify'); box.hidden = !visible.length;
      $('cu-notify-meta').textContent = visible.length ? `${visible.length} item${visible.length === 1 ? '' : 's'}` : '';
      const ol = $('cu-notes'); ol.innerHTML = '';
      visible.slice(0, 3).forEach(n => {
        const brief = String(n.text).split(/\.\s+/)[0].replace(/\.$/, '') + '.';
        const li = el('li', `cu-note cu-note--${n.tone}${fresh && fresh.has(n.audit) ? ' is-new' : ''}${n.audit ? ' cu-note--link' : ''}`, `<div class="cu-note__head"><span class="tag tag--${n.tone === 'red' ? 'red' : n.tone === 'amber' ? 'amber' : 'grey'}">${esc(n.label)}</span><span class="mono small">${t(n.ts)}</span></div><p class="cu-note__text">${brief}</p>${n.first ? `<div class="cu-note__links"><button class="btn btn--small" type="button" data-review="${n.audit}">${pendingConfirm === n.audit ? 'Hide the review' : 'Review and confirm'}</button></div>${pendingConfirm === n.audit ? confirmHtml(n) : ''}` : ''}`);
        li.dataset.subject = n.subject || ''; if (n.audit) { li.dataset.event = n.audit; li.tabIndex = 0; li.setAttribute('role', 'link'); } ol.append(li);
      });
      $('cu-notify-more').textContent = '';
      // a toast for what just arrived, the newest one
      const arrived = fresh && fresh.size ? visible.find(n => fresh.has(n.audit)) : null;
      if (arrived) { const tst = $('cu-toast'); tst.className = `cu-toast cu-toast--${arrived.tone}`; tst.innerHTML = `<b>${esc(arrived.label)}</b> ${arrived.text}`; tst.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { tst.hidden = true; }, 8000); }
    }
    function confirmHtml(n) {
      const r = acRows.find(x => x.id === n.audit); if (!r) return ''; const i = r.entry.instruction || {}; const x = passOf(r.subject) || {}; const m = x.mandate || {}; const ap = approverOf(r.subject);
      const sup = ((m.authorization_details || [{}])[0].supplier_allowlist || []).find(sp => sp.account_ref === i.payee_account_ref) || {};
      const kv = (pairs) => `<dl class="kv">${pairs.map(([k, val]) => `<div><dt>${k}</dt><dd>${val}</dd></div>`).join('')}</dl>`;
      return `<div class="cu-confirm" role="group" aria-label="Review and confirm the first payment"><h3 class="h4">Review and confirm the first payment under this mandate</h3>${kv([['AI agent', `${esc(agentOf(r.subject))} · <span class="mono">${esc(r.subject)}</span>`], ['Payee', `${esc(i.supplier_name || '')} · <span class="mono">${esc(i.payee_account_ref || '')}</span>${sup.register_check && sup.register_check.found ? ` · ${esc(sup.register_check.legal_name)}, checked against the public register` : ''}`], ['Amount', `<b>${gbp(i.amount)}</b> ${esc(i.currency || 'GBP')}${i.invoice_ref ? ` · invoice <span class="mono">${esc(i.invoice_ref)}</span>` : ''}`], ['Mandate', `version ${esc(String(m.version || 1))}, signed by ${esc(ap.name || '')} · up to ${gbp(((m.authorization_details || [{}])[0].per_payment_limit || {}).amount)} a payment`], ['Checks', 'passed R.1 to R.8 at the bank; held at R.9 for this confirmation only']])}<div class="actions"><button class="btn" type="button" data-first="confirm" data-audit="${r.id}">Confirm and pay</button><button class="btn btn--secondary" type="button" data-first="refuse" data-audit="${r.id}">Not this one</button><span class="actions__note">Recorded in the evidence chain as ${esc(ap.name || '')}, ${esc(ap.role || '')}. After this, payments inside the mandate need no confirmation.</span></div><p class="error" id="cu-first-error" hidden></p></div>`;
    }
    $('cu-event-body').addEventListener('click', async (ev) => { const rv = ev.target.closest('[data-review]'); if (rv) { pendingConfirm = pendingConfirm === +rv.dataset.review ? null : +rv.dataset.review; renderEvent(); return; } const fp = ev.target.closest('[data-first]'); if (fp && !fp.disabled) { fp.disabled = true; try { await api('POST', `/api/audit/${fp.dataset.audit}/confirm-first`, { decision: fp.dataset.first }); pendingConfirm = null; } catch (e) { alert(e.message); fp.disabled = false; return; } state = await api('GET', '/api/bank/state'); await renderAccount(); } });
    $('cu-notes').addEventListener('keydown', (ev) => { const li = ev.target.closest('li[data-event]'); if (li && ev.target === li && (ev.key === 'Enter' || ev.key === ' ')) { ev.preventDefault(); location.href = `/customer?event=${li.dataset.event}`; } });
    $('cu-notes').addEventListener('click', async (ev) => {
      if (!ev.target.closest('a, button, .cu-confirm')) { const li = ev.target.closest('li[data-event]'); if (li) { location.href = `/customer?event=${li.dataset.event}`; return; } }
      const rv = ev.target.closest('[data-review]'); if (rv) { pendingConfirm = pendingConfirm === +rv.dataset.review ? null : +rv.dataset.review; renderNotes(); return; }
      const dm = ev.target.closest('[data-dismiss]'); if (dm) { dismissed.add(dm.dataset.dismiss); remember(); renderNotes(); renderCards(); return; }
      const evl = ev.target.closest('[data-ev]'); if (evl) { ev.preventDefault(); if (!wide()) setTab('trail'); let row = document.getElementById('ev-' + evl.dataset.ev); if (!row) { trailAll = true; await renderAccount(); row = document.getElementById('ev-' + evl.dataset.ev); } if (row) { row.scrollIntoView({ behavior: 'smooth', block: 'center' }); row.classList.add('is-spot'); setTimeout(() => row.classList.remove('is-spot'), 2500); } return; }
      const fp = ev.target.closest('[data-first]'); if (fp && !fp.disabled) {
        fp.disabled = true;
        try { const out = await api('POST', `/api/audit/${fp.dataset.audit}/confirm-first`, { decision: fp.dataset.first }); pendingConfirm = null; const tst = $('cu-toast'); tst.className = 'cu-toast cu-toast--slate'; tst.innerHTML = out.outcome === 'RELEASED' ? `<b>Confirmed.</b> ${gbp((out.settlement || {}).amount || (acRows.find(x => x.id === +fp.dataset.audit) || { entry: { instruction: {} } }).entry.instruction.amount)} is on its way. Payments inside the mandate now flow without confirmation; you hear about anything that matters.` : '<b>Refused.</b> Nothing left your account. The next attempt will ask again.'; tst.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { tst.hidden = true; }, 9000); }
        catch (e) { const er = $('cu-first-error'); if (er) { er.textContent = e.message; er.hidden = false; } fp.disabled = false; return; }
        state = await api('GET', '/api/bank/state'); if (p) p = state.passports.find(x => x.passport_id === p.passport_id) || p; await renderAccount(); renderCards();
      }
    });

    function renderCards() {
      const box = $('cu-agents'); box.innerHTML = '';
      const notes = allNotes().filter(n => !dismissed.has(n.id));
      state.passports.forEach(x => {
        const ag = (x.agent_identity || {}).agent || {}, mp = x.mandate_proposed || {}, ad = (((x.mandate || mp).authorization_details) || [{}])[0];
        const tot = Object.values(x.ledger || {}).reduce((s, y) => s + y.total, 0);
        const summary = x.mandate_signed ? `up to ${gbp((ad.per_payment_limit || {}).amount)} a payment · ${gbp((ad.monthly_limit_per_account || {}).amount)} per supplier account in 30 days · ${ad.max_payments_per_day || '?'} payments a day · ${esc(ad.currency || 'GBP')} only · valid to ${esc(mp.valid_until || '')} · ${(ad.supplier_allowlist || []).length} permitted supplier accounts` : 'mandate not signed yet';
        const vio = (state.violations || []).filter(y => y.passport_id === x.passport_id); const errs = vio.filter(y => y.failure_class !== 'fraud').length, fr = vio.filter(y => y.failure_class === 'fraud').length;
        const held = acRows.filter(r => r.kind === 'verify' && r.subject === x.passport_id && r.entry.decision === 'ESCALATE' && !decisionFor(r.id)).length;
        const mine = notes.filter(n => n.subject === x.passport_id || String(n.subject || '').replace('AG-', 'AP-') === x.passport_id);
        const tone = mine.some(n => n.tone === 'red') ? 'red' : mine.some(n => n.tone === 'amber') ? 'amber' : 'slate';
        const badge = mine.length ? `<span class="cu-badge cu-badge--${tone}" title="${mine.length} notification${mine.length === 1 ? '' : 's'} for this agent">${mine.length}</span>` : '';
        const trust = x.mandate_signed && !x.mandate_revoked_at ? (x.first_payment_confirmed ? `<span class="tag tag--green">first payment confirmed</span>` : `<span class="tag tag--amber">first payment awaits your confirmation</span>`) : '';
        const card = el('a', 'cu-card cu-card--link' + (x.passport_id === (p || {}).passport_id ? ' cu-card--current' : ''), `<div class="cu-card__head"><span>${badge}<span class="cu-card__name">${esc(ag.name || x.passport_id)}</span></span>${x.status === 'pending' ? tag('unsigned', 'awaiting your signature') : x.mandate_revoked_at ? tag('revoked', 'mandate revoked') : tag(x.status, x.status)}</div>${x.mandate_signed && !x.first_payment_confirmed && !x.mandate_revoked_at ? '<div class="cu-card__line small hold">first payment awaits your confirmation</div>' : ''}`);
        card.href = `/customer?ref=${x.passport_id}`; box.append(card);
      });
      if (!state.passports.length) box.append(el('p', 'small', 'No AI agent yet.'));
    }
    async function revokeMandate(pid) {
      if (!confirm('Revoke this mandate? The AI agent can no longer pay on this passport from the next instruction. The signed mandate stays on record and the revocation is written to the evidence chain.')) return;
      try { await api('POST', `/api/passports/${pid}/mandate/revoke`, { reason: 'revoked by the customer in the bank app' }); } catch (e) { alert(e.message); }
      state = await api('GET', '/api/bank/state'); if (p) p = state.passports.find(x => x.passport_id === p.passport_id) || p; amending = false; render(); renderAccount();
    }
    $('cu-agents').addEventListener('click', (e) => { const b = e.target.closest('[data-revoke]'); if (b) revokeMandate(b.dataset.revoke); });
    // the passport: three signed parts, side by side, each with only what a person needs to see
    function renderPassport(p, show) {
      const box = $('cu-passport'); box.hidden = !show; if (!show) return;
      const a = p.admission || {}, pr = a.product_ref || {}, ag = (p.agent_identity || {}).agent || {}, key = p.agent || {}, m = p.mandate || {}, ad = (m.authorization_details || [{}])[0];
      const kv = (pairs) => `<dl class="kv">${pairs.filter(x => x[1] != null && x[1] !== '').map(([k, val]) => `<div><dt>${k}</dt><dd>${val}</dd></div>`).join('')}</dl>`;
      const payees = (ad.supplier_allowlist || []).map(sp => `<span class="pp__payee">${esc(sp.name)} <span class="mono">${esc(sp.account_ref)}</span></span>`).join('');
      box.innerHTML = `<div class="pp__strip"><span class="pp__name">Agent Passport</span><span class="mono">${esc(p.passport_id)}</span>${tag(p.status)}<span class="pp__verify">${p.first_payment_confirmed ? 'first payment confirmed' : 'first payment awaits your confirmation'}</span></div>
        <div class="pp__cols">
          <section class="pp__part"><span class="pp__by">Signed by ${esc(state.cast ? state.cast.bank : 'the bank')}</span><h3 class="pp__h">Admission</h3>${kv([['Product', `${esc(pr.product_name || '')} <span class="small">by ${esc(pr.provider || '')}</span>`], ['Assurance', (LEVELS[(a.assurance_evidence || {}).level] || ['not declared'])[0]], ['Holds above', gbp(((a.condition || {}).hold_above || {}).amount)], ['Valid to', d(a.valid_until)]])}</section>
          <section class="pp__part"><span class="pp__by">Signed by you</span><h3 class="pp__h">Agent identity</h3>${kv([['Agent', esc(ag.name || '')], ['Model', `${esc(ag.model_provider || '')} <span class="mono">${esc(ag.model_version || '')}</span>`], ['Key', `<span class="mono">${esc(key.kid || '')}</span> · ${key.pop_verified ? 'possession proven' : 'possession pending'}`]])}</section>
          <section class="pp__part"><span class="pp__by">Signed by ${esc((m.signed_by || {}).name || 'you')}</span><h3 class="pp__h">Mandate <span class="small">version ${esc(String(m.version || 1))}</span></h3>${kv([['Per payment', gbp((ad.per_payment_limit || {}).amount)], ['Per supplier, 30 days', gbp((ad.monthly_limit_per_account || {}).amount)], ['Per day', `${esc(String(ad.max_payments_per_day || ''))} payments`], ['May pay', `<span class="pp__payees">${payees}</span>`], ['Expires', d(m.valid_until)]])}</section>
        </div>`;
    }
    function render() {
      const products = (state.products || []).filter(m => m.admission_status === 'admitted');
      renderCards();
      $('cu-empty').hidden = !!(products.length || p);
      $('cu-create').hidden = !products.length;
      if (subpage === 'new') $('cu-add-form').hidden = false;
      const sel = $('cu-model'); const chosen = sel.value; sel.innerHTML = products.map(m => `<option value="${m.registration_id}">${esc(m.product_name)} · ${esc(m.provider)} · ${esc((LEVELS[m.assurance_level] || ['no level'])[0].toLowerCase())}</option>`).join('');
      if (chosen && products.some(m => String(m.registration_id) === chosen)) sel.value = chosen;
      const showLevel = () => { const m = products.find(y => String(y.registration_id) === sel.value); if ($('cu-model-level')) $('cu-model-level').innerHTML = m ? `${levelTag(m.assurance_level)} <span class="small">assurance level the provider declared with its evidence</span>` : ''; document.querySelectorAll('#cu-products .cu-product').forEach(c => c.setAttribute('aria-checked', String(c.dataset.id === sel.value))); }; sel.onchange = showLevel;
      const pl = $('cu-products'); if (pl) { pl.innerHTML = products.map(m => { const c = ((m.ceilings || {}).per_payment_ceiling || {}).amount; return `<button type="button" class="cu-product" role="radio" data-id="${m.registration_id}" aria-checked="${String(m.registration_id) === sel.value}"><span class="cu-product__mark" aria-hidden="true"></span><span class="cu-product__body"><b>${esc(m.product_name)}</b><span class="small">by ${esc(m.provider)}${(m.payment_intent || {}).label ? ` · ${esc(m.payment_intent.label)}` : ''}</span><span class="cu-product__meta">${levelTag(m.assurance_level)}${m.condition && m.condition.hold_above ? `<span class="small">bank holds anything above ${gbp(m.condition.hold_above.amount)}</span>` : ''}${c ? `<span class="small">up to ${gbp(c)} a payment</span>` : ''}</span></span></button>`; }).join('') || '<p class="small">Your bank has not admitted any AI product yet.</p>'; pl.onclick = (ev) => { const c = ev.target.closest('.cu-product'); if (!c) return; sel.value = c.dataset.id; showLevel(); }; }
      showLevel();
      if ($('cu-legend')) $('cu-legend').hidden = true;
      if (!$('cu-agent-name').value) $('cu-agent-name').value = (state.agent_draft || {}).agent_name || '';
      $('cu-mandate').hidden = !p;
      if (ref || eventId) { $('ac-live').hidden = true; $('ac-transactions').hidden = true; document.body.dataset.actab = 'agent'; document.querySelectorAll('.acct__tab').forEach(bt => { bt.setAttribute('aria-selected', 'false'); }); }
      $('cu-event').hidden = !eventId;
      if (!p) return;
      const mp = p.mandate_proposed, ad = mp.authorization_details[0], signed = p.mandate_signed, ag = p.agent || {}; const revokedM = !!p.mandate_revoked_at;
      if (amending && (!signed || revokedM)) amending = false;
      const asPassport = signed && !amending && !revokedM; document.body.dataset.cusigned = asPassport ? '1' : '0'; renderPassport(p, asPassport);
      const tot0 = Object.values(p.ledger || {}).reduce((s0, y) => s0 + y.total, 0), vio0 = (state.violations || []).filter(y => y.passport_id === p.passport_id), fr0 = vio0.filter(y => y.failure_class === 'fraud').length;
      const held0 = acRows.filter(r => r.kind === 'verify' && r.subject === p.passport_id && r.entry.decision === 'ESCALATE' && !decisionFor(r.id)).length;
      const kvg = (pairs) => pairs.map(([k, val]) => `<div><dt>${k}</dt><dd>${val}</dd></div>`).join('');
      $('cu-agent-title').innerHTML = `${esc(p.agent_identity.agent.name)} ${p.status === 'pending' ? tag('unsigned', 'awaiting your signature') : tag(p.status, p.status)}`;
      $('cu-agent-stats').innerHTML = kvg([['Paid', `${gbp(tot0)} <span class="small">in ${p.payments || 0} payments</span>`], ['Held for a person', String(held0)], ['Refused', `${vio0.length}${fr0 ? ` <span class="small bad">${fr0} fraud indicator${fr0 === 1 ? '' : 's'} stopped by the bank</span>` : ''}`], ['First payment', signed ? (p.first_payment_confirmed ? '<span class="tag tag--green">confirmed by you</span>' : '<span class="tag tag--amber">awaits your confirmation</span>') : 'after you sign']]);
      $('cu-agent-kv').innerHTML = kvg([['Product', `${esc(p.agent_identity.agent.product_name)} <span class="small">by ${esc(p.agent_identity.agent.provider)}</span>`], ['Foundation model', `${esc(p.agent_identity.agent.model_provider)} <span class="mono small">${esc(p.agent_identity.agent.model_version)}</span>`], ['Assurance level', levelTag(((p.admission || {}).assurance_evidence || {}).level)], ['Agent id', `<span class="mono small">${esc(mp.agent_id)}</span>`], ['Key', `<span class="mono small">kid ${esc(mp.agent_kid)}</span> ${ag.pop_verified ? '<span class="tag tag--green">possession proven</span>' : '<span class="tag tag--amber">possession pending</span>'}`], ['Configuration', `<span class="mono small">${esc((ag.config_sha256 || '').slice(0, 16))}…</span>`], [p.status === 'pending' ? 'Record' : 'Passport', `<span class="mono">${esc(p.passport_id)}</span> <span class="small">${p.status === 'pending' ? 'issued when you sign the mandate' : 'issued by the bank when you signed'}</span>`], ['Issued', p.issued_at ? d(p.issued_at) : '']]);
      const _legacy = [['AI agent', `<strong>${esc(p.agent_identity.agent.name)}</strong> · <span class="mono">${esc(mp.agent_id)}</span> · ${esc(p.agent_identity.agent.product_name)} by ${esc(p.agent_identity.agent.provider)} (${esc(p.agent_identity.agent.model_provider)} <span class="mono">${esc(p.agent_identity.agent.model_version)}</span>)`], ['Its key', `<span class="mono">kid ${esc(mp.agent_kid)}</span> · ${ag.pop_verified ? '<span class="tag tag--green">possession proven</span>' : '<span class="tag tag--amber">possession pending</span>'} · config <span class="mono small">${esc((ag.config_sha256 || '').slice(0, 12))}…</span>`], [p.status === 'pending' ? 'Record' : 'Passport', `<span class="mono">${esc(p.passport_id)}</span> ${tag(p.status)} · ${p.status === 'pending' ? 'the passport is issued when you sign the mandate' : 'issued by the bank when you signed'}`]];
      $('cu-id').textContent = p.passport_id; $('cu-ref').textContent = p.passport_id;
      $('cu-state').innerHTML = revokedM ? tag('revoked', 'revoked') : signed ? tag('signed', amending ? `version ${p.mandate_version || 1}, amending` : `signed · version ${p.mandate_version || 1}`) : tag('unsigned', 'awaiting signature');
      $('cu-card').classList.toggle('mandate--signed', signed);
      const cls = ((state.policy || {}).customer_classes || {})[(d0.customer || {}).customer_class] || {}; const tier = ((state.policy || {}).account_tiers || {})[(d0.customer || {}).account_type] || {};
      $('cu-kv').innerHTML = [['Account holder', `${esc((mp.customer || d0.customer).legal_name)} · Companies House <span class="mono">${esc((mp.customer || d0.customer).companies_house_number)}</span> · ${esc(cls.label || '')}`], ['Account', `${esc(tier.label || '')} <span class="mono">${esc((d0.customer || {}).account_ref || '')}</span> · agent channel limited by this account type`], ['Signatory', `${esc((mp.authorising_officer || d0.authorising_officer).name)}, ${esc((mp.authorising_officer || d0.authorising_officer).role)}`], ['Bank hold', `the bank holds anything above ${gbp(p.admission.condition.hold_above.amount)} for your confirmation`]].map(([k, val]) => `<div><dt>${k}</dt><dd>${val}</dd></div>`).join('');
      renderMandateForm(p, signed, ad, mp);
      if ($('cu-limits') && tier.per_payment_gbp) $('cu-limits').innerHTML = `${esc(tier.label || '')}, ${esc(cls.label || '')}: agent ceiling up to ${gbp(tier.per_payment_gbp)} a payment, ${gbp(tier.monthly_per_account_gbp)} per supplier account in 30 days, ${tier.max_payments_per_day} payments a day, ${esc((state.policy || {}).currency || 'GBP')} only, capped further by the bank's admission ceiling for this product.`;

    }
    $('cu-add-toggle').onclick = () => { if (subpage !== 'new') location.href = '/customer?new=1'; };
    $('btn-create-agent').onclick = async () => {
      const b = $('btn-create-agent'); b.disabled = true; $('cu-create-error').hidden = true; $('cu-create-note').textContent = 'generating key, signing the bank\'s challenge…';
      try { const np = await api('POST', '/api/agents', { registration_id: Number($('cu-model').value), agent_name: $('cu-agent-name').value.trim() || null }); location.href = `/customer?ref=${np.passport_id}`; return; }
      catch (e) { $('cu-create-error').textContent = e.message; $('cu-create-error').hidden = false; }
      finally { b.disabled = false; $('cu-create-note').textContent = ''; }
    };
    function renderMandateForm(p, signed, ad, mp) {
      const ce = mp.ceilings || p.admission.ceilings || {}; const revokedM = !!p.mandate_revoked_at;
      $('cu-form').hidden = (signed && !amending) || revokedM || p.status === 'revoked';
      $('cu-suppliers-signed').hidden = !(signed && !amending) && !revokedM;
      $('cu-form-h').textContent = amending ? `Amend the mandate (version ${(p.mandate_version || 1) + 1})` : 'Write the mandate';
      $('btn-cu-prefill').hidden = amending;
      if (amending) { Object.assign(draft, fromMandate(p.mandate)); renderForm(); runCheck(); }
      if (signed || revokedM) {
        const src = p.mandate || {};
        const ad0 = (src.authorization_details || [{}])[0]; ad = ad0;
        const tb = $('cu-suppliers-signed').querySelector('tbody'); tb.innerHTML = '';
        ad.supplier_allowlist.forEach(s => { const rc = s.register_check; tb.append(el('tr', null, `<td><span class="mono">${esc(s.supplier_id)}</span> ${esc(s.name)}${rc ? `<br><span class="small">${rc.found ? `${esc(rc.legal_name)}, ${esc(rc.status)}, ${esc(rc.registered_office || '')}` : 'not on the register'} · checked against the public register (${esc(rc.source)}) · ${esc(rc.result)}</span>` : ''}</td><td class="mono">${esc(s.account_ref)}<br><span class="small">account from the customer; Confirmation of Payee planned, bank-side</span></td>`)); });
        $('cu-kv').insertAdjacentHTML('beforeend', [['May', `<strong>${esc(ad.actions.join(', '))}</strong> in ${esc(ad.currency)} only`], ['Per payment', `not more than ${gbp(ad.per_payment_limit.amount)}`], ['Per supplier account', `not more than ${gbp(ad.monthly_limit_per_account.amount)} in any rolling 30 days`], ['Per day', `not more than ${ad.max_payments_per_day || '?'} payments`], ['Expires', esc(mp.valid_until)]].map(([k, val]) => `<div><dt>${k}</dt><dd>${val}</dd></div>`).join(''));
        const tier0 = ((state.policy || {}).account_tiers || {})[(d0.customer || {}).account_type] || {}, cls0 = ((state.policy || {}).customer_classes || {})[(d0.customer || {}).customer_class] || {};
        if (tier0.per_payment_gbp) $('cu-kv').insertAdjacentHTML('beforeend', `<div><dt>Most you could grant</dt><dd id="cu-limits">${esc(tier0.label || '')}, ${esc(cls0.label || '')}: agent ceiling up to ${gbp(tier0.per_payment_gbp)} a payment, ${gbp(tier0.monthly_per_account_gbp)} per supplier account in 30 days, ${tier0.max_payments_per_day} payments a day, ${esc((state.policy || {}).currency || 'GBP')} only, capped further by the bank's admission ceiling for this product.</dd></div>`);
        $('cu-containment').className = 'containment containment--ok'; $('cu-containment').textContent = 'Within the agent-channel limits for this account. Checked at signing; the bank checks every payment against this mandate.';
      } else {
        $('cu-kv').insertAdjacentHTML('beforeend', `<div><dt>Most you can grant</dt><dd id="cu-limits">working it out…</dd></div>`);
        renderForm(); runCheck();
      }
      $('cu-signer').textContent = `${(draft.authorising_officer || {}).name}, ${(draft.authorising_officer || {}).role}, signs with the ${(draft.customer || {}).legal_name} key.`;
      $('cu-actions').hidden = (signed && !amending) || revokedM || p.status === 'revoked';
      $('btn-sign-mandate').textContent = amending ? 'Sign amended mandate' : 'Sign mandate';
      $('btn-cancel-amend').hidden = !amending;
      $('cu-manage').hidden = !(signed && !amending) || revokedM || p.status === 'revoked' || !!snap;
      $('cu-sig').hidden = !signed || amending || revokedM;
      if (signed && !revokedM) { const vn = p.mandate_version || 1; $('cu-sig').innerHTML = `<strong>${vn > 1 ? `Version ${vn} signed` : 'Signed'} ${d(p.mandate_signed_at)} at ${t(p.mandate_signed_at)} by ${esc((p.mandate.signed_by || {}).name)}, ${esc((p.mandate.signed_by || {}).role)}</strong> Ed25519 signature by the ${esc((mp.customer || {}).legal_name)} key. ${vn > 1 ? `Supersedes version ${vn - 1}; the bank enforces this version from the next instruction. The previous version stays on record.` : 'The bank issued the passport, the list shows ACTIVE and the voucher is minted on the vouch rail. Live at once.'}`; }
      const vers = p.mandate_versions || [];
      $('cu-versions').hidden = !vers.length && !revokedM;
      $('cu-versions').innerHTML = (revokedM ? `<div class="notice"><p><strong>Mandate revoked ${d(p.mandate_revoked_at)} at ${t(p.mandate_revoked_at)}.</strong> The AI agent can no longer pay on this passport; the bank refuses at R.5 from the next instruction and the voucher on the vouch rail is revoked. The signed versions stay on record below.</p></div>` : '') +
        (vers.length ? `<details class="jwt"><summary>Previous mandate versions, retained (${vers.length})</summary><ul class="small">${vers.map(vv => { const a0 = ((vv.mandate || {}).authorization_details || [{}])[0]; return `<li>Version ${vv.version} · signed ${t(vv.signed_at)} · up to ${gbp((a0.per_payment_limit || {}).amount)} a payment · ${gbp((a0.monthly_limit_per_account || {}).amount)} per supplier account · ${a0.max_payments_per_day || '?'} a day · valid to ${esc((vv.mandate || {}).valid_until || '')} · ${(a0.supplier_allowlist || []).length} payees · ${vv.revoked_at ? `revoked ${t(vv.revoked_at)}` : `superseded ${t(vv.superseded_at)}`}</li>`; }).join('')}</ul></details>` : '');
      $('cu-after').hidden = !signed || amending || revokedM;
      $('cu-jwt-wrap').hidden = !signed || amending;
      if (signed) api('GET', `/api/passports/${p.passport_id}`).then(full => { $('cu-jwt-payload').textContent = JSON.stringify(full.mandate, null, 2); $('cu-jwt').textContent = full.envelope.mandate || ''; });
    }
    function renderForm() {
      $('cu-per').value = draft.per_payment_limit ?? ''; $('cu-monthly').value = draft.monthly_limit_per_account ?? ''; $('cu-until').value = draft.valid_until || ''; $('cu-daily').value = draft.max_payments_per_day || '';
      const tb = $('cu-suppliers').querySelector('tbody'); tb.innerHTML = '';
      (draft.supplier_allowlist || []).forEach((s, i) => {
        tb.append(el('tr', null, `<td><span class="mono small">${esc(s.supplier_id || '')}</span> <input class="input" data-i="${i}" data-k="name" value="${esc(s.name)}" aria-label="Supplier name" placeholder="Type the supplier's name" autocomplete="off"><div class="cu-ch"><input class="input mono" data-i="${i}" data-k="companies_house_number" value="${esc(s.companies_house_number || '')}" aria-label="Companies House number" placeholder="or company no."><button class="btn btn--secondary btn--small" type="button" data-check="${i}">Check</button></div><div class="small cu-ch__out" id="cu-ch-${i}"></div></td><td><input class="input mono" data-i="${i}" data-k="account_ref" value="${esc(s.account_ref || '')}" aria-label="Sort code and account number" placeholder="60-11-22 12345678"></td><td><button class="link" type="button" data-remove="${i}">Remove</button></td>`));
        if (s.companies_house_number) checkCompany(i, false);
      });
      if (!(draft.supplier_allowlist || []).length) tb.append(el('tr', null, '<td colspan="3" class="small">No supplier yet. Add one and type its name.</td>'));
    }
    // name first: matches from the public register as the customer types; picking one fills the number, legal name and status
    async function searchCompany(i) {
      const s = draft.supplier_allowlist[i]; const out = $(`cu-ch-${i}`); if (!s || !out) return;
      const q = (s.name || '').trim(); if (q.length < 3) { out.innerHTML = ''; return; }
      const seq = ++searchSeq; out.innerHTML = '<span class="small">searching the public register…</span>';
      let r; try { r = await api('GET', `/api/companies/search?q=${encodeURIComponent(q)}`); } catch (e) { out.innerHTML = ''; return; }
      if (seq !== searchSeq) return;   // a later keystroke superseded this one
      out.innerHTML = r.items.length ? `<span class="small">Public register (${esc(r.items[0].source)}), pick one:</span><ul class="cu-matches">${r.items.map(it => `<li><button class="link" type="button" data-pick="${i}" data-number="${esc(it.number)}" data-name="${esc(it.legal_name)}" data-status="${esc(it.status)}">${esc(it.legal_name)}</button> <span class="mono">${esc(it.number)}</span> · ${esc(it.status)}${it.address ? ` · ${esc(it.address.split(',').slice(-2).join(',').trim())}` : ''}</li>`).join('')}</ul>` : `<span class="small">No match on the public register (${esc(r.mode === 'live' ? 'Companies House' : 'demo register, synthetic')}). Enter the company number if you have it.</span>`;
    }
    const scheduleSearch = (i) => { clearTimeout(searchTimer); searchTimer = setTimeout(() => searchCompany(i), 350); };
    async function checkCompany(i, loud) {
      const s = draft.supplier_allowlist[i]; const out = $(`cu-ch-${i}`); if (!s || !out) return;
      if (!s.companies_house_number) { if (loud) { const r = await api('GET', `/api/companies/search?q=${encodeURIComponent(s.name || '')}`); out.innerHTML = r.items.length ? 'Did you mean: ' + r.items.map(it => `<button class="link" type="button" data-pick="${i}" data-number="${esc(it.number)}">${esc(it.legal_name)} (${esc(it.number)}, ${esc(it.status)})</button>`).join(' · ') + ` <span class="small">· ${esc(r.items[0].source)}</span>` : 'No match on the public register.'; } return; }
      const r = await api('GET', `/api/companies/${encodeURIComponent(s.companies_house_number)}`);
      out.innerHTML = r.found ? `<span class="${r.active ? 'right' : 'wrong'}">${esc(r.legal_name)} · ${esc(r.status)}</span> · ${esc(r.address || '')} · checked against the public register (${esc(r.source)})${r.active ? '' : ' · not an active company'}` : `<span class="wrong">no company with this number</span> on the public register (${esc(r.source)})`;
    }
    function collect() {
      draft.per_payment_limit = Number($('cu-per').value); draft.monthly_limit_per_account = Number($('cu-monthly').value); draft.valid_until = $('cu-until').value; draft.max_payments_per_day = Number($('cu-daily').value); draft.currency = 'GBP';
      document.querySelectorAll('#cu-suppliers [data-i]').forEach(inp => { draft.supplier_allowlist[+inp.dataset.i][inp.dataset.k] = inp.value; });
      return draft;
    }
    async function runCheck() {
      if (!p) return;
      if (!draft.per_payment_limit && !(draft.supplier_allowlist || []).length) { const box = $('cu-containment'); box.className = 'containment'; box.textContent = 'Write the mandate, or prefill the demo data. The agent-channel check runs as you type.'; $('btn-sign-mandate').disabled = true; return; }
      try {
        const r = await api('POST', `/api/passports/${p.passport_id}/mandate/check`, collect());
        const box = $('cu-containment'); box.className = 'containment ' + (r.within_ceilings ? 'containment--ok' : 'containment--bad');
        box.innerHTML = r.within_ceilings ? 'Within the agent-channel limits for this account. Signing makes it live at once.' : `Outside the agent-channel limits for this account. Signing is refused until this is fixed.<ul>${r.problems.map(x => `<li>${esc(x.problem)}</li>`).join('')}</ul>`;
        if ($('cu-limits') && r.limits) $('cu-limits').innerHTML = `${esc(r.limits.account_tier.label)}, ${esc((((state.policy || {}).customer_classes || {})[((state.mandate_draft || {}).customer || {}).customer_class] || {}).label || '')}: agent ceiling up to ${gbp(r.limits.per_payment)} a payment, ${gbp(r.limits.monthly_per_account)} per supplier account in 30 days, ${r.limits.max_payments_per_day} payments a day, ${esc(r.limits.currency)} only, to ${esc(r.limits.max_validity)}. <span class="small">The lower of the account-type tier and the bank's admission ceiling for this product (${esc((LEVELS[r.limits.assurance_level] || ['no level'])[0].toLowerCase())}).</span>`;
        $('btn-sign-mandate').disabled = !r.within_ceilings;
      } catch (e) { $('cu-containment').textContent = e.message; }
    }
    const scheduleCheck = () => { clearTimeout(checkTimer); checkTimer = setTimeout(runCheck, 250); };
    $('cu-form').addEventListener('input', (e) => { if (e.target.matches('[data-i]')) collect(); if (e.target.matches('[data-k="name"]')) scheduleSearch(+e.target.dataset.i); scheduleCheck(); });
    $('cu-form').addEventListener('click', (e) => { const b = e.target.closest('[data-remove]'); if (b) { collect(); draft.supplier_allowlist.splice(+b.dataset.remove, 1); renderForm(); scheduleCheck(); return; } const c = e.target.closest('[data-check]'); if (c) { collect(); checkCompany(+c.dataset.check, true); return; } const k = e.target.closest('[data-pick]'); if (k) { collect(); const s = draft.supplier_allowlist[+k.dataset.pick]; s.companies_house_number = k.dataset.number; if (k.dataset.name) s.name = k.dataset.name; searchSeq++; renderForm(); const acc = document.querySelector(`#cu-suppliers [data-i="${k.dataset.pick}"][data-k="account_ref"]`); if (acc) acc.focus(); scheduleCheck(); } });
    $('btn-cu-prefill').onclick = () => { $('cu-context').hidden = false; $('cu-context').scrollIntoView({ behavior: 'smooth', block: 'center' }); };
    $('btn-cu-prefill-cancel').onclick = () => { $('cu-context').hidden = true; };
    $('btn-cu-prefill-go').onclick = () => { $('cu-context').hidden = true; Object.assign(draft, JSON.parse(JSON.stringify(d0))); renderForm(); runCheck(); };
    $('btn-amend-mandate').onclick = () => { amending = true; history.replaceState(null, '', `?ref=${p.passport_id}&amend=1`); render(); $('cu-form').scrollIntoView({ behavior: 'smooth', block: 'start' }); };
    $('btn-cancel-amend').onclick = () => { amending = false; history.replaceState(null, '', `?ref=${p.passport_id}`); render(); };
    $('btn-revoke-mandate').onclick = () => revokeMandate(p.passport_id);
    $('cu-add').onclick = () => { collect(); draft.supplier_allowlist.push({ supplier_id: `SUP-${String(draft.supplier_allowlist.length + 1).padStart(3, '0')}`, name: '', account_ref: '', companies_house_number: '' }); renderForm(); scheduleCheck(); };
    $('btn-sign-mandate').onclick = async () => {
      const b = $('btn-sign-mandate'); b.disabled = true; $('cu-error').hidden = true;
      try { const np = await api('POST', `/api/passports/${p.passport_id}/mandate/${amending ? 'amend' : 'sign'}`, collect()); amending = false; state = await api('GET', '/api/bank/state'); p = state.passports.find(x => x.passport_id === np.passport_id); history.replaceState(null, '', `?ref=${np.passport_id}`); render(); renderAccount(); }
      catch (e) { $('cu-error').textContent = typeof e.message === 'string' ? e.message : JSON.stringify(e.message); $('cu-error').hidden = false; b.disabled = false; }
    };
  }

  // ───────────── Expert console (/terminal?console=1) ─────────────
  // Presentation only: every verdict comes from POST /api/verify unchanged. The arena shows the nine checks
  // resolving in order (slowed for demonstration); the raw response is kept off-screen for the record and the tests.
  const SHORT = { 'R.1': 'bank admission signature', 'R.2': 'passport list status', 'R.3': 'agent identity signature', 'R.4': 'AI agent signature and nonce', 'R.5': 'customer mandate', 'R.6': 'action, currency, payee', 'R.7': 'per-payment limit', 'R.8': '30-day total and daily count', 'R.9': 'bank hold condition', 'C.a': 'root scope', 'C.b': 'delegation ⊆ root', 'C.c': 'action ⊆ delegation' };
  async function console_() {
    const state = await api('GET', '/api/bank/state');
    const ref = new URLSearchParams(location.search).get('ref');
    const issued = state.passports.filter(x => x.status !== 'pending');
    const p = issued.find(x => x.passport_id === ref) || issued[0] || null;
    const rules = (await api('GET', '/api/rulepack')).runtime_rules;
    const rl = $('rules'); rules.forEach(r => rl.append(el('li', null, `<code>${esc(r.id)}</code> ${esc(r.title)} → <code>${esc(r.on_fail)}</code>`)));
    const lines = $('term-lines');
    const RM = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const pause = (ms) => new Promise(r => setTimeout(r, RM ? 0 : ms));
    let denies = 0;
    function setDenies(n) { denies = n; $('denies').querySelectorAll('i').forEach((i, k) => i.classList.toggle('on', k < n)); }
    if (!p) $('g-subject').innerHTML = '<span class="tm-dim">no passport yet: admit a product in the <a href="/bank">Bank console</a>, then add an AI agent in <a href="/customer">My AI agents</a></span>';

    const judgment = $('judgment'), gWrap = $('gauntlet-wrap'), gCells = $('gauntlet'), gVerdict = $('g-verdict'), fullBox = $('tm-full');
    const inView = (n) => { const r = n.getBoundingClientRect(); return r.top >= 0 && r.bottom <= window.innerHeight; };
    function openFull() { judgment.classList.add('is-full'); document.body.classList.add('tm-lock'); $('g-close').hidden = false; }
    function closeFull() { judgment.classList.remove('is-full'); document.body.classList.remove('tm-lock'); $('g-close').hidden = true; }
    gWrap.addEventListener('click', (e) => { if (judgment.classList.contains('is-full') && !judgment.classList.contains('is-live') && !e.target.closest('label, input, a, details')) closeFull(); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeFull(); });
    function subjectHtml(b, k) {
      return `${esc(b.action_type)} · ${esc(b.supplier_name)} · <span class="mono">${esc(b.payee_account_ref)}</span> · ${gbp(b.amount)}${k ? ' · #' + k : ''}${b.signer === 'rogue' ? ' · <span class="tm-warn">signed with a rogue key</span>' : ''}${b.invoice ? ` · <span class="mono">${esc(b.invoice)}</span>` : ''}`;
    }
    function cellIds(trace) {
      const ids = [];
      rules.forEach(r => { if (r.id === 'R.6') trace.filter(t => t.rule.startsWith('C.')).forEach(t => ids.push(t.rule)); ids.push(r.id); });
      return ids;
    }
    function setCell(li, state, note) { li.dataset.state = state; li.querySelector('.g-cell__s').innerHTML = note; }
    async function judge(b, r, k, fast) {
      const step = fast ? 110 : 240;
      const byRule = Object.fromEntries(r.trace.map(t => [t.rule, t]));
      const ids = cellIds(r.trace);
      judgment.classList.add('is-live'); gWrap.dataset.decision = '';
      if (fullBox.checked) openFull(); else if (!inView(gWrap)) gWrap.scrollIntoView({ behavior: RM ? 'auto' : 'smooth', block: 'start' });
      $('g-subject').innerHTML = subjectHtml(b, k); $('g-count').textContent = '';
      gCells.innerHTML = ''; ids.forEach(id => { const li = el('li', 'g-cell'); li.dataset.rule = id; li.dataset.state = 'idle'; li.innerHTML = `<b>${esc(id)}</b><span class="g-cell__t">${esc(SHORT[id] || (rules.find(x => x.id === id) || {}).title || '')}</span><span class="g-cell__s">—</span>`; gCells.append(li); });
      gVerdict.className = 'g__verdict'; gVerdict.innerHTML = '<span class="tm-dim">evaluating…</span>';
      const cells = [...gCells.children];
      let stopped = false;
      for (let i = 0; i < ids.length; i++) {
        const li = cells[i], tr = byRule[ids[i]];
        if (stopped || !tr) { setCell(li, 'skip', 'not evaluated · denied by default'); await pause(step / 4); continue; }
        $('g-count').textContent = `${i + 1} / ${ids.length}`;
        setCell(li, 'checking', 'checking…'); await pause(step);
        setCell(li, tr.ok ? 'pass' : (r.decision === 'ESCALATE' ? 'hold' : 'fail'), esc(tr.note));
        if (!tr.ok) { stopped = true; $('g-count').textContent = `stopped at ${ids[i]}`; }
      }
      if (!stopped) $('g-count').textContent = `${ids.length} / ${ids.length}`;
      await pause(step * 1.2);
      const cite = r.decision === 'ALLOW' ? `all ${ids.length} checks passed · ${esc(r.code)}` : `${esc(r.rule)} · ${esc(r.code)}`;
      const sig = r.signature && r.signature.checked ? `AI agent signature <b class="${r.signature.verified ? 'ok' : 'fail'}">${r.signature.verified ? 'verified' : 'failed'}</b> · ` : '';
      const reg = r.rails && r.rails.passport_list, rv = r.rails && r.rails.vouch;
      const rails = r.rails && (reg !== 'active' || (rv && rv.status === 'REVOKED')) ? `<span>passport list <b class="${reg !== 'active' ? 'fail' : ''}">${esc(reg)}</b> · vouch rail <b class="${rv.status === 'REVOKED' ? 'fail' : ''}">${esc(rv.status || 'none')}</b>${reg !== 'active' && rv.status === 'REVOKED' ? ' · one action by the bank, two rails refuse' : ''}</span>` : '';
      const settle = r.settlement ? `<span class="ok">${esc(r.settlement.rail_reason)}</span>` : '';
      const vio = r.violation ? `<span>violation #${r.violation.id} recorded ${esc(r.violation.status)} · ${classTag(r.failure_class)} <a href="/bank">→ Bank dashboard</a></span>` : '';
      const held = r.decision === 'ESCALATE' ? (r.code === FIRST ? `<span class="hold">held for the customer: the first payment under this mandate version is confirmed once, in its banking app <a href="/customer?ref=${esc(r.passport_id || (p || {}).passport_id || '')}">→ Customer dashboard</a></span>` : `<span class="hold">held for the customer's named approver; the bank's officer records the decision <a href="/bank">→ Bank dashboard</a></span>`) : '';
      const inc = r.incident ? `<span class="fail"><b>INCIDENT</b> raised to the payments risk team · ${r.incident.denies} refused instructions <a href="/bank">→ Bank console</a></span>` : '';
      gVerdict.className = 'g__verdict g__verdict--' + r.decision; gWrap.dataset.decision = r.decision;
      gVerdict.innerHTML = `<span class="g-word">${r.decision}</span><span class="g-cite">${cite}</span><span class="g-reason">${esc(r.reason)}</span><span class="g-notes">${settle}${held}${rails}${vio}${inc}<span class="tm-dim">${sig}receipt signed by the bank · evidence #${r.audit_id} <span class="mono">${esc(r.audit_hash.slice(0, 12))}</span> <a href="/bank#bd-trail">→ Evidence trail</a></span></span>`;
      judgment.classList.remove('is-live');
    }
    function logLine(b, r, k) {
      lines.append(termLine(b, r, k));
      if (r.incident) { lines.append(el('li', 't-incident', `<span><b>INCIDENT</b> raised to the payments risk team · ${r.incident.denies} refused instructions · evidence #${r.incident.audit_id}</span>`)); setDenies(0); }
      else if (r.decision === 'DENY') setDenies(Math.min(3, (r.deny_count || denies + 1)));
    }
    async function present(b, r, k, fast) { await judge(b, r, k, fast); logLine(b, r, k); }
    const hideSteps = () => { $('invoice-steps').hidden = true; $('invoice-outcome').hidden = true; $('inv-contrast').hidden = true; };

    const ct = $('chain-toggle'); ct.checked = !!state.delegation_chain;
    const chainOn = () => ct.checked;
    const cbw = $('chain-beats-wrap'); cbw.hidden = !ct.checked;
    ct.onchange = () => { cbw.hidden = !ct.checked; };
    function beatButton(b, onclick) {
      const btn = el('button', 'beat'); btn.type = 'button'; btn.disabled = !p; btn.title = b.hint || '';
      btn.innerHTML = `<span class="beat__label">${esc(b.label)}</span><span class="beat__expect">${esc(b.expect)}</span>`;
      btn.onclick = async () => { btn.disabled = true; btn.dataset.running = 'true'; hideSteps(); try { await onclick(); } finally { btn.disabled = false; delete btn.dataset.running; } };
      return el('li').appendChild(btn).parentElement;
    }
    (state.chain_beats || []).forEach(b => $('chain-beats').append(beatButton(b, async () => {
      const r = await api('POST', '/api/agent/act', { passport_id: p.passport_id, action_type: b.action_type, supplier_name: b.supplier_name, payee_account_ref: b.payee_account_ref, amount: b.amount, invoice_ref: b.invoice_ref, signer: b.signer, chain: true, delegate_amount: b.delegate_amount, delegate_account: b.delegate_account || null });
      await present(b, r);
    })));
    function chainHtml(ch) {
      if (!ch) return '';
      const s = ch.scopes;
      return `<span class="chain__inv">${esc(ch.invariant)}</span><div class="chain__scopes"><div><strong>S0 · root mandate</strong>${s.S0.beneficiaries} beneficiaries · ceiling ${gbp(s.S0.ceiling)} · ${esc(s.S0.actions.join(', '))}</div><div><strong>S1 · delegation</strong>${esc((s.S1.beneficiaries || []).join(', ') || '—')} · ceiling ${gbp(s.S1.ceiling)} · ${esc((s.S1.actions || []).join(', '))}<br><span class="small">${esc(s.S1.issuer || '')} → ${esc(s.S1.delegate || '')}</span></div><div><strong>action</strong>${esc(s.action.action)} · ${esc(s.action.payee)} · ${gbp(s.action.amount)}</div></div><ul class="chain__checks">${ch.checks.map(c => `<li class="${c.ok ? '' : (c.note.startsWith('not evaluated') ? 'skip' : 'fail')}"><b>${esc(c.id)}</b> ${esc(c.title)}: ${esc(c.note)}</li>`).join('')}</ul>`;
    }

    const ib = $('invoice-buttons');
    (state.invoices || []).forEach(inv => {
      const b = el('button', 'btn ' + (inv.id.endsWith('clean') ? 'btn--secondary' : 'btn--warning'), esc(inv.label) + ' <span class="btn__sub mono">' + esc(inv.id) + '</span>'); b.type = 'button'; b.disabled = !p;
      b.onclick = async () => {
        ib.querySelectorAll('button').forEach(x => x.disabled = true); b.textContent = 'AI agent reading…';
        try { const r = await api('POST', '/api/agent/invoice', { passport_id: p.passport_id, invoice_id: inv.id, chain: chainOn() }); await showInvoice(r); }
        catch (e) { alert(e.message); }
        finally { ib.querySelectorAll('button').forEach(x => x.disabled = false); b.innerHTML = esc(inv.label) + ' <span class="btn__sub mono">' + esc(inv.id) + '</span>'; }
      };
      ib.append(b);
    });
    async function showInvoice(r) {
      const steps = $('invoice-steps'), out = $('invoice-outcome'); steps.hidden = false; out.hidden = true;
      steps.querySelectorAll('.invoice__step').forEach(x => x.hidden = true); out.querySelectorAll('[data-step]').forEach(x => x.hidden = true); $('inv-contrast').hidden = true;
      const acct = r.instruction.payee_account_ref, ok = r.on_allowlist;
      const digits = (r.extraction.account_number || {}).value || '';
      $('g-subject').innerHTML = `<span class="mono">${esc(r.invoice)}</span> · read by ${esc(modeLabel(r.extraction_mode))}`;
      gWrap.scrollIntoView({ behavior: RM ? 'auto' : 'smooth', block: 'start' });
      $('inv-text').innerHTML = esc(r.text).replace(new RegExp('(Account number:\\s*)(' + digits + ')'), `$1<mark class="${ok ? 'ok' : ''}">$2</mark>`).replace(/(IMPORTANT: our bank details have changed[^\n]*)/, '<mark>$1</mark>');
      $('inv-facts').innerHTML = Object.entries(r.extraction).filter(([k]) => !k.startsWith('_')).map(([k, f]) => `<div><dt>${esc(k.replace(/_/g, ' '))}</dt><dd>${k === 'account_number' ? `<span class="${ok ? 'right' : 'wrong'}">${esc(f.value)}</span>` : esc(String(f.value))} <span class="prov"><q>${esc(f.quote || '')}</q></span></dd></div>`).join('');
      steps.querySelector('[data-step="a"]').hidden = false; await pause(900);
      const i = r.instruction;
      $('inv-instruction').innerHTML = [['Action', esc(i.action_type)], ['Payee', esc(i.supplier_name)], ['Account', `<span class="${ok ? 'right' : 'wrong'}">${esc(acct)}</span>${ok ? ' · on the customer-signed mandate' : ` · not on the mandate; the customer signed for <span class="mono">${esc(r.registered_payee || '—')}</span>`}`], ['Amount', gbp(i.amount) + ' ' + esc(i.currency)], ['Signed by', 'the AI agent key bound in agent_identity (Ed25519)']].concat(r.intent ? [['Declared intent', `${esc(r.intent.task)} → <span class="mono">${esc(r.intent.declared_payee || '—')}</span> <span class="prov">declared before the document was opened · evidence #${r.intent.audit_id}</span>${r.intent.matches ? ' <span class="right">attempted payee matches</span>' : ` <span class="intent-miss">attempted payee differs: the document changed the destination, the AI agent did not</span>`}`]] : []).map(([k, v_]) => `<div><dt>${k}</dt><dd>${v_}</dd></div>`).join('');
      const chv = $('inv-chain');
      if (r.chain && r.result.chain) { chv.hidden = false; chv.innerHTML = `<strong>Delegation chain</strong> <span class="small">the orchestrator read the invoice and delegated exactly what it read to the execution agent, which signed</span>` + chainHtml(r.result.chain); }
      else if (r.chain) { chv.hidden = false; chv.innerHTML = '<strong>Delegation chain</strong> <span class="small">presented; the bank refused before reaching it</span>'; }
      else chv.hidden = true;
      steps.querySelector('[data-step="b"]').hidden = false; await pause(900);
      const res = r.result;
      const subject = { action_type: i.action_type, supplier_name: i.supplier_name, payee_account_ref: acct, amount: i.amount, signer: 'agent', invoice: r.invoice };
      await judge(subject, res);
      const box = $('inv-verdict'); box.className = 'invoice__verdict invoice__verdict--' + res.decision;
      box.innerHTML = `<span class="t-verdict t-verdict--${res.decision}">${res.decision}</span> <b>${res.decision === 'ALLOW' ? 'all nine checks passed' : esc(res.rule) + ' · ' + esc(res.code)}</b>${res.rule === 'R.6' && res.decision === 'DENY' ? ' · named-beneficiary mandate check (FATF 2025 AML/CFT alignment): the customer signed for accounts, not names' : ''}${res.violation ? ` · violation #${res.violation.id} recorded ${esc(res.violation.status)}` : ''}${res.signature ? ` · R.4 instruction signature: ${res.signature.checked ? (res.signature.verified ? 'VERIFIED' : 'FAILED') : 'not reached'}` : ''}`;
      out.hidden = false; box.hidden = false;
      logLine(subject, res);
      await pause(700);
      $('inv-caption').textContent = ok
        ? 'The AI agent read a genuine invoice and paid the account the customer signed for. Same agent, same mandate: the next invoice is the test.'
        : 'The AI agent read a manipulated invoice and would have paid the wrong account. The mandate stopped it.';
      $('inv-caption').hidden = false;
      const con = $('inv-contrast'); con.hidden = ok;
      if (!ok) con.innerHTML = '<b>Today:</b> a disputed payment, no record of what the AI agent was permitted to do. <b>Here:</b> a refused instruction, a flagged entry for the bank\'s risk team, and a replayable record showing the document changed the destination, not the agent.';
    }

    state.beats.forEach(b => $('beats').append(beatButton(b, async () => {
      for (let k = 0; k < (b.repeat || 1); k++) {
        const r = b.replay ? await api('POST', '/api/agent/replay', { passport_id: p.passport_id }) : await api('POST', '/api/agent/act', { passport_id: p.passport_id, action_type: b.action_type, supplier_name: b.supplier_name, payee_account_ref: b.payee_account_ref, amount: b.amount, currency: b.currency || 'GBP', invoice_ref: b.repeat ? `${b.invoice_ref}-${k + 1}` : b.invoice_ref, signer: b.signer });
        const shown = b.replay ? { ...b, supplier_name: (r.trace && r.reason) ? 'replayed instruction' : b.supplier_name } : b;
        await present(shown, r, b.repeat ? k + 1 : null, k > 0);
        if (r.decision !== 'ALLOW') break;
      }
    })));
    function termLine(b, r, k) {
      const trace = r.trace.map(s => `<b>${esc(s.rule)}</b> ${s.ok ? '✓' : '✗'} ${esc(s.note)}`).join(' · ');
      const settle = r.settlement ? `<span class="t-settle">${esc(r.settlement.rail_reason)} · 30-day total for this account now ${gbp(r.settlement.ledger_total_after)}</span>` : '';
      const sigLine = r.signature ? `<span class="t-sig">R.4 instruction signature: <b class="${r.signature.verified ? 'ok' : 'fail'}">${r.signature.checked ? (r.signature.verified ? 'VERIFIED' : 'FAILED') : 'not reached'}</b> (${esc(r.signature.alg)}) · AI agent key ${esc(r.signature.agent_kid || '—')} · payload sha256 ${esc((r.signature.instruction_hash || '').slice(0, 12))}</span>` : '';
      const chainLine = r.chain ? `<span class="t-chain">${esc(r.chain.invariant)} · ${r.chain.checks.map(c => `<b class="${c.ok ? 'ok' : 'fail'}">${esc(c.id)} ${c.ok ? '✓' : '✗'}</b>`).join(' ')} · S1 ${esc((r.chain.scopes.S1.beneficiaries || []).join(', '))} ≤ ${gbp(r.chain.scopes.S1.ceiling)}</span>` : '';
      const rv = r.rails && r.rails.vouch, reg = r.rails && r.rails.passport_list;
      const rails = r.rails ? `<span class="t-rails">passport list <b class="${reg !== 'active' ? 'refused' : ''}">${esc(reg)}</b> · vouch rail <b class="${rv.status === 'REVOKED' ? 'refused' : ''}">${esc(rv.status || 'none')}</b>${rv.voucher_id ? ' ' + esc(rv.voucher_id) : ''}${reg !== 'active' && rv.status === 'REVOKED' ? ' · one action by the bank, two rails refuse' : ''}</span>` : '';
      return el('li', null, `<span class="t-time">${t(new Date().toISOString())}</span><span class="t-body">
        <span class="t-head"><span class="t-action">${esc(b.action_type)} · ${esc(b.supplier_name)} · ${esc(b.payee_account_ref)} · ${gbp(b.amount)}${k ? ' · #' + k : ''}${b.signer === 'rogue' ? ' · signed with rogue key' : ''}</span><span class="t-verdict t-verdict--${r.decision}">${r.decision}</span><span class="t-rule">${r.decision === 'ALLOW' ? 'all nine checks passed · ' + esc(r.code) : 'rule ' + esc(r.rule) + ' · ' + esc(r.code) + (r.failure_class ? ' · ' + esc(r.failure_class.label) : '')}</span></span>
        <span class="t-reason">${esc(r.reason)}${r.decision === 'DENY' && r.rule === 'R.6' ? ' · Named-beneficiary mandate check (FATF 2025 AML/CFT alignment)' : ''}</span>${sigLine}${chainLine}${settle}${rails}
        <span class="t-trace">${trace}</span>
        <span class="t-meta">evidence #${r.audit_id} <b>${esc(r.audit_hash.slice(0, 12))}</b> ← <b>${esc(r.prev_hash.slice(0, 12))}</b> · rule pack <b>${esc(r.rule_pack)}</b> · receipt signed by the bank · decision replayable</span>
        <details class="receipt"><summary>receipt</summary>${esc(r.receipt)}</details></span>`);
    }
  }

  // ───────────── Evidence trail (shared renderer) ─────────────
  function plainEvent(r) {
    const e = r.entry || {}, i = e.instruction || {};
    const acct = (x) => x ? `<span class="mono">${esc(x)}</span>` : '';
    switch (r.kind) {
      case 'verify': return e.decision === 'ALLOW' ? `${statusChip(r)} ${esc(i.supplier_name || '')} · <span class="mono">${gbp(i.amount)}</span>` : e.decision === 'ESCALATE' ? `${statusChip(r)} at ${esc(e.rule)} · ${esc(i.supplier_name || '')} · <span class="mono">${gbp(i.amount)}</span>` : `${statusChip(r)} at ${esc(e.rule)} ${esc(e.code)} · ${esc(i.supplier_name || '')} ${acct(i.payee_account_ref)} · <span class="mono">${gbp(i.amount)}</span>`;
      case 'decision': return e.first_payment ? `<b class="${e.outcome === 'RELEASED' ? 'ok' : 'hold'}">First payment under mandate version ${esc(String(e.mandate_version || 1))} ${e.outcome === 'RELEASED' ? 'confirmed' : 'refused'} by the customer</b> · ${esc(i.supplier_name || '')} · <span class="mono">${gbp(i.amount)}</span> · ${esc(e.officer || '')}` : `<b class="${e.outcome === 'RELEASED' ? 'ok' : 'hold'}">Held payment ${e.outcome === 'RELEASED' ? 'released' : 'refused'} by approver</b> · ${esc(i.supplier_name || '')} · <span class="mono">${gbp(i.amount)}</span> · ${esc(e.officer || '')} · ${esc(e.reason || '')}`;
      case 'intent': return `Intent declared before reading: pay ${esc(e.supplier_name || '')} to ${acct(e.declared_payee)}`;
      case 'agent': return e.attempted_payee ? (e.matches_intent ? `AI agent read the invoice: ${acct(e.attempted_payee)}, as declared` : `AI agent read the invoice: ${acct(e.attempted_payee)}, not the declared ${acct(e.declared_payee)}`) : 'Customer registered its AI agent: key generated, possession proven';
      case 'incident': return `<b class="bad">Incident raised</b> · ${e.denies} refusals`;
      case 'issue': return 'Passport issued: admission signed by the bank, list active';
      case 'mandate': return e.revoked ? `<b class="hold">Mandate revoked</b> by ${esc((e.signer || {}).name || 'the customer')} · ${esc(e.reason || '')}` : (e.version || 1) > 1 ? `<b>Mandate amended</b>: version ${e.version} signed by ${esc((e.signer || {}).name || 'the customer')}, supersedes version ${e.supersedes} · ${(e.changes || []).map(c => c.added ? `added ${esc(c.added.name)}` : c.removed ? `removed ${esc(c.removed.name)}` : `${esc(c.field.replace(/_/g, ' '))} ${esc(String(c.from))} to ${esc(String(c.to))}`).join(', ') || 'no field changed'}` : `Mandate signed by ${esc((e.signer || {}).name || 'the customer')} · ${e.suppliers} payees · ${gbp(e.per_payment_limit)} a payment`;
      case 'admission': return e.condition ? `Product admitted by ${esc(e.officer || 'the bank')} · hold above ${gbp(e.condition.hold_above.amount)}` : esc(e.event);
      case 'check': return `Product filed on the register · ${e.passed} of ${e.total || 7} checks pass · receipt signed`;
      case 'registration': return 'Registration started by the provider';
      case 'review': return `Admission review run · sandbox ${e.sandbox_passed} of ${e.sandbox_total} · ${esc(e.recommendation)}`;
      case 'vouch': return e.event.includes('revoked') ? 'Voucher revoked on the vouch rail' : `Voucher minted on the vouch rail (${esc(e.mode)})`;
      case 'lifecycle': return `${esc(e.event)} · ${esc(e.officer || '')}${e.reason ? ' · ' + esc(e.reason) : ''}`;
      case 'exception': return esc(e.event) + (e.outcome ? ' · ' + esc(e.outcome) : '');
      case 'evidence': return 'Evidence bundle exported for supervisory access';
      case 'draft': return 'File note drafted for the officer';
      case 'system': return esc(e.event);
      default: return esc(e.event || r.kind);
    }
  }
  function trailRows(tbody, rows, opts = {}) {
    tbody.innerHTML = '';
    rows.forEach(r => { const tr = el('tr', opts.newIds && opts.newIds.has(r.id) ? 'is-new' : null, `<td class="mono small">${t(r.ts)}</td><td>${plainEvent(r)}</td>${opts.subject ? `<td class="mono small">${esc(r.subject || '')}</td>` : ''}<td class="small"><span class="hash">#${r.id} ${esc(r.hash.slice(0, 10))}</span>${r.receipt ? ' · receipt' : ''}</td>`); tr.id = 'ev-' + r.id; tbody.append(tr); });
    if (!rows.length) tbody.append(el('tr', null, `<td colspan="${opts.subject ? 4 : 3}" class="empty-row">Nothing recorded yet.</td>`));
  }

  function home() {
    const ink = '#0b0c0c', ink2 = '#505a5f', blue = '#0f6b73', line = '#e5e7e8', font = '"Helvetica Neue", Arial, Helvetica, sans-serif';
    if (window.Chart) {
      Chart.defaults.font.family = font; Chart.defaults.font.size = 13; Chart.defaults.color = ink2;
      const values = { id: 'values', afterDatasetsDraw(c) { const { ctx } = c; ctx.save(); ctx.font = `600 14px ${font}`; ctx.fillStyle = ink; ctx.textAlign = 'center'; c.getDatasetMeta(0).data.forEach((bar, i) => { const dd = c.data.datasets[0]; ctx.fillText(dd.labelsText ? dd.labelsText[i] : dd.data[i], bar.x, bar.y - 8); }); ctx.restore(); } };
      const bars = (id, labels, data, labelsText, notes, opts = {}) => new Chart($(id), { type: 'bar', plugins: [values], data: { labels, datasets: [{ data, labelsText, backgroundColor: data.map((_, i) => opts.proj && i >= opts.proj ? '#fff' : blue), borderColor: blue, borderWidth: data.map((_, i) => opts.proj && i >= opts.proj ? 2 : 0), borderDash: [6, 4], borderSkipped: false, borderRadius: 4, maxBarThickness: 160, categoryPercentage: .7 }] },
        options: { animation: { duration: 700 }, responsive: true, maintainAspectRatio: false, layout: { padding: { top: 24, bottom: 4 } }, plugins: { legend: { display: false }, tooltip: { enabled: false } },
          scales: { x: { grid: { display: false }, border: { color: line }, ticks: { color: ink, font: { size: 14 }, callback: (v_, i) => notes && notes[i] ? [labels[i], notes[i]] : labels[i] } }, y: { beginAtZero: true, max: opts.max, grid: { color: line }, border: { display: false }, ticks: { stepSize: opts.step } } } } });
      if ($('chart-shift')) {
        const pts = [{ x: 2024, y: 229 }, { x: 2025, y: 262 }, { x: 2030, y: 1500 }];
        const lbl = { 229: '$229bn', 262: '$262bn', 1500: '$1.5tn' };
        const pointLabels = { id: 'pointLabels', afterDatasetsDraw(c) { const { ctx } = c; ctx.save(); ctx.font = `600 14px ${font}`; ctx.fillStyle = ink; ctx.textAlign = 'center'; c.getDatasetMeta(0).data.forEach((pt, i) => { ctx.fillText(lbl[pts[i].y], pt.x, pt.y - 14); }); ctx.restore(); } };
        new Chart($('chart-shift'), { type: 'line', plugins: [pointLabels], data: { datasets: [{ data: pts, borderColor: blue, backgroundColor: 'rgba(15,107,115,.12)', fill: true, tension: .45, borderWidth: 3, pointRadius: 6, pointBackgroundColor: blue, pointBorderColor: '#fff', pointBorderWidth: 2, segment: { borderDash: (s) => s.p1.parsed.x > 2025 ? [8, 6] : undefined } }] },
          options: { animation: { duration: 900 }, responsive: true, maintainAspectRatio: false, layout: { padding: { top: 28, right: 24 } }, plugins: { legend: { display: false }, tooltip: { enabled: false } },
            scales: { x: { type: 'linear', min: 2023.6, max: 2030.4, grid: { display: false }, border: { color: line }, afterBuildTicks: (ax) => { ax.ticks = [2024, 2025, 2026, 2027, 2028, 2029, 2030].map(value => ({ value })); }, ticks: { color: ink, font: { size: 14 }, callback: (v_) => String(v_) } }, y: { beginAtZero: true, max: 1600, grid: { color: line }, border: { display: false }, ticks: { stepSize: 400 } } } } });
      }
      if ($('chart-app')) bars('chart-app', ['2021', '2022', '2023', '2024', '2025'], [583, 485, 460, 451, 576], ['£583m', '£485m', '£460m', '£451m', '£576m'], null, { max: 700, step: 175 });
    }
    if (window.mermaid) {
      mermaid.initialize({ startOnLoad: false, theme: 'base', securityLevel: 'loose', fontFamily: font, themeVariables: { primaryColor: '#ffffff', primaryBorderColor: ink, primaryTextColor: ink, lineColor: ink, secondaryColor: '#f3f2f1', tertiaryColor: '#f3f2f1', fontSize: '16px', fontFamily: font },
        flowchart: { htmlLabels: true, curve: 'basis', nodeSpacing: 34, rankSpacing: 52, padding: 12, useMaxWidth: true } });
      mermaid.run({ querySelector: '.mermaid' });
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    const mt = $('menu-toggle'), mp = $('menu-panel');
    if (mt && mp) {
      mt.onclick = () => { const open = mp.hidden; mp.hidden = !open; mt.setAttribute('aria-expanded', String(open)); mt.classList.toggle('is-open', open); };
      const close = () => { mp.hidden = true; mt.setAttribute('aria-expanded', 'false'); mt.classList.remove('is-open'); };
      document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !mp.hidden) { close(); mt.focus(); } });
      document.addEventListener('click', (e) => { if (!mp.hidden && !e.target.closest('#menu-panel, #menu-toggle')) close(); });
    }
    const rb = $('demo-reset');
    if (rb) rb.onclick = async () => { if (confirm('Reset the demo to its baseline? Everything is deleted, then one AI product is filed on the register, admitted by the bank, and the customer mandate signed, so one passport is ACTIVE with a short history: the first payment confirmed by the customer, one payment made, its replay refused, one wrong-currency instruction refused, one payment held for the approver.')) { rb.disabled = true; rb.textContent = 'seeding…'; await api('POST', '/api/demo/seed?stage=history'); location.href = '/terminal'; } };
  });

  // ───────────── the dashboards' extras: greeting, balance toggle, the customer's chart, the quiet pane ─────────────
  const greet = () => { const h = new Date().getHours(); return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'; };
  function dashExtras() {
    if ($('fx-greet')) $('fx-greet').textContent = greet();
    const nav = document.querySelector('.fx-nav');
    if (nav && !document.querySelector('.fx-nav .acct__tab')) {
      const links = [...nav.querySelectorAll('a[href^="#"]')];
      const targets = links.map(a => document.getElementById(a.getAttribute('href').slice(1))).filter(Boolean);
      const mark = () => { let cur = links[0]; const y = window.scrollY + 140; targets.forEach((t_, i) => { if (t_.offsetTop <= y) cur = links[i]; }); links.forEach(a => a.removeAttribute('aria-current')); if (cur) cur.setAttribute('aria-current', 'page'); };
      links.forEach(a => { a.onclick = (e) => { const t_ = document.getElementById(a.getAttribute('href').slice(1)); if (!t_) return; e.preventDefault(); if (t_.tagName === 'DETAILS') t_.open = true; t_.scrollIntoView({ behavior: 'smooth', block: 'start' }); links.forEach(x => x.removeAttribute('aria-current')); a.setAttribute('aria-current', 'page'); }; });
      window.addEventListener('scroll', mark, { passive: true });
    }
    const meta = $('fx-agents-meta'), src = $('bd-agents-meta');
    if (meta && src) setInterval(() => { meta.textContent = src.textContent; }, 1000);
  }
  function customerExtras() {
    dashExtras();
    const eye = $('fx-eye'); if (eye) eye.onclick = () => { const on = $('fx-balance').classList.toggle('is-hidden'); eye.setAttribute('aria-pressed', String(on)); eye.setAttribute('aria-label', on ? 'Show the balance' : 'Hide the balance'); };
    // the quiet pane shows only while there is nothing to notify
    const notify = $('cu-notify'), quiet = $('fx-quiet');
    if (notify && quiet) { const sync = () => { quiet.hidden = !notify.hidden; }; new MutationObserver(sync).observe(notify, { attributes: true, attributeFilter: ['hidden'] }); sync(); }
    let chart = null;
    async function tick() {
      if (document.hidden) return;
      const st = await api('GET', '/api/state');
      const name = ((st.mandate_draft || {}).authorising_officer || {}).name; if (name && $('fx-name')) $('fx-name').textContent = name.split(' ')[0];
      const pays = [...(st.payments || [])].sort((a, b) => (a.ts < b.ts ? -1 : 1));
      const viol = st.violations || [];
      const total = pays.reduce((s, x) => s + Number(x.amount || 0), 0);
      if ($('fx-cu-stats')) $('fx-cu-stats').innerHTML = [[gbp(total), 'Paid by AI agents'], [String(pays.length), 'Payments'], [String(viol.filter(x => x.failure_class === 'fraud').length), 'Stopped by the bank'], [String(viol.filter(x => x.failure_class !== 'fraud').length), 'Agent errors']].map(([n, l]) => `<li><b>${esc(n)}</b><span>${l}</span></li>`).join('');
      if (!window.Chart || !$('chart-customer')) return;
      $('fx-chart-empty').hidden = pays.length > 0;
      // cumulative value paid, one point per payment, so the curve reads as money leaving under mandate
      let run = 0; const labels = [], data = [];
      pays.forEach(x => { run += Number(x.amount || 0); labels.push(t(x.ts)); data.push(run); });
      if (!labels.length) { labels.push(t(new Date().toISOString())); data.push(0); }
      if (!chart) {
        const ctx = $('chart-customer').getContext('2d'); const g = ctx.createLinearGradient(0, 0, 0, 200); g.addColorStop(0, 'rgba(15,107,115,.28)'); g.addColorStop(1, 'rgba(15,107,115,0)');
        Chart.defaults.font.family = getComputedStyle(document.body).fontFamily; Chart.defaults.font.size = 12; Chart.defaults.color = '#66736f';
        chart = new Chart($('chart-customer'), { type: 'line', data: { labels, datasets: [{ data, borderColor: '#0f6b73', borderWidth: 2.5, fill: true, backgroundColor: g, tension: .45, pointRadius: 0, pointHoverRadius: 5, pointHoverBackgroundColor: '#c9f26b', pointHoverBorderColor: '#0f6b73' }] },
          options: { animation: { duration: 400 }, responsive: true, maintainAspectRatio: false, interaction: { intersect: false, mode: 'index' }, plugins: { legend: { display: false }, tooltip: { backgroundColor: '#0f1a17', cornerRadius: 10, padding: 10, displayColors: false, callbacks: { label: (c) => gbp(c.parsed.y) + ' paid so far' } } },
            scales: { x: { grid: { display: false }, border: { display: false }, ticks: { maxTicksLimit: 6, color: '#97a39f' } }, y: { beginAtZero: true, grid: { color: '#eef1f0' }, border: { display: false, dash: [4, 4] }, ticks: { maxTicksLimit: 5, color: '#97a39f', callback: (v_) => gbp(v_) } } } } });
      } else { chart.data.labels = labels; chart.data.datasets[0].data = data; chart.update('none'); }
    }
    tick(); setInterval(tick, 5000);
  }

  function bankExtras() { const meta = $('fx-agents-meta'), src = $('bd-agents-meta'); if (meta && src) setInterval(() => { meta.textContent = src.textContent; }, 1000); }

  return { home, provider, bank, customer, console: console_, dashExtras, customerExtras, bankExtras };
})();
