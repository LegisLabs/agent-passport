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
    if (!r.ok) throw new Error(j.detail || r.statusText);
    return j;
  }
  const statusTag = (s) => ({ active: 'green', approved: 'green', submitted: 'blue', info_requested: 'amber', suspended: 'amber', draft: 'grey', rejected: 'red', revoked: 'red', expired: 'red', signed: 'green', unsigned: 'amber' }[s] || 'grey');
  const tag = (s, label) => `<span class="tag tag--${statusTag(s)}">${esc(label || String(s).replace('_', ' '))}</span>`;
  const v = (f, ...path) => { let c = f; for (const p of path) { if (!c || typeof c !== 'object' || !(p in c)) return undefined; c = c[p]; } return (c && typeof c === 'object' && 'value' in c) ? c.value : c; };
  const NUMERIC = new Set(['per_payment_limit_gbp', 'monthly_limit_per_account_gbp', 'human_confirm_above_gbp', 'cover_gbp']);

  const LABELS = {
    provider: { title: 'Provider', legal_name: 'Legal name', licence_ref: 'Licence reference', companies_house_number: 'Companies House number', permissions: 'Licence permissions' },
    accountable_person: { title: 'Accountable person', name: 'Named responsible individual', role: 'Role or title', email: 'Contact email', declaration_ref: 'Declaration reference', declaration_accepted: 'Accepts responsibility for the agent’s actions' },
    insurance: { title: 'Insurance', provider: 'Insurer', policy_ref: 'Policy reference', cover_gbp: 'Cover (£)', valid_until: 'In force until' },
    agent: { title: 'The agent', agent_name: 'Agent name', agent_id: 'Agent identifier', software: 'Software', software_version: 'Version', model_provider: 'Model provider', config_hash: 'Configuration SHA-256' },
    customer: { title: 'Customer', legal_name: 'Legal name', companies_house_number: 'Companies House number', authorising_officer: 'Authorising officer', officer_role: 'Officer role' },
    mandate: { title: 'Requested mandate', action_type: 'Action type', per_payment_limit_gbp: 'Per-payment limit (£)', monthly_limit_per_account_gbp: '30-day limit per supplier account (£)', valid_until: 'Valid until', human_confirm_above_gbp: 'Proposed human confirmation above (£)' },
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
  const modeLabel = (m) => m === 'gemini' ? 'Gemini (live)' : m === 'fixture' ? 'fixture (deterministic stand-in)' : 'fixture after Gemini failed';

  // ───────────── Provider (operator) ─────────────
  async function provider() {
    let state = await api('GET', '/api/state');
    let a = pick(state.applications);
    render();

    async function refresh() { state = await api('GET', '/api/state'); a = state.applications.find(x => x.id === (a && a.id)) || pick(state.applications); render(); }

    function render() {
      applist(state.applications);
      const has = !!a;
      $('btn-new').hidden = has && a.status === 'draft';
      $('btn-new').textContent = has ? 'Start another application' : 'Start application';
      $('btn-extract').hidden = !has || a.status !== 'draft' || !!a.fields;
      renderDocs();
      const facts = has && a.fields;
      for (const n of [2, 3, 4]) document.querySelector(`[data-step="${n}"]`).hidden = !facts;
      if (facts) {
        $('facts-meta').textContent = `read by ${modeLabel(a.extraction_mode)}`;
        renderFacts(a.fields, a.status === 'draft');
        renderAgent();
      }
      $('extract-note').textContent = has && a.status === 'draft' && !a.fields ? `Reference ${a.ref} · draft` : '';
      const submitted = has && a.status !== 'draft';
      $('btn-submit').hidden = submitted || !(a && a.agent && a.agent.pop_verified);
      $('confirm').hidden = !submitted;
      if (submitted) $('confirm-ref').textContent = a.ref;
    }

    function renderDocs() {
      const ul = $('docs'); ul.innerHTML = '';
      const docs = a ? a.documents : [];
      docs.forEach((doc) => {
        const b = el('button', null, esc(doc.name)); b.type = 'button'; b.setAttribute('aria-pressed', 'false');
        b.onclick = () => { const open = b.getAttribute('aria-pressed') === 'true'; ul.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', 'false')); $('doc-view').hidden = open; if (!open) { b.setAttribute('aria-pressed', 'true'); $('doc-view').textContent = doc.text; } };
        ul.append(el('li', null).appendChild(b).parentElement);
      });
      if (!docs.length) ul.append(el('li', 'small', 'Start an application to load the evidence pack.'));
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
          const prov = fact.source_doc ? `<span class="prov">from <span class="mono">${esc(fact.source_doc)}</span>: <q>${esc(fact.quote || '')}</q></span>` : '<span class="prov">not found in the documents</span>';
          dl.append(el('div', 'fact', `<dt>${esc(label)}</dt><dd>${input}${prov}</dd>`));
        }
        box.append(dl);
      }
      box.append(el('h3', null, 'Suppliers the agent may pay (the allowlist the customer will sign)'));
      const tbl = el('table', 'suppliers', '<thead><tr><th>ID</th><th>Supplier</th><th>Account (sort code, number)</th><th>Source</th></tr></thead>');
      const tb = el('tbody');
      (f.suppliers || []).forEach((s, i) => tb.append(el('tr', null, `<td class="mono">${esc(s.supplier_id)}</td><td><input class="input" data-supplier="${i}" data-key="name" value="${esc(s.name)}" ${editable ? '' : 'disabled'} aria-label="Supplier name"></td><td><input class="input mono" data-supplier="${i}" data-key="account_ref" value="${esc(s.account_ref)}" ${editable ? '' : 'disabled'} aria-label="Account reference"></td><td class="prov small"><q>${esc(s.quote || '')}</q></td>`)));
      tbl.append(tb); box.append(tbl);
      $('btn-save-fields').hidden = !editable;
    }

    function collectFields() {
      const f = JSON.parse(JSON.stringify(a.fields));
      document.querySelectorAll('#facts [data-sec]').forEach(inp => {
        const cur = f[inp.dataset.sec][inp.dataset.key] || (f[inp.dataset.sec][inp.dataset.key] = {});
        cur.value = inp.type === 'checkbox' ? inp.checked : (inp.value === '' ? null : (NUMERIC.has(inp.dataset.key) && !isNaN(inp.value) ? Number(inp.value) : inp.value));
      });
      document.querySelectorAll('#facts [data-supplier]').forEach(inp => { f.suppliers[+inp.dataset.supplier][inp.dataset.key] = inp.value; });
      return f;
    }

    function renderAgent() {
      const ag = a.agent, dl = $('agent-kv'); dl.innerHTML = '';
      if (!ag || !ag.kid) { dl.innerHTML = '<div><dt>Agent key</dt><dd>not generated</dd></div>'; $('btn-key').hidden = a.status !== 'draft'; $('btn-sign').hidden = true; return; }
      dl.innerHTML = `<div><dt>Agent</dt><dd class="mono">${esc(ag.agent_id)}</dd></div><div><dt>Public key</dt><dd class="mono small">Ed25519 · kid ${esc(ag.kid)} · x=${esc(ag.jwk.x)}</dd></div><div><dt>Challenge (nonce)</dt><dd class="mono small">${esc(ag.challenge)}</dd></div><div><dt>Proof of possession</dt><dd>${ag.pop_verified ? '<span class="tag tag--green">Verified</span> signature over the nonce checks against the submitted key' : '<span class="tag tag--amber">Pending</span> challenge not yet signed'}</dd></div>${a.agent_identity_jwt ? '<div><dt>Agent identity</dt><dd><span class="tag tag--green">Signed</span> by the provider’s key at submission</dd></div>' : ''}`;
      $('btn-key').hidden = true; $('btn-sign').hidden = !!ag.pop_verified || a.status !== 'draft';
    }

    $('btn-new').onclick = async () => { a = await api('POST', '/api/applications'); history.replaceState(null, '', `?ref=${a.ref}`); await refresh(); };
    $('btn-extract').onclick = async () => { const b = $('btn-extract'); b.disabled = true; b.textContent = 'Reading documents…'; try { a = await api('POST', `/api/applications/${a.id}/extract`); } finally { b.disabled = false; b.textContent = 'Read documents into facts'; } await refresh(); };
    $('btn-save-fields').onclick = async () => { a = await api('PUT', `/api/applications/${a.id}/fields`, { fields: collectFields() }); $('save-note').textContent = 'Saved ' + t(new Date().toISOString()); await refresh(); };
    $('btn-key').onclick = async () => { await api('PUT', `/api/applications/${a.id}/fields`, { fields: collectFields() }); a = await api('POST', `/api/applications/${a.id}/agent-key`); await refresh(); };
    $('btn-sign').onclick = async () => { a = await api('POST', `/api/applications/${a.id}/sign-challenge`); await refresh(); };
    $('btn-submit').onclick = async () => { await api('PUT', `/api/applications/${a.id}/fields`, { fields: collectFields() }); a = await api('POST', `/api/applications/${a.id}/submit`); await refresh(); window.scrollTo({ top: document.body.scrollHeight }); };
  }

  // ───────────── Regulator ─────────────
  function envelopePanels(full) {
    const pl = full, ver = full.verification.parts, a = pl.assurance, i = pl.agent_identity, m = pl.mandate, mp = pl.mandate_proposed;
    const ad = (m || mp).authorization_details[0];
    const sig = (ok, who, kid) => ok == null ? `<span class="tag tag--amber">Unsigned</span>` : ok ? `<span class="tag tag--green">Verified · Ed25519</span>` : `<span class="tag tag--red">Signature fails</span>`;
    const kv = (rows) => `<dl class="envelope__kv">${rows.map(([k, val]) => `<div><dt>${k}</dt><dd>${val}</dd></div>`).join('')}</dl>`;
    return `
      <section>
        <span class="envelope__who">Signed by the authority</span>
        <h3 class="envelope__title">Assurance ${sig(ver.assurance)}</h3>
        ${kv([['Provider', `${esc(a.provider.legal_name)} · <span class="mono">${esc(a.provider.licence_ref)}</span>`], ['KY-A status', `${esc(a.assurance.kya_status)} · ${a.assurance.checks_passed} checks passed${a.assurance.checks_flagged.length ? ', flagged ' + esc(a.assurance.checks_flagged.join(', ')) : ''}`], ['Condition', `hold above ${gbp(a.condition.human_confirm_above.amount)}`], ['Accountable', `${esc(a.accountable_person.name)}, ${esc(a.accountable_person.role)} · <span class="mono small">${esc(a.accountable_person.declaration_ref)}</span>`], ['Valid until', esc(a.valid_until)], ['Bound to', `agent identity <span class="mono small">${esc(a.binds.agent_identity_sha256.slice(0, 12))}…</span>`]])}
      </section>
      <section>
        <span class="envelope__who">Signed by the provider</span>
        <h3 class="envelope__title">Agent identity ${sig(ver.agent_identity)}</h3>
        ${kv([['Agent', `${esc(i.agent.name)} · <span class="mono">${esc(i.agent.agent_id)}</span>`], ['Public key', `<span class="mono small">kid ${esc(full.minimal.agent_kid)}</span>`], ['Software', `${esc(i.agent.software)} ${esc(i.agent.software_version)}`], ['Model provider', esc(i.agent.model_provider)], ['Config SHA-256', `<span class="mono small">${esc((i.agent.config_sha256 || '').slice(0, 16))}…</span>`]])}
      </section>
      <section>
        <span class="envelope__who">Signed by the customer</span>
        <h3 class="envelope__title">Mandate ${sig(ver.mandate)}</h3>
        ${kv([['Customer', esc(mp.customer.legal_name)], ['Officer', `${esc(mp.authorising_officer.name)}, ${esc(mp.authorising_officer.role)}`], ['Payees', `${ad.supplier_allowlist.length} supplier accounts`], ['Per payment', gbp(ad.per_payment_limit.amount)], ['Per account, 30 days', gbp(ad.monthly_limit_per_account.amount)], ['Expires', esc(mp.valid_until)]])}
        ${m ? '' : `<p class="envelope__pending">Awaiting the finance director’s signature in <a href="/customer">Sign mandate</a>. Until then the bank refuses every instruction at R.5.</p>`}
      </section>`;
  }

  async function regulator() {
    let state = await api('GET', '/api/state');
    let a = pick(state.applications.filter(x => x.status !== 'draft')) || pick(state.applications);
    let p = null;
    render();

    async function refresh() { state = await api('GET', '/api/state'); a = state.applications.find(x => x.id === a.id) || a; render(); }
    function passportFor() { return a ? state.passports.find(x => x.application_id === a.id) : null; }

    function render() {
      applist(state.applications);
      const has = a && a.status !== 'draft';
      $('rg-empty').hidden = !!has; $('rg-case').hidden = !has;
      $('rg-ref').textContent = a ? a.ref : '—';
      $('rg-status').innerHTML = a ? tag(a.status) : '';
      if (!has) return;
      const f = a.fields;
      $('rg-summary').innerHTML = [
        ['Provider', `${esc(v(f, 'provider', 'legal_name'))} · licence <span class="mono">${esc(v(f, 'provider', 'licence_ref'))}</span> · Companies House <span class="mono">${esc(v(f, 'provider', 'companies_house_number'))}</span>`],
        ['Accountable person', `${esc(v(f, 'accountable_person', 'name'))}, ${esc(v(f, 'accountable_person', 'role'))} · ${v(f, 'accountable_person', 'declaration_accepted') ? `declaration <span class="mono">${esc(v(f, 'accountable_person', 'declaration_ref'))}</span> signed` : '<strong>no declaration</strong>'}`],
        ['Insurance', `${esc(v(f, 'insurance', 'provider'))} · <span class="mono">${esc(v(f, 'insurance', 'policy_ref'))}</span> · ${gbp(v(f, 'insurance', 'cover_gbp'))} until ${esc(v(f, 'insurance', 'valid_until'))}`],
        ['Agent', `${esc(v(f, 'agent', 'agent_name'))} <span class="mono">${esc(v(f, 'agent', 'agent_id'))}</span> · ${esc(v(f, 'agent', 'software'))} ${esc(v(f, 'agent', 'software_version'))} · ${esc(v(f, 'agent', 'model_provider'))} · key kid <span class="mono">${esc(a.agent && a.agent.kid)}</span> ${a.agent && a.agent.pop_verified ? '<span class="tag tag--green">possession proven</span>' : '<span class="tag tag--red">possession not proven</span>'} ${a.agent_identity_jwt ? '<span class="tag tag--green">identity signed by provider</span>' : ''}`],
        ['Customer', `${esc(v(f, 'customer', 'legal_name'))} · Companies House <span class="mono">${esc(v(f, 'customer', 'companies_house_number'))}</span> · officer ${esc(v(f, 'customer', 'authorising_officer'))}, ${esc(v(f, 'customer', 'officer_role'))}`],
        ['Requested mandate', `<strong>${esc(v(f, 'mandate', 'action_type'))}</strong> · ${gbp(v(f, 'mandate', 'per_payment_limit_gbp'))} per payment · ${gbp(v(f, 'mandate', 'monthly_limit_per_account_gbp'))} per supplier account in 30 days · until ${esc(v(f, 'mandate', 'valid_until'))} · provider proposes confirmation above ${gbp(v(f, 'mandate', 'human_confirm_above_gbp'))}`],
      ].map(([k, val]) => `<div><dt>${k}</dt><dd>${val}</dd></div>`).join('');
      const sb = $('rg-suppliers').querySelector('tbody'); sb.innerHTML = '';
      (f.suppliers || []).forEach(s => sb.append(el('tr', null, `<td><span class="mono">${esc(s.supplier_id)}</span> ${esc(s.name)}</td><td class="mono">${esc(s.account_ref)}</td><td class="small"><q>${esc(s.quote || '')}</q></td>`)));
      const cb = $('rg-checks').querySelector('tbody'); cb.innerHTML = '';
      (a.checks || []).forEach(c => cb.append(el('tr', null, `<td>${esc(c.id)}</td><td>${esc(c.title)} <span class="tag tag--${c.status === 'CURRENT' ? 'green' : 'grey'}">${esc(c.status)}</span><br><span class="small">${esc(c.detail)}</span></td><td>${esc(c.source)}<br><span class="small">${esc(c.evidence)}</span></td><td>${c.result === 'pass' ? '<span class="tag tag--green">Pass</span>' : '<span class="tag tag--amber">Flag</span>'}</td>`)));
      $('rg-filenote').value = a.file_note || '';
      if (v(f, 'mandate', 'human_confirm_above_gbp') && !$('rg-condition').dataset.touched) $('rg-condition').value = v(f, 'mandate', 'human_confirm_above_gbp');
      p = passportFor();
      $('rg-decide').hidden = !(a.status === 'submitted' || a.status === 'info_requested');
      $('rg-issued').hidden = !p;
      if (p) renderPassport(p);
      const inc = $('rg-incidents'); inc.innerHTML = '';
      const mine = (state.incidents || []).filter(i => !p || i.subject === p.passport_id);
      mine.forEach(i => inc.append(el('li', null, `<time>${t(i.ts)}</time><span>${tag('revoked', 'Incident')} ${esc(i.entry.event)}: ${esc(i.entry.reason)} · last refusal ${esc(i.entry.last_rule)} ${esc(i.entry.last_code)} · audit #${i.id} <span class="mono small">${esc(i.hash.slice(0, 12))}</span></span>`)));
      if (!mine.length) inc.append(el('li', 'log__empty', 'No incidents.'));
      const hist = $('rg-history'); hist.innerHTML = '';
      const lines = [];
      if (a.submitted_at) lines.push([a.submitted_at, 'Application submitted; agent identity signed by the provider; automated checks run.']);
      if (a.officer_note) lines.push([a.decided_at || a.submitted_at, `${a.officer}: ${a.status.replace('_', ' ')} — “${a.officer_note}”`]);
      if (p && p.mandate_signed_at) lines.push([p.mandate_signed_at, `${p.mandate.signed_by.name}, ${p.mandate.signed_by.role} (customer): mandate signed.`]);
      (p ? p.history : []).forEach(h => lines.push([h.ts, `${h.officer}: ${h.from ? h.from + ' → ' : ''}${h.to} — ${h.reason}`]));
      lines.sort((x, y) => x[0] < y[0] ? -1 : 1).reverse().forEach(([ts, txt]) => hist.append(el('li', null, `<time>${t(ts)}</time><span>${esc(txt)}</span>`)));
      if (!lines.length) hist.append(el('li', 'log__empty', 'Nothing yet.'));
    }

    async function renderPassport(p) {
      $('pp-id').textContent = p.passport_id;
      $('pp-status').innerHTML = tag(p.status);
      $('btn-suspend').hidden = p.status !== 'active'; $('btn-reinstate').hidden = p.status !== 'suspended'; $('btn-revoke').hidden = p.status === 'revoked';
      const full = await api('GET', `/api/passports/${p.passport_id}`);
      const env = $('envelope');
      env.innerHTML = envelopePanels(full);
      env.classList.toggle('envelope--incomplete', !full.mandate_signed);
      env.classList.toggle('envelope--revoked', p.status === 'revoked');
      renderRail(p, null);
      $('jwt-panels').innerHTML = ['assurance', 'agent_identity', 'mandate'].map(k => full.envelope[k] ? `<h4 class="h4">${k} <span class="small">header ${esc(JSON.stringify(full.headers[k]))}</span></h4><pre class="code">${esc(JSON.stringify(full[k], null, 2))}</pre><pre class="code code--wrap">${esc(full.envelope[k])}</pre>` : `<h4 class="h4">${k}</h4><p class="small">not yet signed</p>`).join('');
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
    let p = state.passports.find(x => x.passport_id === ref) || state.passports[0] || null;
    render();

    function render() {
      const ul = $('cu-list'); ul.innerHTML = state.passports.length ? '' : '<li class="small">None yet.</li>';
      state.passports.forEach(x => ul.append(el('li', null, `<a href="/customer?ref=${x.passport_id}" class="mono">${esc(x.passport_id)}</a> ${tag(x.mandate_signed ? 'signed' : 'unsigned', x.mandate_signed ? 'signed' : 'awaiting signature')}`)));
      $('cu-empty').hidden = !!p; $('cu-mandate').hidden = !p;
      if (!p) return;
      const mp = p.mandate_proposed, ad = mp.authorization_details[0], signed = p.mandate_signed;
      $('cu-id').textContent = p.passport_id;
      $('cu-state').innerHTML = signed ? tag('signed', 'signed') : tag('unsigned', 'awaiting signature');
      $('cu-card').classList.toggle('mandate--signed', signed);
      $('cu-kv').innerHTML = [['Agent', `${esc(p.agent_identity.agent.name)} · <span class="mono">${esc(mp.agent_id)}</span> · key kid <span class="mono">${esc(mp.agent_kid)}</span>`], ['Operated by', `${esc(mp.provider)} · assured by the ${esc(p.assurance.iss)} until ${esc(p.assurance.valid_until)}`], ['Action', `<strong>${esc(ad.actions.join(', '))}</strong> in ${esc(ad.currency)}`], ['Per payment', `not more than ${gbp(ad.per_payment_limit.amount)}`], ['Per supplier account', `not more than ${gbp(ad.monthly_limit_per_account.amount)} in any rolling 30 days`], ['Supervisor condition', `the bank holds anything above ${gbp(p.assurance.condition.human_confirm_above.amount)} for your confirmation`], ['Expires', esc(mp.valid_until)]].map(([k, val]) => `<div><dt>${k}</dt><dd>${val}</dd></div>`).join('');
      const tb = $('cu-suppliers').querySelector('tbody'); tb.innerHTML = '';
      ad.supplier_allowlist.forEach(s => tb.append(el('tr', null, `<td><span class="mono">${esc(s.supplier_id)}</span> ${esc(s.name)}</td><td class="mono">${esc(s.account_ref)}</td>`)));
      $('cu-signer').textContent = `${mp.authorising_officer.name}, ${mp.authorising_officer.role}, signs with the ${mp.customer.legal_name} key.`;
      $('cu-actions').hidden = signed || p.status === 'revoked';
      $('cu-sig').hidden = !signed;
      if (signed) $('cu-sig').innerHTML = `<strong>Signed ${d(p.mandate_signed_at)} at ${t(p.mandate_signed_at)} by ${esc(p.mandate.signed_by.name)}, ${esc(p.mandate.signed_by.role)}</strong> Ed25519 signature by the ${esc(mp.customer.legal_name)} key. The envelope is complete.`;
      $('cu-after').hidden = !signed;
      $('cu-jwt-wrap').hidden = !signed;
      if (signed) api('GET', `/api/passports/${p.passport_id}`).then(full => { $('cu-jwt-payload').textContent = JSON.stringify(full.mandate, null, 2); $('cu-jwt').textContent = full.envelope.mandate; });
    }
    $('btn-sign-mandate').onclick = async () => {
      const b = $('btn-sign-mandate'); b.disabled = true; $('cu-error').hidden = true;
      try { await api('POST', `/api/passports/${p.passport_id}/mandate/sign`); state = await api('GET', '/api/state'); p = state.passports.find(x => x.passport_id === p.passport_id); render(); }
      catch (e) { $('cu-error').textContent = e.message; $('cu-error').hidden = false; }
      finally { b.disabled = false; }
    };
  }

  // ───────────── Bank ─────────────
  async function bank() {
    let state = await api('GET', '/api/state');
    const ref = new URLSearchParams(location.search).get('ref');
    const p = state.passports.find(x => x.passport_id === ref) || state.passports[0] || null;
    const rules = (await api('GET', '/api/rulepack')).runtime_rules;
    const rl = $('rules'); rules.forEach(r => rl.append(el('li', null, `<code>${esc(r.id)}</code> ${esc(r.title)} → <code>${esc(r.on_fail)}</code> <span class="small">— ${esc(r.data)}</span>`)));
    const lines = $('term-lines');
    let denies = 0;

    async function strip() {
      if (!p) return;
      const full = await api('GET', `/api/passports/${p.passport_id}`);
      const m = full.minimal;
      $('st-id').textContent = m.passport_id;
      $('st-assurance').innerHTML = tag(m.status);
      $('st-mandate').innerHTML = tag(m.mandate_signed ? 'signed' : 'unsigned', m.mandate_signed ? 'signed' : 'not signed');
      $('st-payments').textContent = full.payments;
      api('GET', `/api/passports/${p.passport_id}/vouch`).then(x => { const st = (x.live && x.live.status) || x.recorded.status; $('st-vouch').innerHTML = `${tag(st === 'ACTIVE' ? 'active' : st === 'REVOKED' ? 'revoked' : 'grey', st || 'none')} <span class="small mono">${esc(x.voucher_id || '')}</span>`; }).catch(() => { $('st-vouch').textContent = '—'; });
      const mt = $('st-meters'); mt.innerHTML = '';
      const ad = (full.mandate || full.mandate_proposed).authorization_details[0];
      const cap = ad.monthly_limit_per_account.amount;
      ad.supplier_allowlist.forEach(s => {
        const total = (full.ledger[s.account_ref] || { total: 0 }).total;
        const pct = Math.min(1, total / cap);
        const row = el('div', null, `<span class="meters__k">${esc(s.name)}</span><span class="meters__v">${gbp(total)} of ${gbp(cap)}</span><span class="meter"><span class="meter__fill ${pct >= 1 ? 'over' : pct >= .75 ? 'warn' : ''}" style="transform:scaleX(${pct})"></span></span>`);
        mt.append(row);
      });
      $('rp-passport').innerHTML = [['Passport', `<span class="mono">${esc(m.passport_id)}</span>`], ['Issuer', esc(m.issuer)], ['Provider', `${esc(m.provider)} · <span class="mono">${esc(m.licence_ref)}</span>`], ['Agent', `${esc(m.agent)} · <span class="mono">${esc(m.agent_id)}</span> · key kid <span class="mono">${esc(m.agent_kid)}</span>`], ['Mandate', `${esc(m.scope.actions.join(', '))} · ${m.scope.suppliers} payee accounts · ${gbp(m.scope.per_payment_limit.amount)} per payment · ${gbp(m.scope.monthly_limit_per_account.amount)} per account in 30 days`], ['Condition', `hold above ${gbp(m.condition.human_confirm_above.amount)}`], ['Valid until', esc(m.valid_until)], ['Signatures', `<span class="mono small">assurance ${esc(m.signers.assurance)} · agent identity ${esc(m.signers.agent_identity)} · mandate ${esc(m.signers.mandate)}</span> ${full.verification.ok ? '<span class="tag tag--green">all three verify</span>' : `<span class="tag tag--amber">${esc(full.verification.failure.replace('_', ' '))}</span>`}`], ['Status (live)', `${tag(m.status)} <button class="link small" id="rp-recheck" type="button">re-check</button>`]].map(([k, val]) => `<div><dt>${k}</dt><dd>${val}</dd></div>`).join('');
      $('rp-recheck').onclick = strip;
      setDenies(denies);
    }
    function setDenies(n) { denies = n; $('denies').querySelectorAll('i').forEach((i, k) => i.classList.toggle('on', k < n)); }
    if (!p) $('rp-passport').innerHTML = '<div><dt>Passport</dt><dd>none issued yet — approve an application in <a href="/regulator">Review &amp; issue</a></dd></div>';
    else await strip();

    // ── Task 1: the agent reads an invoice ──
    const ib = $('invoice-buttons');
    (state.invoices || []).forEach(inv => {
      const b = el('button', 'btn ' + (inv.id.endsWith('clean') ? 'btn--secondary' : 'btn--warning'), esc(inv.label) + ' <span class="btn__sub mono">' + esc(inv.id) + '</span>'); b.type = 'button'; b.disabled = !p;
      b.onclick = async () => {
        ib.querySelectorAll('button').forEach(x => x.disabled = true); b.textContent = 'Agent reading…';
        try { const r = await api('POST', '/api/agent/invoice', { passport_id: p.passport_id, invoice_id: inv.id }); await showInvoice(r); await strip(); }
        catch (e) { alert(e.message); }
        finally { ib.querySelectorAll('button').forEach(x => x.disabled = false); b.innerHTML = esc(inv.label) + ' <span class="btn__sub mono">' + esc(inv.id) + '</span>'; }
      };
      ib.append(b);
    });
    const pause = (ms) => new Promise(r => setTimeout(r, ms));
    async function showInvoice(r) {
      const steps = $('invoice-steps'); steps.hidden = false;
      steps.querySelectorAll('.invoice__step').forEach(x => x.hidden = true);
      const acct = r.instruction.payee_account_ref, ok = r.on_allowlist;
      const digits = (r.extraction.account_number || {}).value || '';
      // a. what the agent read, account number marked
      $('inv-text').innerHTML = esc(r.text).replace(new RegExp('(Account number:\\s*)(' + digits + ')'), `$1<mark class="${ok ? 'ok' : ''}">$2</mark>`).replace(/(IMPORTANT: our bank details have changed[^\n]*)/, '<mark>$1</mark>');
      $('inv-facts').innerHTML = Object.entries(r.extraction).filter(([k]) => !k.startsWith('_')).map(([k, f]) => `<div><dt>${esc(k.replace(/_/g, ' '))}</dt><dd>${k === 'account_number' ? `<span class="${ok ? 'right' : 'wrong'}">${esc(f.value)}</span>` : esc(String(f.value))} <span class="prov">from <span class="mono">${esc(f.source_doc || '')}</span>: <q>${esc(f.quote || '')}</q></span></dd></div>`).join('') + `<div><dt>read by</dt><dd>${esc(modeLabel(r.extraction_mode))}</dd></div>`;
      steps.querySelector('[data-step="a"]').hidden = false; await pause(700);
      // b. the generated instruction
      const i = r.instruction;
      $('inv-instruction').innerHTML = [['Action', esc(i.action_type)], ['Payee', esc(i.supplier_name)], ['Account', `<span class="${ok ? 'right' : 'wrong'}">${esc(acct)}</span>${ok ? ' on the customer-signed mandate' : ` not on the mandate; the customer signed for <span class="mono">${esc(r.registered_payee || '—')}</span>`}`], ['Amount', gbp(i.amount) + ' ' + esc(i.currency)], ['Invoice', esc(i.invoice_ref)], ['Signed by', 'the agent key bound in agent_identity (Ed25519)']].map(([k, v_]) => `<div><dt>${k}</dt><dd>${v_}</dd></div>`).join('');
      steps.querySelector('[data-step="b"]').hidden = false; await pause(700);
      // c. the bank's decision
      const res = r.result;
      const box = $('inv-verdict'); box.className = 'invoice__verdict invoice__verdict--' + res.decision;
      const rulesHtml = res.trace.map(s => `<li class="${s.ok ? 'ok' : 'fail'}">${esc(s.rule)} ${s.ok ? '✓' : '✗'}</li>`).join('');
      box.innerHTML = `<div><span class="t-verdict t-verdict--${res.decision}" style="color:${res.decision === 'DENY' ? 'var(--red)' : res.decision === 'ALLOW' ? 'var(--green)' : 'var(--amber-ink)'}">${res.decision}</span> <strong>${esc(res.rule)} · ${esc(res.code)}</strong></div><div>${esc(res.reason)}</div><ul class="invoice__rules">${rulesHtml}</ul>${res.rule === 'R.6' && res.decision === 'DENY' ? '<div class="invoice__note">Named-beneficiary mandate check (FATF 2025 AML/CFT alignment). The customer signed for accounts, not names: a changed account on a genuine-looking invoice has no authority.</div>' : ''}${res.violation ? `<div class="invoice__note">Violation #${res.violation.id} recorded as ${esc(res.violation.status)} for the supervisor’s exception panel.</div>` : ''}${res.settlement ? `<div class="invoice__note">${esc(res.settlement.rail_reason)}</div>` : ''}<div class="invoice__note">audit #${res.audit_id} <span class="mono">${esc(res.audit_hash.slice(0, 12))}</span> · receipt signed by the authority · decision replayable</div>`;
      steps.querySelector('[data-step="c"]').hidden = false;
      if (lines.querySelector('.terminal__hint')) lines.innerHTML = '';
      lines.append(termLine({ action_type: i.action_type, supplier_name: i.supplier_name, payee_account_ref: acct, amount: i.amount, signer: 'agent' }, res)); lines.scrollTop = lines.scrollHeight;
      if (res.incident) { lines.append(el('li', 't-incident', `<span><b>INCIDENT</b> escalated to supervisor · ${res.incident.denies} refused instructions · audit #${res.incident.audit_id}</span>`)); setDenies(0); }
      else if (res.decision === 'DENY') setDenies(Math.min(3, (res.deny_count || denies + 1)));
      await pause(700);
      // d. caption
      $('inv-caption').textContent = ok
        ? 'The AI read a genuine invoice and paid the account the customer signed for. Same agent, same mandate: the next invoice is the test.'
        : 'The AI read a manipulated invoice and would have paid the wrong account. The mandate stopped it.';
      steps.querySelector('[data-step="d"]').hidden = false;
      steps.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    state.beats.forEach(b => {
      const btn = el('button', 'beat'); btn.type = 'button'; btn.disabled = !p;
      btn.innerHTML = `<span class="beat__label">${esc(b.label)}<small>${esc(b.hint)}</small></span><span class="beat__expect">${esc(b.expect)}</span>`;
      btn.onclick = async () => {
        btn.disabled = true; btn.dataset.running = 'true';
        try {
          for (let k = 0; k < (b.repeat || 1); k++) {
            const r = await api('POST', '/api/agent/act', { passport_id: p.passport_id, action_type: b.action_type, supplier_name: b.supplier_name, payee_account_ref: b.payee_account_ref, amount: b.amount, invoice_ref: b.repeat ? `${b.invoice_ref}-${k + 1}` : b.invoice_ref, signer: b.signer });
            if (lines.querySelector('.terminal__hint')) lines.innerHTML = '';
            lines.append(termLine(b, r, b.repeat ? k + 1 : null));
            if (r.incident) { lines.append(el('li', 't-incident', `<span><b>INCIDENT</b> escalated to supervisor · ${r.incident.denies} refused instructions · audit #${r.incident.audit_id} <b>${esc(r.incident.hash.slice(0, 12))}</b> · visible in the regulator’s incident feed</span>`)); setDenies(0); }
            else if (r.decision === 'DENY') setDenies(Math.min(3, (r.deny_count || denies + 1)));
            lines.scrollTop = lines.scrollHeight;
            if (r.decision !== 'ALLOW') break;
          }
          await strip();
        } finally { btn.disabled = false; delete btn.dataset.running; }
      };
      $('beats').append(el('li').appendChild(btn).parentElement);
    });
    function termLine(b, r, k) {
      const trace = r.trace.map(s => `<b>${esc(s.rule)}</b> ${s.ok ? '✓' : '✗'} ${esc(s.note)}`).join(' · ');
      const settle = r.settlement ? `<span class="t-settle">${esc(r.settlement.rail_reason)} · 30-day total for this account now ${gbp(r.settlement.ledger_total_after)}</span>` : '';
      const rv = r.rails && r.rails.vouch, reg = r.rails && r.rails.authority_registry;
      const rails = r.rails ? `<span class="t-rails">authority registry <b class="${reg !== 'active' ? 'refused' : ''}">${esc(reg)}</b> · vouch rail <b class="${rv.status === 'REVOKED' ? 'refused' : ''}">${esc(rv.status || 'none')}</b>${rv.voucher_id ? ' ' + esc(rv.voucher_id) : ''}${reg !== 'active' && rv.status === 'REVOKED' ? ' · one supervisory action, two rails refuse' : ''}</span>` : '';
      return el('li', null, `<span class="t-time">${t(new Date().toISOString())}</span><span class="t-body">
        <span class="t-head"><span class="t-action">${esc(b.action_type)} · ${esc(b.supplier_name)} · ${esc(b.payee_account_ref)} · ${gbp(b.amount)}${k ? ' · #' + k : ''}${b.signer === 'rogue' ? ' · signed with rogue key' : ''}</span><span class="t-verdict t-verdict--${r.decision}">${r.decision}</span><span class="t-rule">rule ${esc(r.rule)} · ${esc(r.code)}</span></span>
        <span class="t-reason">${esc(r.reason)}</span>${settle}${rails}
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
    $('btn-replay-all').onclick = async () => { for (const r of data.rows.filter(x => x.kind === 'verify')) await replay(r.id); $('replay-note').textContent = `${same} of ${run} verifications replayed identically`; };
  }

  document.addEventListener('DOMContentLoaded', () => {
    const rb = $('demo-reset');
    if (rb) rb.onclick = async () => { if (confirm('Reset the whole demo? All applications, passports, payments and audit entries are deleted.')) { await api('POST', '/api/reset'); location.href = '/provider'; } };
  });

  return { provider, regulator, customer, bank, audit };
})();
