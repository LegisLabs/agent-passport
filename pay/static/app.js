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

  const LABELS = {
    company: { title: 'Provider', legal_name: 'Legal name', companies_house_number: 'Companies House number', website: 'Website' },
    principal: { title: 'Accountable principal', name: 'Name', role: 'Role', declaration_ref: 'Declaration reference' },
    insurance: { title: 'Insurance', insurer: 'Insurer', policy_ref: 'Policy reference', cover_gbp: 'Cover (£)', expires: 'In force until' },
    product: { title: 'The AI product', product_name: 'Product name', product_id: 'Product identifier', release: 'Release', model_provider: 'Foundation model provider', model_version: 'Foundation model version (pinned)', documentation_url: 'Documentation (URL)' },
    assurance_evidence: { title: 'Independent Assurance Evidence', issuer: 'Issuer', reference: 'Reference', date: 'Date', use_case: 'Use case covered', summary: 'What it covers', report_url: 'Report (URL)' },
    intended_use: { title: 'Registered use', action_type: 'Action type', description: 'Description' },
  };
  const SECTION_HINTS = {
    principal: 'The person who declares this filing accurate, as for a Companies House filing. Accountable for the filing, not for what any AI agent later does.',
    assurance_evidence: 'An independent benchmark or audit that the product meets the minimum assurance requirements for its use case. It is attached, not assessed, by the register; each bank assesses it against its own requirements.',
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
        ...regs.map(x => ({ cells: [`<a href="/provider?ref=${x.ref}">${esc(x.ref)}</a>`, esc(v(x.fields, 'product', 'product_name') || 'Untitled'), esc(v(x.fields, 'company', 'legal_name') || ''), d(x.submitted_at), regTag(x), admissionTag(x)] })),
        ...prior.map(m => ({ cells: [esc(m.registration), esc(m.product), esc(m.provider), d(m.registered), tag(m.status, m.status === 'active' ? 'on the register' : m.status), '<span class="small">no decision</span>'] })),
      ], 6);
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
          const input = `<input class="input" data-sec="${sec}" data-key="${k}" value="${esc(fact.value ?? '')}" ${editable ? '' : 'disabled'} aria-label="${esc(label)}">`;
          dl.append(el('div', 'fact', `<dt>${esc(label)}</dt><dd>${input}</dd>`));
        }
        box.append(dl);
      }
      $('btn-save-fields').hidden = !editable;
    }

    function collectFields() {
      const f = JSON.parse(JSON.stringify(a.fields));
      document.querySelectorAll('#facts [data-sec]').forEach(inp => {
        const cur = f[inp.dataset.sec][inp.dataset.key] || (f[inp.dataset.sec][inp.dataset.key] = {});
        cur.value = inp.value === '' ? null : (NUMERIC.has(inp.dataset.key) && !isNaN(inp.value) ? Number(inp.value) : inp.value);
      });
      return f;
    }

    $('btn-new').onclick = async () => { a = await api('POST', '/api/registrations'); history.replaceState(null, '', `?ref=${a.ref}`); await refresh(); };
    $('btn-prefill').onclick = async () => { a = await api('POST', `/api/registrations/${a.id}/prefill`); await refresh(); };
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
    let state = await api('GET', '/api/state');
    const q = new URLSearchParams(location.search);
    const issued = () => state.passports.filter(x => x.status !== 'pending');
    let p = q.get('passport') ? issued().find(x => x.passport_id === q.get('passport')) || null : null;
    let a = p ? state.registrations.find(x => x.id === p.registration_id) : (q.get('ref') ? state.registrations.find(x => x.ref === q.get('ref') && x.status !== 'draft') || null : null);
    const mode = p ? 'agent' : a ? 'case' : 'dash';
    let selectedVid = null;
    render();

    async function refresh() { state = await api('GET', '/api/state'); if (a) a = state.registrations.find(x => x.id === a.id) || a; render(); }
    function passportFor() { return p ? (state.passports.find(x => x.passport_id === p.passport_id) || p) : null; }
    const who = () => state.cast ? `${state.cast.officer}, ${state.cast.team}` : '';

    function render() {
      $('bk-dash').hidden = mode !== 'dash'; $('bk-case').hidden = mode !== 'case'; $('bk-agent').hidden = mode !== 'agent';
      p = passportFor();
      $(mode === 'agent' ? 'bk-agent-anomaly' : 'bk-dash-anomaly').append($('bk-anomaly'));
      $(mode === 'agent' ? 'bk-agent-history' : 'bk-case-history').append($('bk-history-wrap'));
      $('bk-anomaly').hidden = mode === 'case'; $('bk-history-wrap').hidden = mode === 'dash';
      if (mode === 'dash') renderDash(); else if (mode === 'agent') renderAgent(); else renderCase();
      renderExceptions();
      renderIncidents();
      renderHistory();
    }
    function renderDash() {
      const regs = state.registrations.filter(x => x.status !== 'draft'), live = issued(), viol = state.violations || [], inc = state.incidents || [];
      const todo = regs.filter(x => !x.admission_status || x.admission_status === 'info_requested');
      const paid = (state.payments || []).reduce((s, x) => s + Number(x.amount || 0), 0);
      $('bk-stats').innerHTML = [[live.filter(x => x.status === 'active').length, 'live AI agents'], [todo.length, 'awaiting your admission decision'], [gbp(paid), 'executed in 30 days'], [viol.filter(x => x.status === 'OPEN').length, 'open refusals'], [inc.length, 'incidents']].map(([n, l]) => `<li><b>${n}</b><span>${l}</span></li>`).join('');
      $('bk-todo').hidden = !todo.length;
      $('bk-todo').innerHTML = todo.map(x => `<span><strong>${esc(v(x.fields, 'product', 'product_name') || x.ref)}</strong> by ${esc(v(x.fields, 'company', 'legal_name') || '')} is on the register and awaits your admission decision.</span><a class="btn btn--small" href="/bank?ref=${x.ref}">Open ${esc(x.ref)}</a>`).join('');
      rows('bk-agents', live.map(x => { const ag = (x.agent_identity || {}).agent || {}, mp = x.mandate_proposed || {}; const tot = Object.values(x.ledger || {}).reduce((s, y) => s + y.total, 0); const nv = viol.filter(y => y.passport_id === x.passport_id).length; return { cells: [`<a href="/bank?passport=${x.passport_id}">${esc(x.passport_id)}</a>`, esc(ag.name || ''), esc((mp.customer || {}).legal_name || ''), esc(ag.product_name || ''), gbp(tot), nv ? `<span class="tag tag--${nv >= 2 ? 'red' : 'amber'}">${nv}</span>` : '0', tag(x.status)] }; }), 7, 'No AI agent has a passport on your list yet.');
      rows('bk-products', regs.filter(x => x.admission_status && x.admission_status !== 'declined' && x.admission_status !== 'info_requested').map(x => { const pr = (state.products || []).find(y => y.registration_id === x.id) || { passports: [] }; return { cells: [`<a href="/bank?ref=${x.ref}">${esc(x.ref)}</a>`, esc(v(x.fields, 'product', 'product_name') || ''), esc(v(x.fields, 'company', 'legal_name') || ''), d(x.admitted_at), holdOf(x) != null ? gbp(holdOf(x)) : '—', String(pr.passports.length), admissionTag(x)] }; }), 7, 'No product admitted yet.');
      rows('bk-register', [
        ...regs.map(x => ({ cells: [`<a href="/bank?ref=${x.ref}">${esc(x.ref)}</a>`, esc(v(x.fields, 'product', 'product_name') || ''), esc(v(x.fields, 'company', 'legal_name') || ''), d(x.submitted_at), `${(x.checks || []).filter(c => c.result === 'pass').length} of ${(x.checks || []).length} pass`, admissionTag(x)] })),
        ...(state.register || []).map(m => ({ cells: [esc(m.registration), esc(m.product), esc(m.provider), d(m.registered), '6 of 6 pass', tag('grey', m.status === 'active' ? 'not on your list' : m.status)] })),
      ], 6);
      const ev = $('bk-evidence'); ev.innerHTML = '';
      live.forEach(x => ev.append(el('li', null, `<span><span class="mono">${esc(x.passport_id)}</span> · complete evidence bundle: filing, admission, agent identity, mandate, every verification, chain segment</span><a class="btn btn--secondary btn--small" href="/api/evidence/passports/${esc(x.passport_id)}" target="_blank" rel="noopener">Export JSON</a>`)));
      viol.slice(0, 5).forEach(x => ev.append(el('li', null, `<span>Refusal #${x.id} · <span class="mono">${esc(x.rule)} ${esc(x.code)}</span> on <span class="mono">${esc(x.passport_id)}</span> · ${t(x.ts)}</span><a class="btn btn--secondary btn--small" href="/api/evidence/violations/${x.id}" target="_blank" rel="noopener">Export JSON</a>`)));
      if (!live.length && !viol.length) ev.append(el('li', 'small', 'Nothing to export yet.'));
    }
    function renderCase() {
      $('bk-ref').textContent = a.ref;
      $('bk-status').innerHTML = admissionTag(a);
      const f = a.fields;
      $('bk-summary').innerHTML = [
        ['Provider', `${esc(v(f, 'company', 'legal_name'))} · Companies House <span class="mono">${esc(v(f, 'company', 'companies_house_number'))}</span> · ${esc(v(f, 'company', 'website'))}`],
        ['Accountable principal', `${esc(v(f, 'principal', 'name'))}, ${esc(v(f, 'principal', 'role'))} · declaration <span class="mono">${esc(v(f, 'principal', 'declaration_ref'))}</span> · accountable for the accuracy of the filing`],
        ['Insurance', `${esc(v(f, 'insurance', 'insurer'))} · policy <span class="mono">${esc(v(f, 'insurance', 'policy_ref'))}</span> · cover ${gbp(v(f, 'insurance', 'cover_gbp'))} · in force until ${esc(v(f, 'insurance', 'expires'))}`],
        ['AI product', `<strong>${esc(v(f, 'product', 'product_name'))}</strong> <span class="mono">${esc(v(f, 'product', 'product_id'))}</span> · release ${esc(v(f, 'product', 'release'))} · ${esc(v(f, 'product', 'model_provider'))} <span class="mono">${esc(v(f, 'product', 'model_version'))}</span> · <a href="${esc(v(f, 'product', 'documentation_url'))}">documentation</a>`],
        ['Independent Assurance Evidence', `${esc(v(f, 'assurance_evidence', 'issuer'))} · <span class="mono">${esc(v(f, 'assurance_evidence', 'reference'))}</span> · ${esc(v(f, 'assurance_evidence', 'date'))} · use case <span class="mono">${esc(v(f, 'assurance_evidence', 'use_case'))}</span><span class="sub">${esc(v(f, 'assurance_evidence', 'summary'))} · <a href="${esc(v(f, 'assurance_evidence', 'report_url'))}">report</a></span>`],
        ['Registered use', `<strong>${esc(v(f, 'intended_use', 'action_type'))}</strong> · ${esc(v(f, 'intended_use', 'description'))} · no customer named: each customer writes its own mandate within your ceilings`],
        ['Register receipt', a.registration_jwt ? `signed by the register <span class="mono small">${esc(a.registration_jwt.slice(0, 24))}…</span> · filed ${d(a.submitted_at)}` : '—'],
      ].map(([k, val]) => `<div><dt>${k}</dt><dd>${val}</dd></div>`).join('');
      const pol = state.policy || {};
      $('bk-ceilings').textContent = `per payment ≤ ${gbp(pol.per_payment_ceiling_gbp)} · per account in 30 days ≤ ${gbp(pol.monthly_per_account_ceiling_gbp)} · expiry ≤ ${pol.max_validity} · actions ${(pol.action_types || []).join(', ')}`;
      checksTable('bk-checks', a.checks);
      $('bk-filenote').value = a.file_note || '';
      if (pol.hold_above_gbp && !$('bk-condition').dataset.touched) $('bk-condition').value = pol.hold_above_gbp;
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
        if (st.id === 'recommendation') { const dd = st.data; badge = `<span class="tag tag--blue">${esc(dd.label)}</span>`; body = `<p class="verdict verdict--${dd.verdict.startsWith('ADMIT') ? 'approve' : 'refer'}">${esc(dd.verdict)}</p><ul>${dd.reasons.map(x => `<li>${esc(x)}</li>`).join('')}</ul><p class="small">Draft note (${esc(modeLabel(dd.narrative_mode))}): ${esc(dd.narrative)}</p>`; if ($('bk-condition') && !$('bk-condition').dataset.touched) $('bk-condition').value = dd.condition.hold_above; }
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
      $('ex-meta').textContent = mine.length ? `${mine.length} refusals · ${mine.filter(x => x.status === 'OPEN').length} open` : 'no refusals';
      const tb = $('bk-violations').querySelector('tbody'); tb.innerHTML = '';
      mine.forEach(x => { const tr = el('tr', null, `<td>${t(x.ts)}</td><td class="mono small">${esc(x.agent_id || '')}${p ? '' : `<br><a href="/bank?passport=${esc(x.passport_id)}">${esc(x.passport_id)}</a>`}</td><td><span class="mono">${esc(x.rule)}</span><br><span class="small">${esc(x.code)}</span></td><td>${esc(x.instruction.action_type)} · ${esc(x.instruction.supplier_name || '')} · <span class="mono">${esc(x.instruction.payee_account_ref || '')}</span> · ${gbp(x.instruction.amount)}${x.evidence ? ` <span class="tag tag--grey">invoice ${esc(x.evidence.invoice)}</span>` : ''}</td><td>${tag('revoked', x.outcome)}</td><td>${tag(x.status, x.status)}${x.resolution ? `<br><span class="small">${esc(x.resolution)}</span>` : ''}</td>`); tr.dataset.vid = x.id; tr.setAttribute('aria-selected', String(x.id === selectedVid)); tr.onclick = () => { selectedVid = x.id; renderEvidence(x); renderExceptions(); }; tb.append(tr); });
      if (!mine.length) tb.append(el('tr', null, '<td colspan="6" class="empty-row">Nothing refused. Every instruction the verifier refuses appears here with its rule, the reason and the evidence that produced it.</td>'));
      const ex = $('exception'); ex.hidden = !p; if (!p) return;
      const inv = p.investigation === 'investigating';
      $('ex-state').innerHTML = `<span class="stamp stamp--${p.status === 'active' ? 'green' : p.status === 'suspended' ? 'amber' : 'red'}">${esc(p.status)}</span>${inv ? '<span class="stamp stamp--amber">investigating</span>' : ''}<span class="small">${p.status === 'suspended' ? 'payments blocked at R.2 while you look' : p.status === 'revoked' ? 'closed; passport list REVOKED, vouch voucher revoked' : 'payments flow; the verifier reads the list on every instruction'}${inv ? ' · investigating blocks nothing by itself; the list status does' : ''}</span>`;
      const act = $('ex-actions'); act.innerHTML = '';
      const btn = (label, cls, fn) => { const b = el('button', 'btn btn--small ' + cls, label); b.type = 'button'; b.onclick = fn; act.append(b); };
      const reason = () => $('bk-reason').value.trim() || 'via the exception panel';
      if (p.status === 'active') btn('Suspend', 'btn--secondary', () => lifeFrom('suspended', reason()));
      if (p.status !== 'revoked' && !inv) btn('Open investigation', 'btn--secondary', async () => { await api('POST', `/api/passports/${p.passport_id}/investigation`, { action: 'open', note: reason() }); await refresh(); });
      if (p.status !== 'revoked') btn('Revoke', 'btn--warning', () => lifeFrom('revoked', reason()));
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
      ev.innerHTML = `<strong>Refusal #${x.id} · ${esc(x.rule)} ${esc(x.code)} · ${t(x.ts)}</strong><div>Instruction: ${esc(x.instruction.action_type)} · ${esc(x.instruction.supplier_name || '')} · <span class="mono">${esc(x.instruction.payee_account_ref || '')}</span> · ${gbp(x.instruction.amount)} · invoice ${esc(x.instruction.invoice_ref || '—')} · evidence entry #${x.audit_id} · <a href="/api/evidence/violations/${x.id}" target="_blank" rel="noopener">export bundle</a></div>` +
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

  // ───────────── Customer: my AI agents ─────────────
  async function customer() {
    let state = await api('GET', '/api/state');
    const ref = new URLSearchParams(location.search).get('ref');
    let p = state.passports.find(x => x.passport_id === ref) || null;
    const d0 = state.mandate_draft || { customer: {}, authorising_officer: {} };
    const draft = JSON.parse(JSON.stringify(d0)); let checkTimer = null;
    render();

    function render() {
      const products = (state.products || []).filter(m => m.admission_status === 'admitted');
      rows('cu-agents', state.passports.map(x => { const ag = (x.agent_identity || {}).agent || {}; const tot = Object.values(x.ledger || {}).reduce((s, y) => s + y.total, 0); return { cells: [`<a href="/customer?ref=${x.passport_id}">${esc(x.passport_id)}</a>`, esc(ag.name || ''), `${esc(ag.product_name || '')} <span class="small">by ${esc(ag.provider || '')}</span>`, gbp(tot), x.status === 'pending' ? tag('unsigned', 'awaiting your signature') : tag(x.status, x.status)] }; }), 5, 'No AI agent yet.');
      $('cu-empty').hidden = !!(products.length || p);
      $('cu-create').hidden = !products.length;
      const sel = $('cu-model'); sel.innerHTML = products.map(m => `<option value="${m.registration_id}">${esc(m.product_name)} · ${esc(m.provider)} · ${esc(m.model_version)}</option>`).join('');
      if (!$('cu-agent-name').value) $('cu-agent-name').value = (state.agent_draft || {}).agent_name || '';
      $('cu-mandate').hidden = !p;
      if (!p) return;
      const mp = p.mandate_proposed, ad = mp.authorization_details[0], signed = p.mandate_signed, ag = p.agent || {};
      $('cu-agent-kv').innerHTML = [['AI agent', `<strong>${esc(p.agent_identity.agent.name)}</strong> · <span class="mono">${esc(mp.agent_id)}</span> · ${esc(p.agent_identity.agent.product_name)} by ${esc(p.agent_identity.agent.provider)} (${esc(p.agent_identity.agent.model_provider)} <span class="mono">${esc(p.agent_identity.agent.model_version)}</span>)`], ['Its key', `<span class="mono">kid ${esc(mp.agent_kid)}</span> · ${ag.pop_verified ? '<span class="tag tag--green">possession proven</span>' : '<span class="tag tag--amber">possession pending</span>'} · config <span class="mono small">${esc((ag.config_sha256 || '').slice(0, 12))}…</span>`], [p.status === 'pending' ? 'Record' : 'Passport', `<span class="mono">${esc(p.passport_id)}</span> ${tag(p.status)} · ${p.status === 'pending' ? 'the passport is issued when you sign the mandate' : 'issued by the bank when you signed'}`]].map(([k, val]) => `<div><dt>${k}</dt><dd>${val}</dd></div>`).join('');
      $('cu-id').textContent = p.passport_id; $('cu-ref').textContent = p.passport_id;
      $('cu-state').innerHTML = signed ? tag('signed', 'signed') : tag('unsigned', 'awaiting signature');
      $('cu-card').classList.toggle('mandate--signed', signed);
      $('cu-kv').innerHTML = [['Account holder', `${esc((mp.customer || d0.customer).legal_name)} · Companies House <span class="mono">${esc((mp.customer || d0.customer).companies_house_number)}</span>`], ['Signatory', `${esc((mp.authorising_officer || d0.authorising_officer).name)}, ${esc((mp.authorising_officer || d0.authorising_officer).role)}`], ['Bank hold', `the bank holds anything above ${gbp(p.admission.condition.hold_above.amount)} for your confirmation`]].map(([k, val]) => `<div><dt>${k}</dt><dd>${val}</dd></div>`).join('');
      renderMandateForm(p, signed, ad, mp);
      renderActivity(p);
    }
    async function renderActivity(p) {
      const wrap = $('cu-activity-wrap'); if (p.status === 'pending') { wrap.hidden = true; return; }
      const data = await api('GET', '/api/audit');
      const mine = data.rows.filter(r => r.kind === 'verify' && r.subject === p.passport_id);
      const tb = $('cu-activity').querySelector('tbody'); tb.innerHTML = '';
      mine.forEach(r => { const e = r.entry, i = e.instruction || {}; tb.append(el('tr', null, `<td class="mono small">${t(r.ts)}</td><td>${esc(i.action_type)} · ${esc(i.supplier_name || '')} · <span class="mono">${esc(i.payee_account_ref || '')}</span> · ${gbp(i.amount)}</td><td>${e.decision === 'ALLOW' ? tag('active', 'paid') : e.decision === 'ESCALATE' ? tag('pending', 'held for you') : tag('revoked', 'refused')}</td><td class="small">${esc(e.reason)}</td>`)); });
      if (!mine.length) tb.append(el('tr', null, '<td colspan="4" class="empty-row">No payments yet.</td>'));
      wrap.hidden = false;
    }
    $('btn-create-agent').onclick = async () => {
      const b = $('btn-create-agent'); b.disabled = true; $('cu-create-error').hidden = true; $('cu-create-note').textContent = 'generating key, signing the bank\'s challenge…';
      try { const np = await api('POST', '/api/agents', { registration_id: Number($('cu-model').value), agent_name: $('cu-agent-name').value.trim() || null }); state = await api('GET', '/api/state'); p = state.passports.find(x => x.passport_id === np.passport_id); history.replaceState(null, '', `?ref=${p.passport_id}`); render(); }
      catch (e) { $('cu-create-error').textContent = e.message; $('cu-create-error').hidden = false; }
      finally { b.disabled = false; $('cu-create-note').textContent = ''; }
    };
    function renderMandateForm(p, signed, ad, mp) {
      const ce = mp.ceilings || p.admission.ceilings || {};
      $('cu-form').hidden = signed || p.status === 'revoked';
      $('cu-suppliers-signed').hidden = !signed;
      if (signed) {
        const tb = $('cu-suppliers-signed').querySelector('tbody'); tb.innerHTML = '';
        ad.supplier_allowlist.forEach(s => tb.append(el('tr', null, `<td><span class="mono">${esc(s.supplier_id)}</span> ${esc(s.name)}</td><td class="mono">${esc(s.account_ref)}</td>`)));
        $('cu-kv').insertAdjacentHTML('beforeend', [['May', `<strong>${esc(ad.actions.join(', '))}</strong> in ${esc(ad.currency)}`], ['Per payment', `not more than ${gbp(ad.per_payment_limit.amount)}`], ['Per supplier account', `not more than ${gbp(ad.monthly_limit_per_account.amount)} in any rolling 30 days`], ['Expires', esc(mp.valid_until)]].map(([k, val]) => `<div><dt>${k}</dt><dd>${val}</dd></div>`).join(''));
        $('cu-containment').className = 'containment containment--ok'; $('cu-containment').textContent = 'Within the limits your bank set for this product. Checked at signing; the bank checks every payment against this mandate.';
      } else {
        $('cu-kv').insertAdjacentHTML('beforeend', `<div><dt>Bank's limits for this product</dt><dd>per payment ≤ ${gbp((ce.per_payment_ceiling || {}).amount)} · per supplier account in 30 days ≤ ${gbp((ce.monthly_per_account_ceiling || {}).amount)} · expiry ≤ ${esc(ce.max_validity || '')}</dd></div>`);
        renderForm(); runCheck();
      }
      $('cu-signer').textContent = `${(draft.authorising_officer || {}).name}, ${(draft.authorising_officer || {}).role}, signs with the ${(draft.customer || {}).legal_name} key.`;
      $('cu-actions').hidden = signed || p.status === 'revoked';
      $('cu-sig').hidden = !signed;
      if (signed) $('cu-sig').innerHTML = `<strong>Signed ${d(p.mandate_signed_at)} at ${t(p.mandate_signed_at)} by ${esc((p.mandate.signed_by || {}).name)}, ${esc((p.mandate.signed_by || {}).role)}</strong> Ed25519 signature by the ${esc((mp.customer || {}).legal_name)} key. The bank issued the passport, the list shows ACTIVE and the voucher is minted on the vouch rail. Live at once.`;
      $('cu-after').hidden = !signed;
      $('cu-jwt-wrap').hidden = !signed;
      if (signed) api('GET', `/api/passports/${p.passport_id}`).then(full => { $('cu-jwt-payload').textContent = JSON.stringify(full.mandate, null, 2); $('cu-jwt').textContent = full.envelope.mandate; });
    }
    function renderForm() {
      $('cu-per').value = draft.per_payment_limit; $('cu-monthly').value = draft.monthly_limit_per_account; $('cu-until').value = draft.valid_until;
      const tb = $('cu-suppliers').querySelector('tbody'); tb.innerHTML = '';
      (draft.supplier_allowlist || []).forEach((s, i) => tb.append(el('tr', null, `<td><span class="mono small">${esc(s.supplier_id || '')}</span> <input class="input" data-i="${i}" data-k="name" value="${esc(s.name)}" aria-label="Supplier name"></td><td><input class="input mono" data-i="${i}" data-k="account_ref" value="${esc(s.account_ref)}" aria-label="Account" placeholder="60-11-22 12345678"></td><td><button class="link small" type="button" data-remove="${i}">remove</button></td>`)));
    }
    function collect() {
      draft.per_payment_limit = Number($('cu-per').value); draft.monthly_limit_per_account = Number($('cu-monthly').value); draft.valid_until = $('cu-until').value;
      document.querySelectorAll('#cu-suppliers [data-i]').forEach(inp => { draft.supplier_allowlist[+inp.dataset.i][inp.dataset.k] = inp.value; });
      return draft;
    }
    async function runCheck() {
      if (!p) return;
      try {
        const r = await api('POST', `/api/passports/${p.passport_id}/mandate/check`, collect());
        const box = $('cu-containment'); box.className = 'containment ' + (r.within_ceilings ? 'containment--ok' : 'containment--bad');
        box.innerHTML = r.within_ceilings ? 'Within the limits your bank set for this product. Signing makes it live at once.' : `Outside the limits your bank set for this product. Signing is refused until this is fixed.<ul>${r.problems.map(x => `<li>${esc(x.problem)}</li>`).join('')}</ul>`;
        $('btn-sign-mandate').disabled = !r.within_ceilings;
      } catch (e) { $('cu-containment').textContent = e.message; }
    }
    const scheduleCheck = () => { clearTimeout(checkTimer); checkTimer = setTimeout(runCheck, 250); };
    $('cu-form').addEventListener('input', (e) => { if (e.target.matches('[data-i]')) collect(); scheduleCheck(); });
    $('cu-form').addEventListener('click', (e) => { const b = e.target.closest('[data-remove]'); if (b) { collect(); draft.supplier_allowlist.splice(+b.dataset.remove, 1); renderForm(); scheduleCheck(); } });
    $('cu-add').onclick = () => { collect(); draft.supplier_allowlist.push({ supplier_id: `SUP-${String(draft.supplier_allowlist.length + 1).padStart(3, '0')}`, name: '', account_ref: '' }); renderForm(); scheduleCheck(); };
    $('btn-sign-mandate').onclick = async () => {
      const b = $('btn-sign-mandate'); b.disabled = true; $('cu-error').hidden = true;
      try { const np = await api('POST', `/api/passports/${p.passport_id}/mandate/sign`, collect()); state = await api('GET', '/api/state'); p = state.passports.find(x => x.passport_id === np.passport_id); history.replaceState(null, '', `?ref=${np.passport_id}`); render(); }
      catch (e) { $('cu-error').textContent = typeof e.message === 'string' ? e.message : JSON.stringify(e.message); $('cu-error').hidden = false; b.disabled = false; }
    };
  }

  // ───────────── Expert console (/terminal?console=1) ─────────────
  // Presentation only: every verdict comes from POST /api/verify unchanged. The arena shows the nine checks
  // resolving in order (slowed for demonstration); the raw response is kept off-screen for the record and the tests.
  const SHORT = { 'R.1': 'bank admission signature', 'R.2': 'passport list status', 'R.3': 'agent identity signature', 'R.4': 'AI agent signature', 'R.5': 'customer mandate', 'R.6': 'payee on allowlist', 'R.7': 'per-payment limit', 'R.8': '30-day limit', 'R.9': 'bank hold condition', 'C.a': 'root scope', 'C.b': 'delegation ⊆ root', 'C.c': 'action ⊆ delegation' };
  async function console_() {
    const state = await api('GET', '/api/state');
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
      const vio = r.violation ? `<span>violation #${r.violation.id} recorded ${esc(r.violation.status)} <a href="/bank">→ Bank console</a></span>` : '';
      const inc = r.incident ? `<span class="fail"><b>INCIDENT</b> raised to the payments risk team · ${r.incident.denies} refused instructions <a href="/bank">→ Bank console</a></span>` : '';
      gVerdict.className = 'g__verdict g__verdict--' + r.decision; gWrap.dataset.decision = r.decision;
      gVerdict.innerHTML = `<span class="g-word">${r.decision}</span><span class="g-cite">${cite}</span><span class="g-reason">${esc(r.reason)}</span><span class="g-notes">${settle}${rails}${vio}${inc}<span class="tm-dim">${sig}receipt signed by the bank · evidence #${r.audit_id} <span class="mono">${esc(r.audit_hash.slice(0, 12))}</span> <a href="/audit">→ Evidence trail</a></span></span>`;
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
        const r = await api('POST', '/api/agent/act', { passport_id: p.passport_id, action_type: b.action_type, supplier_name: b.supplier_name, payee_account_ref: b.payee_account_ref, amount: b.amount, invoice_ref: b.repeat ? `${b.invoice_ref}-${k + 1}` : b.invoice_ref, signer: b.signer });
        await present(b, r, b.repeat ? k + 1 : null, k > 0);
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
        <span class="t-head"><span class="t-action">${esc(b.action_type)} · ${esc(b.supplier_name)} · ${esc(b.payee_account_ref)} · ${gbp(b.amount)}${k ? ' · #' + k : ''}${b.signer === 'rogue' ? ' · signed with rogue key' : ''}</span><span class="t-verdict t-verdict--${r.decision}">${r.decision}</span><span class="t-rule">${r.decision === 'ALLOW' ? 'all nine checks passed · ' + esc(r.code) : 'rule ' + esc(r.rule) + ' · ' + esc(r.code)}</span></span>
        <span class="t-reason">${esc(r.reason)}${r.decision === 'DENY' && r.rule === 'R.6' ? ' · Named-beneficiary mandate check (FATF 2025 AML/CFT alignment)' : ''}</span>${sigLine}${chainLine}${settle}${rails}
        <span class="t-trace">${trace}</span>
        <span class="t-meta">evidence #${r.audit_id} <b>${esc(r.audit_hash.slice(0, 12))}</b> ← <b>${esc(r.prev_hash.slice(0, 12))}</b> · rule pack <b>${esc(r.rule_pack)}</b> · receipt signed by the bank · decision replayable</span>
        <details class="receipt"><summary>receipt</summary>${esc(r.receipt)}</details></span>`);
    }
  }

  // ───────────── Evidence trail ─────────────
  async function audit() {
    const data = await api('GET', '/api/audit');
    $('au-count').textContent = data.rows.length;
    $('au-chain').innerHTML = data.chain.ok ? '<span class="tag tag--green">Intact</span>' : `<span class="tag tag--red">Broken at #${data.chain.broken_at}</span>`;
    $('au-head').textContent = (data.chain.head || '').slice(0, 16);
    const tb = $('au-table').querySelector('tbody'); tb.innerHTML = '';
    let run = 0, same = 0;
    const subjects = [...new Set(data.rows.filter(r => r.subject && r.subject.startsWith('AP-')).map(r => r.subject))];
    if (subjects.length) $('au-evidence').innerHTML = 'Supervisory access: ' + subjects.map(s => `<a href="/api/evidence/passports/${esc(s)}" target="_blank" rel="noopener">evidence bundle for ${esc(s)}</a>`).join(' · ');
    for (const r of data.rows) {
      const e = { ...r.entry }; delete e.ts; delete e.presented_envelope; if (e.instruction) { e.instruction = { ...e.instruction }; delete e.instruction.agent_signature; } delete e.trace;
      const extra = r.kind === 'verify' ? ` → <strong>${esc(e.decision)}</strong> ${esc(e.rule)} ${esc(e.code)}${e.ledger_total_before ? ` (ledger before ${gbp(e.ledger_total_before)})` : ''}` : '';
      tb.append(el('tr', null, `<td>${r.id}</td><td class="mono small">${t(r.ts)}</td><td>${esc(r.kind)}</td><td class="mono small">${esc(r.subject || '')}</td><td class="small">${esc(e.event || '')}${extra}${e.reason ? ` · ${esc(e.reason)}` : ''}${e.note ? ` · “${esc(e.note)}”` : ''}${e.detail ? ` · ${esc(e.detail)}` : ''}</td><td class="hash">${esc(r.hash.slice(0, 12))}<br>← ${esc(r.prev_hash.slice(0, 12))}</td><td class="small" id="au-r-${r.id}">${r.receipt ? '<span class="tag tag--green">receipt</span> ' : ''}${r.kind === 'verify' ? `<button class="link" data-replay="${r.id}" type="button">replay</button>` : ''}</td>`));
    }
    async function replay(id) {
      const rp = await api('POST', `/api/audit/${id}/replay`);
      run++; if (rp.identical) same++;
      $(`au-r-${id}`).innerHTML = `<span class="${rp.identical ? 'ok' : 'bad'}">${rp.identical ? 'identical' : 'DIFFERS'}</span> <span class="small">${esc(rp.replay.decision)} ${esc(rp.replay.rule)}</span>`;
      $('au-replays').textContent = `${run} run · ${same} identical`;
    }
    tb.addEventListener('click', e => { const b = e.target.closest('[data-replay]'); if (b) replay(+b.dataset.replay); });
    const replayAll = async () => { run = 0; same = 0; for (const r of data.rows.filter(x => x.kind === 'verify')) await replay(r.id); $('replay-note').textContent = run ? `${same} of ${run} verifications replayed identically` : 'no verifications yet'; };
    $('btn-replay-all').onclick = replayAll;
    replayAll();
  }

  function home() {
    const ink = '#14213a', ink2 = '#4b5a6e', blue = '#2b6ca3', line = '#e3e9f0', font = 'Inter, "Helvetica Neue", Arial, sans-serif';
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
        new Chart($('chart-shift'), { type: 'line', plugins: [pointLabels], data: { datasets: [{ data: pts, borderColor: blue, backgroundColor: 'rgba(43,108,163,.12)', fill: true, tension: .45, borderWidth: 3, pointRadius: 6, pointBackgroundColor: blue, pointBorderColor: '#fff', pointBorderWidth: 2, segment: { borderDash: (s) => s.p1.parsed.x > 2025 ? [8, 6] : undefined } }] },
          options: { animation: { duration: 900 }, responsive: true, maintainAspectRatio: false, layout: { padding: { top: 28, right: 24 } }, plugins: { legend: { display: false }, tooltip: { enabled: false } },
            scales: { x: { type: 'linear', min: 2023.6, max: 2030.4, grid: { display: false }, border: { color: line }, afterBuildTicks: (ax) => { ax.ticks = [2024, 2025, 2026, 2027, 2028, 2029, 2030].map(value => ({ value })); }, ticks: { color: ink, font: { size: 14 }, callback: (v_) => String(v_) } }, y: { beginAtZero: true, max: 1600, grid: { color: line }, border: { display: false }, ticks: { stepSize: 400 } } } } });
      }
      if ($('chart-app')) bars('chart-app', ['2021', '2022', '2023', '2024', '2025'], [583, 485, 460, 451, 576], ['£583m', '£485m', '£460m', '£451m', '£576m'], null, { max: 700, step: 175 });
    }
    if (window.mermaid) {
      mermaid.initialize({ startOnLoad: false, theme: 'base', securityLevel: 'loose', fontFamily: font, themeVariables: { primaryColor: '#ffffff', primaryBorderColor: '#9fb3c8', primaryTextColor: ink, lineColor: '#4b5a6e', secondaryColor: '#f3f6fa', tertiaryColor: '#f3f6fa', fontSize: '15px', fontFamily: font },
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
    if (rb) rb.onclick = async () => { if (confirm('Reset the demo to its baseline? Everything is deleted, then one AI product is filed on the register, admitted by the bank, and the customer mandate signed, so one passport is ACTIVE with no payments and no refusals.')) { rb.disabled = true; rb.textContent = 'seeding…'; await api('POST', '/api/demo/seed?stage=issued'); location.href = '/terminal'; } };
  });

  return { home, provider, bank, customer, console: console_, audit };
})();
