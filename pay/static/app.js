/* Agent Passport · payments vertical — view controllers. Server holds all state; this file renders it and calls the API. */
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
  const statusTag = (s) => ({ pending: 'amber', active: 'green', approved: 'green', submitted: 'blue', info_requested: 'amber', suspended: 'amber', draft: 'grey', rejected: 'red', revoked: 'red', expired: 'red', signed: 'green', unsigned: 'amber' }[s] || 'grey');
  const tag = (s, label) => `<span class="tag tag--${statusTag(s)}">${esc(label || String(s).replace('_', ' '))}</span>`;
  const v = (f, ...path) => { let c = f; for (const p of path) { if (!c || typeof c !== 'object' || !(p in c)) return undefined; c = c[p]; } return (c && typeof c === 'object' && 'value' in c) ? c.value : c; };
  const NUMERIC = new Set(['human_confirm_above_gbp', 'cover_gbp']);

  const LABELS = {
    company: { title: 'Model company', legal_name: 'Legal name', companies_house_number: 'Companies House number', website: 'Website' },
    attestation: { title: 'Attestation (documentation accuracy)', name: 'Named person', role: 'Role or title', declaration_ref: 'Declaration reference' },
    model: { title: 'The model', model_name: 'Model name', model_id: 'Model identifier', release: 'Release', model_provider: 'Foundation model provider', model_version: 'Foundation model version (pinned)', benchmarks_url: 'Benchmark data (URL)', training_details_url: 'Training details (URL)', documentation_url: 'Model card / documentation (URL)' },
    intended_use: { title: 'Registered use domain', action_type: 'Action type', description: 'Description' },
  };


  function applist(apps, id = 'applist') {
    const ul = $(id); if (!ul) return;
    ul.innerHTML = apps.length ? '' : '<li class="small">None yet.</li>';
    for (const a of apps) ul.append(el('li', null, `<a href="${location.pathname}?ref=${a.ref}" class="mono">${esc(a.ref)}</a> ${tag(a.status)}`));
  }
  function pick(apps) {
    const ref = new URLSearchParams(location.search).get('ref');
    return apps.find(a => a.ref === ref) || apps[0] || null;
  }
  const rows = (id, list, cols) => { const tb = $(id).querySelector('tbody'); tb.innerHTML = ''; list.forEach(x => tb.append(el('tr', null, x.cells.map(c => `<td>${c}</td>`).join('')))); if (!list.length) tb.append(el('tr', null, `<td class="empty-row" colspan="${cols}">None yet.</td>`)); };
  const modelStatus = (x) => x.status === 'approved' ? tag(x.model_status === 'revoked' ? 'revoked' : x.model_status === 'suspended' ? 'suspended' : 'approved', x.model_status && x.model_status !== 'active' ? 'approved · ' + x.model_status : 'approved · active') : tag(x.status);
  const modeLabel = (m) => m === 'gemini' ? 'Gemini (live)' : m === 'fixture' ? 'fixture (deterministic stand-in)' : 'fixture after Gemini failed';

  // ───────────── Provider (operator) ─────────────
  async function provider() {
    let state = await api('GET', '/api/state');
    const ref0 = new URLSearchParams(location.search).get('ref');
    let a = state.applications.find(x => x.ref === ref0) || null;
    render();

    async function refresh() { state = await api('GET', '/api/state'); a = state.applications.find(x => x.id === (a && a.id)) || null; render(); }

    function render() {
      const apps = state.applications, prior = state.registered_models || [];
      rows('pv-models', [
        ...apps.map(x => ({ cells: [`<a href="/provider?ref=${x.ref}">${esc(x.ref)}</a>`, esc(v(x.fields, 'model', 'model_name') || 'Untitled'), d(x.submitted_at), modelStatus(x)] })),
        ...prior.map(m => ({ cells: [esc(m.registration), esc(m.model), d(m.assured), tag(m.status)] })),
      ], 4);
      const has = !!a, draft = has && a.status === 'draft';
      $('pv-form').hidden = !has;
      if (has) { $('pv-ref').textContent = a.ref; $('pv-status').innerHTML = modelStatus(a); }
      $('btn-prefill').hidden = !draft;
      document.querySelector('[data-step="3"]').hidden = !has;
      if (has) { renderFacts(a.fields, draft); } else { $('facts').innerHTML = ''; $('btn-save-fields').hidden = true; }
      const submitted = has && a.status !== 'draft';
      $('btn-submit').hidden = submitted;
      $('confirm').hidden = !submitted;
      if (submitted) $('confirm-ref').textContent = a.ref;
    }

    function renderFacts(f, editable) {
      const box = $('facts'); box.innerHTML = ''; box.className = 'facts';
      for (const [sec, labels] of Object.entries(LABELS)) {
        box.append(el('h3', null, esc(labels.title)));
        const dl = el('dl');
        for (const [k, label] of Object.entries(labels)) {
          if (k === 'title') continue;
          const fact = (f[sec] || {})[k] || { value: null };
          const isBool = typeof fact.value === 'boolean';
          const input = isBool
            ? `<label><input type="checkbox" data-sec="${sec}" data-key="${k}" ${fact.value ? 'checked' : ''} ${editable ? '' : 'disabled'}> ${fact.value ? 'Yes' : 'No'}</label>`
            : `<input class="input" data-sec="${sec}" data-key="${k}" value="${esc(fact.value ?? '')}" ${editable ? '' : 'disabled'} aria-label="${esc(label)}">`;
          const prov = fact.source_doc ? `<span class="prov">from <span class="mono">${esc(fact.source_doc)}</span>: <q>${esc(fact.quote || '')}</q></span>` : '';
          dl.append(el('div', 'fact', `<dt>${esc(label)}</dt><dd>${input}${prov}</dd>`));
        }
        box.append(dl);
      }
      $('btn-save-fields').hidden = !editable;
    }

    function collectFields() {
      const f = JSON.parse(JSON.stringify(a.fields));
      document.querySelectorAll('#facts [data-sec]').forEach(inp => {
        const cur = f[inp.dataset.sec][inp.dataset.key] || (f[inp.dataset.sec][inp.dataset.key] = {});
        cur.value = inp.type === 'checkbox' ? inp.checked : (inp.value === '' ? null : (NUMERIC.has(inp.dataset.key) && !isNaN(inp.value) ? Number(inp.value) : inp.value));
      });
      return f;
    }

    $('btn-new').onclick = async () => { a = await api('POST', '/api/applications'); history.replaceState(null, '', `?ref=${a.ref}`); await refresh(); };
    $('btn-prefill').onclick = async () => { a = await api('POST', `/api/applications/${a.id}/prefill`); await refresh(); };
    $('btn-save-fields').onclick = async () => { a = await api('PUT', `/api/applications/${a.id}/fields`, { fields: collectFields() }); $('save-note').textContent = 'Saved ' + t(new Date().toISOString()); await refresh(); };
    $('btn-submit').onclick = async () => { await api('PUT', `/api/applications/${a.id}/fields`, { fields: collectFields() }); a = await api('POST', `/api/applications/${a.id}/submit`); await refresh(); window.scrollTo({ top: document.body.scrollHeight }); };
  }

  // ───────────── Regulator ─────────────
  function envelopePanels(full) {
    const pl = full, ver = full.verification.parts, a = pl.assurance, i = pl.agent_identity, m = pl.mandate, mp = pl.mandate_proposed;
    const ad = (m || mp).authorization_details[0];
    const sig = (ok, who, kid) => ok == null ? (full.status === 'pending' && who === 'authority' ? `<span class="tag tag--amber">Not issued yet</span>` : `<span class="tag tag--amber">Unsigned</span>`) : ok ? `<span class="tag tag--green">Verified · Ed25519</span>` : `<span class="tag tag--red">Signature fails</span>`;
    const kv = (rows) => `<dl class="envelope__kv">${rows.map(([k, val]) => `<div><dt>${k}</dt><dd>${val}</dd></div>`).join('')}</dl>`;
    return `
      <section>
        <span class="envelope__who">Signed by the authority · issued from the model approval when the customer signs</span>
        <h3 class="envelope__title">Assurance ${sig(ver.assurance, 'authority')}</h3>
        ${kv([['Approved model', `${esc(a.model_ref.model_name)} <span class="mono">${esc(a.model_ref.model_id)}</span> · ${esc(a.model_ref.company)} · <span class="mono small">${esc(a.model_ref.registration)}</span>`], ['Status', `${esc(a.assurance.kya_status)} · ${a.assurance.checks_passed} checks passed${a.assurance.checks_flagged.length ? ', flagged ' + esc(a.assurance.checks_flagged.join(', ')) : ''}`], ['Condition', `hold above ${gbp(a.condition.human_confirm_above.amount)}`], ['Ceilings', `≤ ${gbp(a.policy_ceilings.per_payment_ceiling.amount)} per payment · ≤ ${gbp(a.policy_ceilings.monthly_per_account_ceiling.amount)} per account in 30 days`], ['Attested by', `${esc(a.attestation.name)}, ${esc(a.attestation.role)} · documentation accuracy only`], ['Valid until', esc(a.valid_until)], ['Bound to', `agent identity <span class="mono small">${esc(a.binds.agent_identity_sha256.slice(0, 12))}…</span>`]])}
      </section>
      <section>
        <span class="envelope__who">Signed by the customer · its deployment of the model</span>
        <h3 class="envelope__title">Agent identity ${sig(ver.agent_identity)}</h3>
        ${kv([['Agent', `${esc(i.agent.name)} · <span class="mono">${esc(i.agent.agent_id)}</span>`], ['Public key', `<abbr title="Agent key binding provides workload-identity guarantees equivalent to SPIFFE SVID."><span class="mono small">kid ${esc(full.minimal.agent_kid)}</span></abbr> · possession ${i.deployment && i.deployment.proof_of_possession ? 'proven' : 'not proven'}`], ['Model', `${esc(i.agent.model_name)} · ${esc(i.agent.model_provider)} <span class="mono small">${esc(i.agent.model_version)}</span>`], ['Config SHA-256', `<span class="mono small">${esc((i.agent.config_sha256 || '').slice(0, 16))}…</span>`], ['Key custody', esc((i.deployment || {}).key_storage || '')]])}
      </section>
      <section>
        <span class="envelope__who">Signed by the customer</span>
        <h3 class="envelope__title">Payment Mandate ${sig(ver.mandate)}</h3>
        <span class="small">OAuth 2.0 RFC 9396 Rich Authorization Request · written by the customer within the policy ceilings · not reviewed by the authority</span>
        ${kv(m ? [['Customer', esc((mp.customer || {}).legal_name || '')], ['Signed by', `${esc((mp.authorising_officer || {}).name || '')}, ${esc((mp.authorising_officer || {}).role || '')}`], ['Payees', `${ad.supplier_allowlist.length} accounts (content stays with the customer and the bank)`], ['Expires', esc(mp.valid_until)], ['Ceiling containment', '<span class="tag tag--green">within policy ceilings</span>']]
                : [['Ceilings', `per payment ≤ ${gbp(a.policy_ceilings.per_payment_ceiling.amount)} · per account in 30 days ≤ ${gbp(a.policy_ceilings.monthly_per_account_ceiling.amount)} · expiry ≤ ${esc(a.policy_ceilings.max_validity)}`], ['Actions', esc(a.policy_ceilings.action_types.join(', '))]])}
        ${m ? '' : `<p class="envelope__pending">Awaiting the customer's mandate in the <a href="/customer">Customer Panel</a>. The passport is issued when the customer signs; until then the bank refuses every instruction at R.1.</p>`}
      </section>`;
  }

  async function regulator() {
    let state = await api('GET', '/api/state');
    const q = new URLSearchParams(location.search);
    const issued = () => state.passports.filter(x => x.status !== 'pending');
    let p = q.get('passport') ? issued().find(x => x.passport_id === q.get('passport')) || null : null;
    let a = p ? state.applications.find(x => x.id === p.application_id) : (q.get('ref') ? state.applications.find(x => x.ref === q.get('ref') && x.status !== 'draft') || null : null);
    const mode = p ? 'agent' : a ? 'case' : 'dash';
    let selectedVid = null;
    render();

    async function refresh() { state = await api('GET', '/api/state'); if (a) a = state.applications.find(x => x.id === a.id) || a; render(); }
    function passportFor() { return p ? (state.passports.find(x => x.passport_id === p.passport_id) || p) : null; }
    function renderModel() {
      const box = $('rg-model'); const ok = a && a.status === 'approved'; box.hidden = !ok; if (!ok) return;
      const m = (state.models || []).find(x => x.application_id === a.id) || { model_status: 'active', passports: [] };
      const ms = m.model_status || 'active';
      $('md-status').innerHTML = tag(ms === 'active' ? 'active' : ms, ms === 'active' ? 'approved · active' : ms);
      const pol = state.policy || {};
      $('md-summary').innerHTML = [['Model', `<strong>${esc(m.model_name || '')}</strong> <span class="mono">${esc(m.model_id || '')}</span> · ${esc(m.company || '')}`], ['Approved', `${d(m.approved_at)} by ${esc(a.officer || '')}`], ['Policy ceilings', `per payment ≤ ${gbp(pol.per_payment_ceiling_gbp)} · per account in 30 days ≤ ${gbp(pol.monthly_per_account_ceiling_gbp)} · expiry ≤ ${esc(pol.max_validity)}`], ['Condition', `hold instructions above ${gbp(((a.condition || {}).human_confirm_above || {}).amount)}`]].map(([k, val]) => `<div><dt>${k}</dt><dd>${val}</dd></div>`).join('');
      $('btn-md-suspend').hidden = ms !== 'active'; $('btn-md-reinstate').hidden = ms !== 'suspended'; $('btn-md-revoke').hidden = ms === 'revoked';
      const ul = $('md-passports'); ul.innerHTML = '';
      const mine = issued().filter(x => x.application_id === a.id);
      mine.forEach(x => ul.append(el('li', null, `<a href="/regulator?passport=${x.passport_id}" class="mono">${esc(x.passport_id)}</a> ${tag(x.status)} <span class="small">${esc(((x.agent_identity || {}).agent || {}).name || '')} · ${esc(((x.mandate_proposed || {}).customer || {}).legal_name || '')}</span>`)));
      if (!mine.length) ul.append(el('li', 'small', 'None yet: an agent appears here when a customer registers it on this model and signs its mandate.'));
    }
    async function modelLife(status) {
      const reason = $('md-reason').value.trim(); $('md-error').hidden = true;
      try { await api('POST', `/api/models/${a.id}/status`, { status, reason }); $('md-reason').value = ''; await refresh(); }
      catch (e) { $('md-error').textContent = e.message; $('md-error').hidden = false; }
    }
    $('btn-md-suspend').onclick = () => modelLife('suspended');
    $('btn-md-reinstate').onclick = () => modelLife('active');
    $('btn-md-revoke').onclick = () => modelLife('revoked');

    function render() {
      $('rg-dash').hidden = mode !== 'dash'; $('rg-case').hidden = mode !== 'case'; $('rg-agent').hidden = mode !== 'agent';
      p = passportFor();
      $(mode === 'agent' ? 'rg-agent-anomaly' : 'rg-dash-anomaly').append($('rg-anomaly'));
      $(mode === 'agent' ? 'rg-agent-history' : 'rg-case-history').append($('rg-history-wrap'));
      $('rg-anomaly').hidden = mode === 'case'; $('rg-history-wrap').hidden = mode === 'dash'; $('rg-quiet').hidden = true;
      if (mode === 'dash') renderDash(); else if (mode === 'agent') renderAgent(); else renderCase();
      renderExceptions();
      renderIncidents();
      renderHistory();
    }
    function renderDash() {
      const apps = state.applications.filter(x => x.status !== 'draft'), live = issued(), viol = state.violations || [];
      const todo = apps.filter(x => x.status === 'submitted' || x.status === 'info_requested');
      $('rg-todo').hidden = !todo.length;
      $('rg-todo').innerHTML = todo.map(x => `<a href="/regulator?ref=${x.ref}">${esc(x.ref)}</a> awaits your decision.`).join(' ');
      rows('rg-models', apps.map(x => ({ cells: [`<a href="/regulator?ref=${x.ref}">${esc(x.ref)}</a>`, esc(v(x.fields, 'model', 'model_name') || ''), esc(v(x.fields, 'company', 'legal_name') || ''), d(x.submitted_at), modelStatus(x)] })), 5);
      rows('rg-agents', live.map(x => { const ag = (x.agent_identity || {}).agent || {}, mp = x.mandate_proposed || {}; return { cells: [`<a href="/regulator?passport=${x.passport_id}">${esc(x.passport_id)}</a>`, esc(ag.name || ''), esc((mp.customer || {}).legal_name || ''), esc(ag.model_name || ''), tag(x.status)] }; }), 5);
      const quiet = !viol.length && !(state.incidents || []).length;
      $('rg-quiet').hidden = !quiet; $('rg-anomaly').hidden = quiet;
    }
    function renderCase() {
      $('rg-ref').textContent = a.ref;
      $('rg-status').innerHTML = modelStatus(a);
      const f = a.fields;
      $('rg-summary').innerHTML = [
        ['Model company', `${esc(v(f, 'company', 'legal_name'))} · Companies House <span class="mono">${esc(v(f, 'company', 'companies_house_number'))}</span> · ${esc(v(f, 'company', 'website'))}`],
        ['Attestation', `${esc(v(f, 'attestation', 'name'))}, ${esc(v(f, 'attestation', 'role'))} · declaration <span class="mono">${esc(v(f, 'attestation', 'declaration_ref'))}</span> · documentation accuracy only, no liability for agents' actions`],
        ['Model', `<strong>${esc(v(f, 'model', 'model_name'))}</strong> <span class="mono">${esc(v(f, 'model', 'model_id'))}</span> · release ${esc(v(f, 'model', 'release'))} · ${esc(v(f, 'model', 'model_provider'))} <span class="mono">${esc(v(f, 'model', 'model_version'))}</span>`],
        ['Documentation', `<a href="${esc(v(f, 'model', 'documentation_url'))}">model card</a> · <a href="${esc(v(f, 'model', 'benchmarks_url'))}">benchmark data</a> · <a href="${esc(v(f, 'model', 'training_details_url'))}">training details</a>`],
        ['Registered use domain', `<strong>${esc(v(f, 'intended_use', 'action_type'))}</strong> · ${esc(v(f, 'intended_use', 'description'))} · no customer named: each customer registers its own agent and mandate within the policy ceilings`],
      ].map(([k, val]) => `<div><dt>${k}</dt><dd>${val}</dd></div>`).join('');
      const pol = state.policy || {};
      $('rg-ceilings').textContent = `per payment ≤ ${gbp(pol.per_payment_ceiling_gbp)} · per account in 30 days ≤ ${gbp(pol.monthly_per_account_ceiling_gbp)} · expiry ≤ ${pol.max_validity} · actions ${(pol.action_types || []).join(', ')}`;
      const cb = $('rg-checks').querySelector('tbody'); cb.innerHTML = '';
      (a.checks || []).forEach(c => cb.append(el('tr', null, `<td>${esc(c.id)}</td><td>${esc(c.title)} <span class="tag tag--${c.status === 'CURRENT' ? 'green' : 'grey'}">${esc(c.status)}</span><br><span class="small">${esc(c.detail)}</span></td><td>${esc(c.source)}<br><span class="small">${esc(c.evidence)}</span></td><td>${c.result === 'pass' ? '<span class="tag tag--green">Pass</span>' : '<span class="tag tag--amber">Flag</span>'}</td>`)));
      $('rg-filenote').value = a.file_note || '';
      if (pol.human_confirm_above_gbp && !$('rg-condition').dataset.touched) $('rg-condition').value = pol.human_confirm_above_gbp;
      if (a.review) renderReview(a.review); else if (!a._reviewing) { a._reviewing = true; runReview(true); }
      $('rg-decide').hidden = !(a.status === 'submitted' || a.status === 'info_requested');
      renderModel();
    }
    function renderAgent() {
      const ag = (p.agent_identity || {}).agent || {}, mp = p.mandate_proposed || {};
      $('ag-meta').innerHTML = `<strong>${esc(ag.name || '')}</strong> · customer ${esc((mp.customer || {}).legal_name || '')} · on ${esc(ag.model_name || '')} <span class="mono">${esc(ag.model_version || '')}</span>, registration <a href="/regulator?ref=${esc(a.ref)}" class="mono">${esc(a.ref)}</a> · issued ${d(p.issued_at)} when the customer signed its mandate`;
      renderPassport(p);
    }
    function renderIncidents() {
      const inc = $('rg-incidents'); inc.innerHTML = '';
      const mine = (state.incidents || []).filter(i => !p || i.subject === p.passport_id);
      mine.forEach(i => inc.append(el('li', null, `<time>${t(i.ts)}</time><span>${tag('revoked', 'Incident')} <a href="/regulator?passport=${esc(i.subject)}" class="mono">${esc(i.subject)}</a> ${esc(i.entry.event)}: ${esc(i.entry.reason)} · last refusal ${esc(i.entry.last_rule)} ${esc(i.entry.last_code)} · audit #${i.id} <span class="mono small">${esc(i.hash.slice(0, 12))}</span></span>`)));
      if (!mine.length) inc.append(el('li', 'log__empty', 'No incidents.'));
    }
    function renderHistory() {
      const hist = $('rg-history'); hist.innerHTML = '';
      if (!a) return;
      const lines = [];
      if (a.submitted_at) lines.push([a.submitted_at, 'Model registration submitted; documentation accuracy attested; checks M.1–M.6 run.']);
      if (a.officer_note) lines.push([a.decided_at || a.submitted_at, `${a.officer}: ${a.status.replace('_', ' ')} — “${a.officer_note}”`]);
      if (p && p.mandate_signed_at) lines.push([p.mandate_signed_at, `${(p.mandate.signed_by || {}).name}, ${(p.mandate.signed_by || {}).role} (customer): wrote and signed the mandate; within policy ceilings. Passport issued.`]);
      (p ? p.history : []).forEach(h => lines.push([h.ts, `${h.officer}: ${h.from ? h.from + ' → ' : ''}${h.to} — ${h.reason}`]));
      lines.sort((x, y) => x[0] < y[0] ? -1 : 1).reverse().forEach(([ts, txt]) => hist.append(el('li', null, `<time>${t(ts)}</time><span>${esc(txt)}</span>`)));
      if (!lines.length) hist.append(el('li', 'log__empty', 'Nothing yet.'));
    }

    function renderReview(r) {
      const ol = $('review'); ol.hidden = false; ol.innerHTML = '';
      const kv = (o) => `<dl class="kv">${Object.entries(o).map(([k, v_]) => `<div><dt>${esc(k.replace(/_/g, ' '))}</dt><dd>${Array.isArray(v_) ? v_.map(esc).join('<br>') : esc(String(v_ ?? '—'))}</dd></div>`).join('')}</dl>`;
      for (const st of r.steps) {
        let body = '', state = 'done', badge = '';
        if (st.id === 'evidence') body = `<p class="small">The model company registers</p>${kv(st.data.company_registers || st.data.provider_claims || {})}<p class="small">Customers will</p>${kv(st.data.customers_will || st.data.customer_authorises || {})}<p class="small">The authority is asked to certify</p>${kv(st.data.authority_asked_to_certify || {})}<p class="small">${esc(st.data.registration || '')}</p>`;
        if (st.id === 'rule_map') { badge = `<span class="tag tag--blue">${esc(r.assistant)}</span> <span class="mono small">${esc(st.data.rule_pack)}</span>`; body = `<table class="rulemap"><thead><tr><th>Rule</th><th>Requirement</th><th>Evidence</th><th>Result</th></tr></thead><tbody>${st.data.rules.map(x => `<tr><td>${esc(x.id)}</td><td>${esc(x.title)} <span class="tag tag--${x.status === 'CURRENT' ? 'green' : 'grey'}">${esc(x.status)}</span></td><td>${x.evidence ? `<span class="mono small">${esc(String(x.evidence.value))}</span>${x.evidence.source_doc ? `<br><span class="small">${esc(x.evidence.source_doc)}</span>` : ''}` : '<span class="tag tag--red">uncovered</span>'}</td><td>${x.result === 'pass' ? '<span class="tag tag--green">Pass</span>' : '<span class="tag tag--amber">Flag</span>'}</td></tr>`).join('')}</tbody></table>${st.data.uncovered.length ? `<p class="error">Uncovered: ${esc(st.data.uncovered.join(', '))}</p>` : '<p class="small">Every rule maps to cited evidence.</p>'}`; }
        if (st.id === 'tests') body = `<div class="cards">${st.data.map(x => `<div><strong>${esc(x.id)} · ${esc(x.title)}</strong><span class="small">${esc(x.instruction.supplier_name)} · ${esc(x.instruction.payee_account_ref)} · ${gbp(x.instruction.amount)}${x.variant !== 'normal' ? ' · ' + esc(x.variant) : ''}</span><span class="small">expect <b>${esc(x.expect)} ${esc(x.expect_rule)}</b></span></div>`).join('')}</div>`;
        if (st.id === 'sandbox') { const ok = st.data.filter(x => x.pass).length; badge = `<span class="tag tag--${ok === st.data.length ? 'green' : 'red'}">${ok} of ${st.data.length} as expected</span> <span class="small">same code path as /bank</span>`; body = `<div class="cards">${st.data.map(x => `<div data-pass="${x.pass}"><strong>${esc(x.id)} ${x.pass ? 'PASS' : 'FAIL'}</strong><span>${esc(x.decision)} <span class="mono">${esc(x.rule)} · ${esc(x.code)}</span></span><span class="small">${esc(x.reason)}</span></div>`).join('')}</div>`; }
        if (st.id === 'recommendation') { const d = st.data; badge = `<span class="tag tag--blue">${esc(d.label)}</span>`; body = `<p class="verdict verdict--${d.verdict.startsWith('APPROVE') ? 'approve' : 'refer'}">${esc(d.verdict)}</p><ul>${d.reasons.map(x => `<li>${esc(x)}</li>`).join('')}</ul><p class="small">Draft note (${esc(modeLabel(d.narrative_mode))}): ${esc(d.narrative)}</p>`; if ($('rg-condition') && !$('rg-condition').dataset.touched) $('rg-condition').value = d.condition.human_confirm_above; }
        if (st.id === 'signoff') { state = a.status === 'approved' ? 'done' : 'human'; body = `<p>${esc(st.data.who)} decides below. ${esc(st.data.note)}.${a.status === 'approved' ? ' <span class="tag tag--green">signed</span>' : a.status === 'rejected' ? ' <span class="tag tag--red">rejected</span>' : ''}</p>`; }
        const li = el('li', null, `<div class="stepper__title">${esc(st.title)} ${badge}</div><div class="stepper__body">${body}</div>`); li.dataset.state = state; ol.append(li);
      }
    }
    async function runReview(auto) {
      const b = $('btn-review'); b.disabled = true; b.textContent = 'Running…';
      try { const r = await api('POST', `/api/applications/${a.id}/review`, { human_confirm_above: $('rg-condition').dataset.touched ? Number($('rg-condition').value) : null }); a.review = r.review; renderReview(r.review); $('review-note').textContent = (auto ? 'ran on opening · ' : '') + 'deterministic; the model only phrases the draft note'; }
      catch (e) { $('review-note').textContent = e.message; }
      finally { b.disabled = false; b.textContent = 'Run the six steps again'; }
    }
    $('btn-review').onclick = () => runReview(false);

    function renderExceptions() {
      const pt = state.pattern_threshold || { count: 2, window_hours: 24 };
      const mine = (state.violations || []).filter(x => !p || x.passport_id === p.passport_id);
      const alerts = (state.alerts || []).filter(x => !p || x.passport_id === p.passport_id);
      const al = $('rg-alert');
      if (alerts.length) { al.hidden = false; al.innerHTML = alerts.map(x => `SUPERVISOR ALERT · ${esc(x.passport_id)} · ${x.n} refusals at ${esc(x.rule)} ${esc(x.code)} within ${pt.window_hours}h <span>(threshold ${pt.count} in ${pt.window_hours}h, rule pack policy) · pattern, not a single error · <a href="#exception">open the exception panel</a></span>`).join('<br>'); }
      else al.hidden = true;
      $('ex-meta').textContent = mine.length ? `${mine.length} refusals · ${mine.filter(x => x.status === 'OPEN').length} open` : 'no refusals yet';
      const tb = $('rg-violations').querySelector('tbody'); tb.innerHTML = '';
      mine.forEach(x => { const tr = el('tr', null, `<td>${t(x.ts)}</td><td class="mono small">${esc(x.agent_id || '')}${p ? '' : `<br><a href="/regulator?passport=${esc(x.passport_id)}">${esc(x.passport_id)}</a>`}</td><td><span class="mono">${esc(x.rule)}</span><br><span class="small">${esc(x.code)}</span></td><td>${esc(x.instruction.action_type)} · ${esc(x.instruction.supplier_name || '')} · <span class="mono">${esc(x.instruction.payee_account_ref || '')}</span> · ${gbp(x.instruction.amount)}${x.evidence ? ` <span class="tag tag--grey">invoice ${esc(x.evidence.invoice)}</span>` : ''}</td><td>${tag('revoked', x.outcome)}</td><td>${tag(x.status === 'OPEN' ? 'amber' : x.status === 'INVESTIGATING' ? 'blue' : 'green', x.status)}${x.resolution ? `<br><span class="small">${esc(x.resolution)}</span>` : ''}</td>`); tr.dataset.vid = x.id; tr.setAttribute('aria-selected', String(x.id === selectedVid)); tr.onclick = () => { selectedVid = x.id; renderEvidence(x); renderExceptions(); }; tb.append(tr); });
      if (!mine.length) tb.append(el('tr', null, '<td colspan="6" class="small">Nothing refused yet.</td>'));
      const ex = $('exception'); ex.hidden = !p; if (!p) return;
      const inv = p.investigation === 'investigating';
      $('ex-state').innerHTML = `<span class="stamp stamp--${p.status === 'active' ? 'green' : p.status === 'suspended' ? 'amber' : 'red'}">${esc(p.status)}</span>${inv ? '<span class="stamp stamp--amber">investigating</span>' : ''}<span class="small">${p.status === 'suspended' ? 'payments blocked at R.2 while you look' : p.status === 'revoked' ? 'closed; registry REVOKED, vouch voucher revoked' : 'payments flow; the bank reads the registry on every instruction'}${inv ? ' · investigating blocks nothing by itself; the registry status does' : ''}</span>`;
      const act = $('ex-actions'); act.innerHTML = '';
      const btn = (label, cls, fn) => { const b = el('button', 'btn btn--small ' + cls, label); b.type = 'button'; b.onclick = fn; act.append(b); };
      const reason = () => $('rg-reason').value.trim() || 'via the exception panel';
      if (p.status === 'active') btn('Suspend', 'btn--secondary', () => lifeFrom('suspended', reason()));
      if (p.status !== 'revoked' && !inv) btn('Open investigation', 'btn--secondary', async () => { await api('POST', `/api/passports/${p.passport_id}/investigation`, { action: 'open', note: reason() }); await refresh(); });
      if (p.status !== 'revoked') btn('Revoke', 'btn--warning', () => lifeFrom('revoked', reason()));
      if (p.status === 'suspended') btn('Reinstate (false positive)', '', () => lifeFrom('active', reason()));
      if (inv && p.status === 'active') btn('Close investigation, no change', 'btn--secondary', async () => { await api('POST', `/api/passports/${p.passport_id}/investigation`, { action: 'close', note: reason() }); await refresh(); });
    }
    async function lifeFrom(status, reason) {
      $('ex-error').hidden = true;
      try { await api('POST', `/api/passports/${p.passport_id}/status`, { status, reason }); $('rg-reason').value = ''; await refresh(); }
      catch (e) { $('ex-error').textContent = e.message; $('ex-error').hidden = false; }
    }
    function renderEvidence(x) {
      const ev = $('ex-evidence'); ev.hidden = false;
      const e = x.evidence;
      ev.innerHTML = `<strong>Refusal #${x.id} · ${esc(x.rule)} ${esc(x.code)} · ${t(x.ts)}</strong><div>Instruction: ${esc(x.instruction.action_type)} · ${esc(x.instruction.supplier_name || '')} · <span class="mono">${esc(x.instruction.payee_account_ref || '')}</span> · ${gbp(x.instruction.amount)} · invoice ${esc(x.instruction.invoice_ref || '—')} · audit #${x.audit_id}</div>` +
        (e ? `<div>Extraction evidence (${esc(e.invoice)}, read by ${esc(modeLabel(e.extraction_mode))}): the agent read account <span class="${e.instruction_payee === e.registered_payee ? 'right' : 'wrong'}">${esc(e.instruction_payee)}</span>; the customer signed for <span class="mono">${esc(e.registered_payee || '—')}</span>.</div><dl class="kv">${Object.entries(e.facts || {}).filter(([k]) => !k.startsWith('_')).map(([k, f]) => `<div><dt>${esc(k.replace(/_/g, ' '))}</dt><dd>${esc(String(f.value))} <span class="prov"><q>${esc(f.quote || '')}</q></span></dd></div>`).join('')}</dl>` : '<div class="small">No document evidence: the instruction came straight from the agent.</div>');
    }

    async function renderPassport(p) {
      $('pp-id').textContent = p.passport_id;
      $('pp-status').innerHTML = tag(p.status);
      $('btn-suspend').hidden = p.status !== 'active'; $('btn-reinstate').hidden = p.status !== 'suspended'; $('btn-revoke').hidden = p.status === 'revoked';
      const full = await api('GET', `/api/passports/${p.passport_id}`);
      const env = $('envelope');
      env.innerHTML = envelopePanels(full);
      env.classList.toggle('envelope--incomplete', !full.mandate_signed);
      const stamp = $('envelope-stamp'); if (stamp) { const ok = full.verification.ok; stamp.innerHTML = ok ? '<span class="stamp stamp--green">ALL THREE VERIFY</span> <span class="small">authority, provider and customer signatures checked with real Ed25519 calls just now</span>' : `<span class="stamp stamp--amber">${esc(String(full.verification.failure || '').replace('_', ' '))}</span> <span class="small">the envelope is not complete</span>`; }
      env.classList.toggle('envelope--revoked', p.status === 'revoked');
      renderRail(p, null);
      $('jwt-panels').innerHTML = ['assurance', 'agent_identity', 'mandate'].map(k => full.envelope[k] ? `<h4 class="h4">${k} <span class="small">JWT (OIDC-compatible) · header ${esc(JSON.stringify(full.headers[k]))}</span></h4><pre class="code">${esc(JSON.stringify(full[k], null, 2))}</pre><pre class="code code--wrap">${esc(full.envelope[k])}</pre>` : `<h4 class="h4">${k}</h4><p class="small">not yet signed</p>`).join('');
    }

    function renderRail(p, live) {
      const r = $('rail');
      const st = live ? live.status : p.vouch_status;
      const stTag = st === 'ACTIVE' ? tag('active', 'active on rail') : st === 'REVOKED' ? tag('revoked', 'revoked on rail') : tag('grey', st || 'unknown');
      r.innerHTML = `<div><span class="rail__k">Voucher</span><span class="rail__v mono">${esc(p.vouch_voucher_id || '—')}</span></div><div><span class="rail__k">Mode</span><span class="rail__v">${esc(p.vouch_mode || state.vouch_mode)}${p.vouch_mode === 'live-fallback' ? ' <span class="small">(fixture)</span>' : ''}</span></div><div><span class="rail__k">Status</span><span class="rail__v">${stTag}${live ? ` <span class="small">${esc(live.detail)}</span>` : ''}</span></div><button class="btn btn--secondary btn--small" id="btn-rail" type="button">Re-check on rail</button>`;
      $('btn-rail').onclick = async () => { const x = await api('GET', `/api/passports/${p.passport_id}/vouch`); renderRail(p, x.live); };
    }

    async function decide(decision) {
      const note = $('rg-officer-note').value.trim();
      $('decide-error').hidden = true;
      try { await api('POST', `/api/applications/${a.id}/decision`, { decision, note, human_confirm_above: Number($('rg-condition').value) }); await refresh(); }
      catch (e) { $('decide-error').textContent = e.message; $('decide-error').hidden = false; }
    }
    async function life(status) {
      const reason = $('rg-reason').value.trim(); $('life-error').hidden = true;
      try { await api('POST', `/api/passports/${p.passport_id}/status`, { status, reason }); $('rg-reason').value = ''; await refresh(); }
      catch (e) { $('life-error').textContent = e.message; $('life-error').hidden = false; }
    }
    $('rg-condition').oninput = () => { $('rg-condition').dataset.touched = '1'; };
    $('btn-approve').onclick = () => decide('approve');
    $('btn-info').onclick = () => decide('request_info');
    $('btn-reject').onclick = () => decide('reject');
    $('btn-suspend').onclick = () => life('suspended');
    $('btn-reinstate').onclick = () => life('active');
    $('btn-revoke').onclick = () => life('revoked');
    $('btn-note').onclick = async () => { const b = $('btn-note'); b.disabled = true; b.textContent = 'Drafting…'; try { const r = await api('POST', `/api/applications/${a.id}/file-note`); $('rg-filenote').value = r.note; $('note-mode').textContent = `drafted by ${modeLabel(r.mode)}`; } finally { b.disabled = false; b.textContent = 'Draft file note'; } };
  }

  // ───────────── Customer ─────────────
  async function customer() {
    let state = await api('GET', '/api/state');
    const ref = new URLSearchParams(location.search).get('ref');
    let p = state.passports.find(x => x.passport_id === ref) || null;
    const d0 = state.mandate_draft || { customer: {}, authorising_officer: {} };
    const draft = JSON.parse(JSON.stringify(d0)); let checkTimer = null;
    render();

    function render() {
      const models = (state.models || []).filter(m => m.model_status === 'active');
      rows('cu-agents', state.passports.map(x => { const ag = (x.agent_identity || {}).agent || {}; return { cells: [`<a href="/customer?ref=${x.passport_id}">${esc(x.passport_id)}</a>`, esc(ag.name || ''), esc(ag.model_name || ''), x.status === 'pending' ? tag('unsigned', 'awaiting your signature') : tag(x.status, 'passport ' + x.status)] }; }), 4);
      $('cu-empty').hidden = !!(models.length || p);
      $('cu-create').hidden = !models.length;
      const sel = $('cu-model'); sel.innerHTML = models.map(m => `<option value="${m.application_id}">${esc(m.model_name)} · ${esc(m.company)} · ${esc(m.model_version)}</option>`).join('');
      const pol = state.policy || {};
      if (!$('cu-agent-name').value) $('cu-agent-name').value = (state.agent_draft || {}).agent_name || '';
      $('cu-mandate').hidden = !p;
      if (!p) return;
      const mp = p.mandate_proposed, ad = mp.authorization_details[0], signed = p.mandate_signed, ag = p.agent || {};
      $('cu-agent-kv').innerHTML = [['Agent', `<strong>${esc(p.agent_identity.agent.name)}</strong> · <span class="mono">${esc(mp.agent_id)}</span> · on ${esc(p.agent_identity.agent.model_name)} (${esc(p.agent_identity.agent.model_provider)} <span class="mono">${esc(p.agent_identity.agent.model_version)}</span>)`], ['Agent key', `<span class="mono">kid ${esc(mp.agent_kid)}</span> · ${ag.pop_verified ? '<span class="tag tag--green">possession proven</span>' : '<span class="tag tag--amber">possession pending</span>'} · config <span class="mono small">${esc((ag.config_sha256 || '').slice(0, 12))}…</span>`], [p.status === 'pending' ? 'Agent record' : 'Passport', `<span class="mono">${esc(p.passport_id)}</span> ${tag(p.status)} · ${p.status === 'pending' ? 'passport issued when you sign the mandate' : 'issued from the model approval when the mandate was signed'}`]].map(([k, val]) => `<div><dt>${k}</dt><dd>${val}</dd></div>`).join('');
      $('cu-id').textContent = p.passport_id; $('cu-ref').textContent = p.passport_id;
      $('cu-state').innerHTML = signed ? tag('signed', 'signed') : tag('unsigned', 'awaiting signature');
      $('cu-card').classList.toggle('mandate--signed', signed);
      $('cu-kv').innerHTML = [['Customer', `${esc((mp.customer || d0.customer).legal_name)} · Companies House <span class="mono">${esc((mp.customer || d0.customer).companies_house_number)}</span>`], ['Authorising officer', `${esc((mp.authorising_officer || d0.authorising_officer).name)}, ${esc((mp.authorising_officer || d0.authorising_officer).role)}`], ['Supervisor condition', `the bank holds anything above ${gbp(p.assurance.condition.human_confirm_above.amount)} for your confirmation`]].map(([k, val]) => `<div><dt>${k}</dt><dd>${val}</dd></div>`).join('');
      renderMandateForm(p, signed, ad, mp);
    }
    $('btn-create-agent').onclick = async () => {
      const b = $('btn-create-agent'); b.disabled = true; $('cu-create-error').hidden = true; $('cu-create-note').textContent = 'generating key, signing challenge…';
      try { const np = await api('POST', '/api/agents', { application_id: Number($('cu-model').value), agent_name: $('cu-agent-name').value.trim() || null }); state = await api('GET', '/api/state'); p = state.passports.find(x => x.passport_id === np.passport_id); history.replaceState(null, '', `?ref=${p.passport_id}`); render(); }
      catch (e) { $('cu-create-error').textContent = e.message; $('cu-create-error').hidden = false; }
      finally { b.disabled = false; $('cu-create-note').textContent = ''; }
    };
    function renderMandateForm(p, signed, ad, mp) {
      const ce = mp.ceilings || p.assurance.policy_ceilings || {};
      $('cu-form').hidden = signed || p.status === 'revoked';
      $('cu-suppliers-signed').hidden = !signed;
      if (signed) {
        const tb = $('cu-suppliers-signed').querySelector('tbody'); tb.innerHTML = '';
        ad.supplier_allowlist.forEach(s => tb.append(el('tr', null, `<td><span class="mono">${esc(s.supplier_id)}</span> ${esc(s.name)}</td><td class="mono">${esc(s.account_ref)}</td>`)));
        $('cu-kv').insertAdjacentHTML('beforeend', [['Action', `<strong>${esc(ad.actions.join(', '))}</strong> in ${esc(ad.currency)}`], ['Per payment', `not more than ${gbp(ad.per_payment_limit.amount)}`], ['Per supplier account', `not more than ${gbp(ad.monthly_limit_per_account.amount)} in any rolling 30 days`], ['Expires', esc(mp.valid_until)]].map(([k, val]) => `<div><dt>${k}</dt><dd>${val}</dd></div>`).join(''));
        $('cu-containment').className = 'containment containment--ok'; $('cu-containment').textContent = 'Ceiling containment: this mandate sits within the policy ceilings the authority set. Checked at signing; the bank checks it again on every payment.';
      } else {
        $('cu-kv').insertAdjacentHTML('beforeend', `<div><dt>Policy ceilings</dt><dd>per payment ≤ ${gbp((ce.per_payment_ceiling || {}).amount)} · per supplier account in 30 days ≤ ${gbp((ce.monthly_per_account_ceiling || {}).amount)} · expiry ≤ ${esc(ce.max_validity || '')}</dd></div>`);
        renderForm(); runCheck();
      }
      $('cu-signer').textContent = `${(draft.authorising_officer || {}).name}, ${(draft.authorising_officer || {}).role}, signs with the ${(draft.customer || {}).legal_name} key.`;
      $('cu-actions').hidden = signed || p.status === 'revoked';
      $('cu-sig').hidden = !signed;
      if (signed) $('cu-sig').innerHTML = `<strong>Signed ${d(p.mandate_signed_at)} at ${t(p.mandate_signed_at)} by ${esc((p.mandate.signed_by || {}).name)}, ${esc((p.mandate.signed_by || {}).role)}</strong> Ed25519 signature by the ${esc((mp.customer || {}).legal_name)} key. The passport is issued and ACTIVE, the voucher minted on the vouch rail. Live at once; no authority review.`;
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
        box.innerHTML = r.within_ceilings ? 'Ceiling containment: within the policy ceilings. Signing makes it live at once.' : `Ceiling containment: outside the policy ceilings. Signing is refused until this is fixed.<ul>${r.problems.map(x => `<li>${esc(x.problem)}</li>`).join('')}</ul>`;
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

  // ───────────── Bank · Action Terminal ─────────────
  // Presentation only: every verdict below comes from POST /api/verify unchanged. The arena shows the nine checks
  // resolving in order (slowed for demonstration); the raw response is kept off-screen for the record and the tests.
  const SHORT = { 'R.1': 'authority signature', 'R.2': 'registry status', 'R.3': 'agent identity signature', 'R.4': 'agent signature', 'R.5': 'customer mandate', 'R.6': 'payee on allowlist', 'R.7': 'per-payment limit', 'R.8': '30-day limit', 'R.9': 'supervisor condition', 'C.a': 'root scope', 'C.b': 'delegation ⊆ root', 'C.c': 'action ⊆ delegation' };
  async function bank() {
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
    if (!p) $('g-subject').innerHTML = '<span class="tm-dim">no passport yet — approve a registration in the <a href="/regulator">Regulator Panel</a>, then create the agent in the <a href="/customer">Customer Panel</a></span>';

    // ── the arena ──
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
      const sig = r.signature && r.signature.checked ? `agent signature <b class="${r.signature.verified ? 'ok' : 'fail'}">${r.signature.verified ? 'verified' : 'failed'}</b> · ` : '';
      const reg = r.rails && r.rails.authority_registry, rv = r.rails && r.rails.vouch;
      const rails = r.rails && (reg !== 'active' || (rv && rv.status === 'REVOKED')) ? `<span>authority registry <b class="${reg !== 'active' ? 'fail' : ''}">${esc(reg)}</b> · vouch rail <b class="${rv.status === 'REVOKED' ? 'fail' : ''}">${esc(rv.status || 'none')}</b>${reg !== 'active' && rv.status === 'REVOKED' ? ' · one supervisory action, two rails refuse' : ''}</span>` : '';
      const settle = r.settlement ? `<span class="ok">${esc(r.settlement.rail_reason)}</span>` : '';
      const vio = r.violation ? `<span>violation #${r.violation.id} recorded ${esc(r.violation.status)} <a href="/regulator">→ Regulator Panel</a></span>` : '';
      const inc = r.incident ? `<span class="fail"><b>INCIDENT</b> escalated to supervisor · ${r.incident.denies} refused instructions <a href="/regulator">→ Regulator Panel</a></span>` : '';
      gVerdict.className = 'g__verdict g__verdict--' + r.decision; gWrap.dataset.decision = r.decision;
      gVerdict.innerHTML = `<span class="g-word">${r.decision}</span><span class="g-cite">${cite}</span><span class="g-reason">${esc(r.reason)}</span><span class="g-notes">${settle}${rails}${vio}${inc}<span class="tm-dim">${sig}receipt signed by the authority · audit #${r.audit_id} <span class="mono">${esc(r.audit_hash.slice(0, 12))}</span> <a href="/audit">→ Audit</a></span></span>`;
      judgment.classList.remove('is-live');
    }
    function logLine(b, r, k) {
      lines.append(termLine(b, r, k));
      if (r.incident) { lines.append(el('li', 't-incident', `<span><b>INCIDENT</b> escalated to supervisor · ${r.incident.denies} refused instructions · audit #${r.incident.audit_id}</span>`)); setDenies(0); }
      else if (r.decision === 'DENY') setDenies(Math.min(3, (r.deny_count || denies + 1)));
    }
    async function present(b, r, k, fast) { await judge(b, r, k, fast); logLine(b, r, k); }
    const hideSteps = () => { $('invoice-steps').hidden = true; $('invoice-outcome').hidden = true; };

    // ── Part B: delegation chain toggle ──
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

    // ── the agent reads an invoice ──
    const ib = $('invoice-buttons');
    (state.invoices || []).forEach(inv => {
      const b = el('button', 'btn ' + (inv.id.endsWith('clean') ? 'btn--secondary' : 'btn--warning'), esc(inv.label) + ' <span class="btn__sub mono">' + esc(inv.id) + '</span>'); b.type = 'button'; b.disabled = !p;
      b.onclick = async () => {
        ib.querySelectorAll('button').forEach(x => x.disabled = true); b.textContent = 'Agent reading…';
        try { const r = await api('POST', '/api/agent/invoice', { passport_id: p.passport_id, invoice_id: inv.id, chain: chainOn() }); await showInvoice(r); }
        catch (e) { alert(e.message); }
        finally { ib.querySelectorAll('button').forEach(x => x.disabled = false); b.innerHTML = esc(inv.label) + ' <span class="btn__sub mono">' + esc(inv.id) + '</span>'; }
      };
      ib.append(b);
    });
    async function showInvoice(r) {
      const steps = $('invoice-steps'), out = $('invoice-outcome'); steps.hidden = false; out.hidden = true;
      steps.querySelectorAll('.invoice__step').forEach(x => x.hidden = true); out.querySelectorAll('[data-step]').forEach(x => x.hidden = true);
      const acct = r.instruction.payee_account_ref, ok = r.on_allowlist;
      const digits = (r.extraction.account_number || {}).value || '';
      $('g-subject').innerHTML = `<span class="mono">${esc(r.invoice)}</span> · read by ${esc(modeLabel(r.extraction_mode))}`;
      gWrap.scrollIntoView({ behavior: RM ? 'auto' : 'smooth', block: 'start' });
      // a. what the agent read, account number marked
      $('inv-text').innerHTML = esc(r.text).replace(new RegExp('(Account number:\\s*)(' + digits + ')'), `$1<mark class="${ok ? 'ok' : ''}">$2</mark>`).replace(/(IMPORTANT: our bank details have changed[^\n]*)/, '<mark>$1</mark>');
      $('inv-facts').innerHTML = Object.entries(r.extraction).filter(([k]) => !k.startsWith('_')).map(([k, f]) => `<div><dt>${esc(k.replace(/_/g, ' '))}</dt><dd>${k === 'account_number' ? `<span class="${ok ? 'right' : 'wrong'}">${esc(f.value)}</span>` : esc(String(f.value))} <span class="prov"><q>${esc(f.quote || '')}</q></span></dd></div>`).join('');
      steps.querySelector('[data-step="a"]').hidden = false; await pause(900);
      // b. the generated instruction
      const i = r.instruction;
      $('inv-instruction').innerHTML = [['Action', esc(i.action_type)], ['Payee', esc(i.supplier_name)], ['Account', `<span class="${ok ? 'right' : 'wrong'}">${esc(acct)}</span>${ok ? ' · on the customer-signed mandate' : ` · not on the mandate; the customer signed for <span class="mono">${esc(r.registered_payee || '—')}</span>`}`], ['Amount', gbp(i.amount) + ' ' + esc(i.currency)], ['Signed by', 'the agent key bound in agent_identity (Ed25519)']].map(([k, v_]) => `<div><dt>${k}</dt><dd>${v_}</dd></div>`).join('');
      const chv = $('inv-chain');
      if (r.chain && r.result.chain) { chv.hidden = false; chv.innerHTML = `<strong>Delegation chain</strong> <span class="small">the orchestrator read the invoice and delegated exactly what it read to the execution agent, which signed</span>` + chainHtml(r.result.chain); }
      else if (r.chain) { chv.hidden = false; chv.innerHTML = '<strong>Delegation chain</strong> <span class="small">presented; the bank refused before reaching it</span>'; }
      else chv.hidden = true;
      steps.querySelector('[data-step="b"]').hidden = false; await pause(900);
      // c. the checks run; then one line with what only the invoice path adds
      const res = r.result;
      const subject = { action_type: i.action_type, supplier_name: i.supplier_name, payee_account_ref: acct, amount: i.amount, signer: 'agent', invoice: r.invoice };
      await judge(subject, res);
      const box = $('inv-verdict'); box.className = 'invoice__verdict invoice__verdict--' + res.decision;
      box.innerHTML = `<span class="t-verdict t-verdict--${res.decision}">${res.decision}</span> <b>${res.decision === 'ALLOW' ? 'all nine checks passed' : esc(res.rule) + ' · ' + esc(res.code)}</b>${res.rule === 'R.6' && res.decision === 'DENY' ? ' · named-beneficiary mandate check (FATF 2025 AML/CFT alignment): the customer signed for accounts, not names' : ''}${res.violation ? ` · violation #${res.violation.id} recorded ${esc(res.violation.status)}` : ''}${res.signature ? ` · R.4 instruction signature: ${res.signature.checked ? (res.signature.verified ? 'VERIFIED' : 'FAILED') : 'not reached'}` : ''}`;
      out.hidden = false; box.hidden = false;
      logLine(subject, res);
      await pause(700);
      // d. caption
      $('inv-caption').textContent = ok
        ? 'The AI read a genuine invoice and paid the account the customer signed for. Same agent, same mandate: the next invoice is the test.'
        : 'The AI read a manipulated invoice and would have paid the wrong account. The mandate stopped it.';
      $('inv-caption').hidden = false;
    }

    // ── the eight instructions ──
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
      const sigLine = r.signature ? `<span class="t-sig">R.4 instruction signature: <b class="${r.signature.verified ? 'ok' : 'fail'}">${r.signature.checked ? (r.signature.verified ? 'VERIFIED' : 'FAILED') : 'not reached'}</b> (${esc(r.signature.alg)}) · agent key ${esc(r.signature.agent_kid || '—')} · payload sha256 ${esc((r.signature.instruction_hash || '').slice(0, 12))}</span>` : '';
      const chainLine = r.chain ? `<span class="t-chain">${esc(r.chain.invariant)} · ${r.chain.checks.map(c => `<b class="${c.ok ? 'ok' : 'fail'}">${esc(c.id)} ${c.ok ? '✓' : '✗'}</b>`).join(' ')} · S1 ${esc((r.chain.scopes.S1.beneficiaries || []).join(', '))} ≤ ${gbp(r.chain.scopes.S1.ceiling)}</span>` : '';
      const rv = r.rails && r.rails.vouch, reg = r.rails && r.rails.authority_registry;
      const rails = r.rails ? `<span class="t-rails">authority registry <b class="${reg !== 'active' ? 'refused' : ''}">${esc(reg)}</b> · vouch rail <b class="${rv.status === 'REVOKED' ? 'refused' : ''}">${esc(rv.status || 'none')}</b>${rv.voucher_id ? ' ' + esc(rv.voucher_id) : ''}${reg !== 'active' && rv.status === 'REVOKED' ? ' · one supervisory action, two rails refuse' : ''}</span>` : '';
      return el('li', null, `<span class="t-time">${t(new Date().toISOString())}</span><span class="t-body">
        <span class="t-head"><span class="t-action">${esc(b.action_type)} · ${esc(b.supplier_name)} · ${esc(b.payee_account_ref)} · ${gbp(b.amount)}${k ? ' · #' + k : ''}${b.signer === 'rogue' ? ' · signed with rogue key' : ''}</span><span class="t-verdict t-verdict--${r.decision}">${r.decision}</span><span class="t-rule">${r.decision === 'ALLOW' ? 'all nine checks passed · ' + esc(r.code) : 'rule ' + esc(r.rule) + ' · ' + esc(r.code)}</span></span>
        <span class="t-reason">${esc(r.reason)}${r.decision === 'DENY' && r.rule === 'R.6' ? ' · Named-beneficiary mandate check (FATF 2025 AML/CFT alignment)' : ''}</span>${sigLine}${chainLine}${settle}${rails}
        <span class="t-trace">${trace}</span>
        <span class="t-meta">audit #${r.audit_id} <b>${esc(r.audit_hash.slice(0, 12))}</b> ← <b>${esc(r.prev_hash.slice(0, 12))}</b> · rule pack <b>${esc(r.rule_pack)}</b> · receipt signed by authority · decision replayable</span>
        <details class="receipt"><summary>receipt</summary>${esc(r.receipt)}</details></span>`);
    }
  }

  // ───────────── Audit ─────────────
  async function audit() {
    const data = await api('GET', '/api/audit');
    $('au-count').textContent = data.rows.length;
    $('au-chain').innerHTML = data.chain.ok ? '<span class="tag tag--green">Intact</span>' : `<span class="tag tag--red">Broken at #${data.chain.broken_at}</span>`;
    $('au-head').textContent = (data.chain.head || '').slice(0, 16);
    const tb = $('au-table').querySelector('tbody'); tb.innerHTML = '';
    let run = 0, same = 0;
    for (const r of data.rows) {
      const e = { ...r.entry }; delete e.ts; delete e.presented_envelope; if (e.instruction) { e.instruction = { ...e.instruction }; delete e.instruction.agent_signature; } delete e.trace;
      const extra = r.kind === 'verify' ? ` → <strong>${esc(e.decision)}</strong> ${esc(e.rule)} ${esc(e.code)}${e.ledger_total_before ? ` (ledger before ${gbp(e.ledger_total_before)})` : ''}` : '';
      tb.append(el('tr', null, `<td>${r.id}</td><td class="mono small">${t(r.ts)}</td><td>${esc(r.kind)}</td><td class="mono small">${esc(r.subject || '')}</td><td class="small">${esc(e.event || '')}${extra}${e.reason ? ` — ${esc(e.reason)}` : ''}${e.note ? ` — “${esc(e.note)}”` : ''}${e.detail ? ` — ${esc(e.detail)}` : ''}</td><td class="hash">${esc(r.hash.slice(0, 12))}<br>← ${esc(r.prev_hash.slice(0, 12))}</td><td class="small" id="au-r-${r.id}">${r.receipt ? '<span class="tag tag--green">receipt</span> ' : ''}${r.kind === 'verify' ? `<button class="link" data-replay="${r.id}" type="button">replay</button>` : ''}</td>`));
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

  document.addEventListener('DOMContentLoaded', () => {
    const mt = $('menu-toggle');
    const paintMenu = () => { const hidden = document.body.classList.contains('menu-hidden'); mt.textContent = hidden ? 'Show menu' : 'Hide menu'; mt.setAttribute('aria-expanded', String(!hidden)); };
    if (mt) { paintMenu(); mt.onclick = () => { document.body.classList.toggle('menu-hidden'); try { localStorage.setItem('ap.menu', document.body.classList.contains('menu-hidden') ? 'hidden' : 'shown'); } catch (e) {} paintMenu(); }; }
    const rb = $('demo-reset');
    if (rb) rb.onclick = async () => { if (confirm('Reset the demo to its baseline? Everything is deleted, then one registration is reviewed, approved and the customer mandate signed, so the passport is ACTIVE with no payments and no violations.')) { rb.disabled = true; rb.textContent = 'seeding…'; await api('POST', '/api/demo/seed?stage=issued'); location.href = '/bank'; } };
  });

  return { provider, regulator, customer, bank, audit };
})();
