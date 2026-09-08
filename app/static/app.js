/* Agent Passport v1 — view controllers. Server holds all state; this file renders it and calls the API. */
'use strict';

const AP = (() => {
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, html) => { const n = document.createElement(tag); if (cls) n.className = cls; if (html != null) n.innerHTML = html; return n; };
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const t = (iso) => iso ? new Date(iso).toLocaleTimeString('en-GB', { hour12: false }) : '';
  const d = (iso) => iso ? new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '';
  const gbp = (n) => '£' + Number(n || 0).toLocaleString('en-GB');
  const ROOT = document.body.dataset.root || '';
  async function api(method, url, body) {
    const r = await fetch(ROOT + url, { method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.detail || r.statusText);
    return j;
  }
  const statusTag = (s) => ({ active: 'green', approved: 'green', submitted: 'blue', info_requested: 'amber', suspended: 'amber', draft: 'grey', rejected: 'red', revoked: 'red', expired: 'red' }[s] || 'grey');
  const tag = (s) => `<span class="tag tag--${statusTag(s)}">${esc(String(s).replace('_', ' '))}</span>`;
  const v = (f, ...path) => { let c = f; for (const p of path) { if (!c || typeof c !== 'object' || !(p in c)) return undefined; c = c[p]; } return (c && typeof c === 'object' && 'value' in c) ? c.value : c; };

  const LABELS = {
    firm: { title: 'Firm identity', name: 'Firm name', asa_reference: 'Agent Services Account reference', gateway_id: 'Agent Government Gateway ID', companies_house_number: 'Companies House number' },
    accountable_person: { title: 'Accountable person', name: 'Named responsible individual', role: 'Role or title', professional_body: 'Professional body', email: 'Contact email', declaration_accepted: 'Accepts responsibility for the agent’s actions' },
    compliance: { title: 'Compliance', aml_supervisor: 'AML supervisory body', aml_reference: 'AML registration reference' },
    requested_authority: { title: 'Requested authority', task: 'Task', tax_year: 'Tax year', action_type: 'Action type', escalation_threshold_gbp: 'Hold for human review above (£ tax due)', valid_until: 'Requested validity (until)' },
    agent: { title: 'The agent', agent_id: 'Agent name or ID', software: 'Software', software_version: 'Version', model_provider: 'Model provider' },
  };

  function applist(apps, current) {
    const ul = $('applist'); if (!ul) return;
    ul.innerHTML = apps.length ? '' : '<li class="small">None yet.</li>';
    for (const a of apps) ul.append(el('li', null, `<a href="${location.pathname}?ref=${a.ref}" class="mono">${esc(a.ref)}</a> ${tag(a.status)}`));
  }
  function pick(apps) {
    const ref = new URLSearchParams(location.search).get('ref');
    return apps.find(a => a.ref === ref) || apps[0] || null;
  }

  // ───────────── Operator ─────────────
  async function operator() {
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
      document.querySelector('[data-step="2"]').hidden = !facts;
      document.querySelector('[data-step="3"]').hidden = !facts;
      document.querySelector('[data-step="4"]').hidden = !facts;
      if (facts) {
        $('facts-meta').textContent = `read by ${a.extraction_mode === 'gemini' ? 'Gemini (live)' : a.extraction_mode === 'fixture' ? 'fixture (deterministic stand-in)' : 'fixture after Gemini failed'}`;
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
      docs.forEach((doc, i) => {
        const b = el('button', null, esc(doc.name)); b.type = 'button';
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
          const fact = f[sec][k] || { value: null };
          const isBool = typeof fact.value === 'boolean';
          const input = isBool
            ? `<label><input type="checkbox" data-sec="${sec}" data-key="${k}" ${fact.value ? 'checked' : ''} ${editable ? '' : 'disabled'}> ${fact.value ? 'Yes' : 'No'}</label>`
            : `<input class="input" data-sec="${sec}" data-key="${k}" value="${esc(fact.value ?? '')}" ${editable ? '' : 'disabled'}>`;
          const prov = fact.source_doc ? `<span class="prov">from <span class="mono">${esc(fact.source_doc)}</span>: <q>${esc(fact.quote || '')}</q></span>` : '<span class="prov">not found in the documents</span>';
          dl.append(el('div', 'fact', `<dt>${esc(label)}</dt><dd>${input}${prov}</dd>`));
        }
        box.append(dl);
      }
      box.append(el('h3', null, 'Clients the agent will act for'));
      const tbl = el('table', 'clients', '<thead><tr><th>Client</th><th>UTR</th><th>Route</th><th>Authorised</th><th>Consent to automated processing</th><th>Source</th></tr></thead>');
      const tb = el('tbody');
      (f.clients || []).forEach((c, i) => tb.append(el('tr', null, `<td>${esc(c.name)}</td><td class="mono">${esc(c.utr)}</td><td>${esc(c.authorisation_route)}</td><td><input type="checkbox" data-client="${i}" data-key="authorisation_confirmed" ${c.authorisation_confirmed ? 'checked' : ''} ${editable ? '' : 'disabled'}></td><td><input type="checkbox" data-client="${i}" data-key="consent_automated_processing" ${c.consent_automated_processing ? 'checked' : ''} ${editable ? '' : 'disabled'}></td><td class="prov small"><q>${esc(c.quote || '')}</q></td>`)));
      tbl.append(tb); box.append(tbl);
      $('btn-save-fields').hidden = !editable;
    }

    function collectFields() {
      const f = JSON.parse(JSON.stringify(a.fields));
      document.querySelectorAll('#facts [data-sec]').forEach(inp => {
        const cur = f[inp.dataset.sec][inp.dataset.key] || (f[inp.dataset.sec][inp.dataset.key] = {});
        cur.value = inp.type === 'checkbox' ? inp.checked : (inp.value === '' ? null : (isNaN(inp.value) || inp.dataset.key !== 'escalation_threshold_gbp' ? inp.value : Number(inp.value)));
      });
      document.querySelectorAll('#facts [data-client]').forEach(inp => { f.clients[+inp.dataset.client][inp.dataset.key] = inp.checked; });
      return f;
    }

    function renderAgent() {
      const ag = a.agent, dl = $('agent-kv'); dl.innerHTML = '';
      if (!ag || !ag.kid) { dl.innerHTML = '<div><dt>Agent key</dt><dd>not generated</dd></div>'; $('btn-key').hidden = a.status !== 'draft'; $('btn-sign').hidden = true; return; }
      dl.innerHTML = `<div><dt>Agent</dt><dd class="mono">${esc(ag.agent_id)}</dd></div><div><dt>Public key</dt><dd class="mono small">Ed25519 · kid ${esc(ag.kid)} · x=${esc(ag.jwk.x)}</dd></div><div><dt>Challenge (nonce)</dt><dd class="mono small">${esc(ag.challenge)}</dd></div><div><dt>Proof of possession</dt><dd>${ag.pop_verified ? '<span class="tag tag--green">Verified</span> signature over the nonce checks against the submitted key' : '<span class="tag tag--amber">Pending</span> challenge not yet signed'}</dd></div>`;
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
        ['Firm', `${esc(v(f, 'firm', 'name'))} · ASA <span class="mono">${esc(v(f, 'firm', 'asa_reference'))}</span> · Companies House <span class="mono">${esc(v(f, 'firm', 'companies_house_number'))}</span>`],
        ['Accountable person', `${esc(v(f, 'accountable_person', 'name'))}, ${esc(v(f, 'accountable_person', 'role'))} (${esc(v(f, 'accountable_person', 'professional_body'))}) · ${v(f, 'accountable_person', 'declaration_accepted') ? 'declaration signed' : '<strong>no declaration</strong>'}`],
        ['AML supervision', `${esc(v(f, 'compliance', 'aml_supervisor'))} · <span class="mono">${esc(v(f, 'compliance', 'aml_reference'))}</span>`],
        ['Agent', `<span class="mono">${esc(v(f, 'agent', 'agent_id'))}</span> · ${esc(v(f, 'agent', 'software'))} ${esc(v(f, 'agent', 'software_version'))} · ${esc(v(f, 'agent', 'model_provider'))} · key kid <span class="mono">${esc(a.agent && a.agent.kid)}</span> ${a.agent && a.agent.pop_verified ? '<span class="tag tag--green">possession proven</span>' : '<span class="tag tag--red">possession not proven</span>'}`],
        ['Requested authority', `${esc(v(f, 'requested_authority', 'task'))} · tax year ${esc(v(f, 'requested_authority', 'tax_year'))} · <strong>${esc(String(v(f, 'requested_authority', 'action_type')).replace('_', ' '))}</strong> · hold above ${gbp(v(f, 'requested_authority', 'escalation_threshold_gbp'))} tax due · until ${esc(v(f, 'requested_authority', 'valid_until'))}`],
      ].map(([k, val]) => `<div><dt>${k}</dt><dd>${val}</dd></div>`).join('');
      const tb = $('rg-clients').querySelector('tbody'); tb.innerHTML = '';
      (f.clients || []).forEach(c => tb.append(el('tr', null, `<td>${esc(c.name)}</td><td class="mono">${esc(c.utr)}</td><td>${c.authorisation_confirmed ? '<span class="tag tag--green">confirmed</span>' : '<span class="tag tag--amber">not confirmed</span>'} <span class="small">${esc(c.authorisation_route)}</span></td><td>${c.consent_automated_processing ? '<span class="tag tag--green">consented</span>' : '<span class="tag tag--amber">no consent</span>'}</td>`)));
      const cb = $('rg-checks').querySelector('tbody'); cb.innerHTML = '';
      (a.checks || []).forEach(c => cb.append(el('tr', null, `<td>${esc(c.id)}</td><td>${esc(c.title)} <span class="tag tag--${c.status === 'CURRENT' ? 'green' : 'grey'}">${esc(c.status)}</span><br><span class="small">${esc(c.detail)}</span></td><td>${esc(c.source)}<br><span class="small">${esc(c.evidence)}</span></td><td>${c.result === 'pass' ? '<span class="tag tag--green">Pass</span>' : '<span class="tag tag--amber">Flag</span>'}</td>`)));
      $('rg-filenote').value = a.file_note || '';
      p = passportFor();
      $('rg-decide').hidden = !(a.status === 'submitted' || a.status === 'info_requested');
      $('rg-issued').hidden = !p;
      if (p) renderPassport(p);
      const hist = $('rg-history'); hist.innerHTML = '';
      const lines = [];
      if (a.submitted_at) lines.push([a.submitted_at, 'Application submitted; automated checks run.']);
      if (a.officer_note) lines.push([a.decided_at || a.submitted_at, `${a.officer}: ${a.status.replace('_', ' ')} — “${a.officer_note}”`]);
      (p ? p.history : []).forEach(h => lines.push([h.ts, `${h.officer}: ${h.from ? h.from + ' → ' : ''}${h.to} — ${h.reason}`]));
      lines.sort((x, y) => x[0] < y[0] ? -1 : 1).reverse().forEach(([ts, txt]) => hist.append(el('li', null, `<time>${t(ts)}</time><span>${esc(txt)}</span>`)));
      if (!lines.length) hist.append(el('li', 'log__empty', 'Nothing yet.'));
    }

    function renderPassport(p) {
      const pl = p.payload, ad = pl.authorization_details[0];
      $('pp-status').innerHTML = tag(p.status);
      $('rg-passport').classList.toggle('passport--revoked', p.status === 'revoked');
      $('pp-body').innerHTML = [
        ['Passport', `<span class="mono">${esc(pl.jti)}</span>`], ['Agent', `<span class="mono">${esc(pl.subject.agent_id)}</span>`],
        ['Accountable firm', esc(pl.subject.operator.firm)], ['Accountable person', esc(v(a.fields, 'accountable_person', 'name')) + ' <span class="small">(held by the authority; not in the token)</span>'],
        ['Granted scope', `${esc(ad.task)} · ${esc(ad.tax_year)} · <strong>${esc(ad.action_type.replace('_', ' '))}</strong> · authorised clients only`], ['Human review above', gbp(ad.escalation_threshold.amount) + ' tax due'],
        ['Issued', d(p.issued_at)], ['Expires', d(pl.valid_until)],
        ['Agent key', `<span class="mono small">kid ${esc(a.agent.kid)}</span>`], ['Signature', `<span class="tag tag--green">Ed25519</span> <span class="mono small">issued by ${esc(pl.issued_by)}</span>`],
      ].map(([k, val]) => `<div><span class="passport__k">${k}</span><span class="passport__v">${val}</span></div>`).join('');
      $('btn-suspend').hidden = p.status !== 'active'; $('btn-reinstate').hidden = p.status !== 'suspended'; $('btn-revoke').hidden = p.status === 'revoked';
      api('GET', `/api/passports/${p.jti}`).then(full => { $('jwt-header').textContent = JSON.stringify(full.header, null, 2); $('jwt-payload').textContent = JSON.stringify(full.payload, null, 2); $('jwt-compact').textContent = full.jwt; });
    }

    async function decide(decision) {
      const note = $('rg-officer-note').value.trim();
      $('decide-error').hidden = true;
      try { await api('POST', `/api/applications/${a.id}/decision`, { decision, note }); await refresh(); }
      catch (e) { $('decide-error').textContent = e.message; $('decide-error').hidden = false; }
    }
    async function life(status) {
      const reason = $('rg-reason').value.trim(); $('life-error').hidden = true;
      try { await api('POST', `/api/passports/${p.jti}/status`, { status, reason }); $('rg-reason').value = ''; await refresh(); }
      catch (e) { $('life-error').textContent = e.message; $('life-error').hidden = false; }
    }
    $('btn-approve').onclick = () => decide('approve');
    $('btn-info').onclick = () => decide('request_info');
    $('btn-reject').onclick = () => decide('reject');
    $('btn-suspend').onclick = () => life('suspended');
    $('btn-reinstate').onclick = () => life('active');
    $('btn-revoke').onclick = () => life('revoked');
    $('btn-renew').onclick = async () => { const r = await api('POST', `/api/passports/${p.jti}/renew`); $('life-error').textContent = r.note; $('life-error').hidden = false; await refresh(); };
    $('btn-note').onclick = async () => { const b = $('btn-note'); b.disabled = true; b.textContent = 'Drafting…'; try { const r = await api('POST', `/api/applications/${a.id}/file-note`); $('rg-filenote').value = r.note; $('note-mode').textContent = `drafted by ${r.mode}`; } finally { b.disabled = false; b.textContent = 'Draft file note'; } };
  }

  // ───────────── Relying party ─────────────
  async function relying() {
    const state = await api('GET', '/api/state');
    const p = state.passports[0];
    const rules = (await api('GET', '/api/rulepack')).runtime_rules;
    const rl = $('rules'); rules.forEach(r => rl.append(el('li', null, `<code>${esc(r.id)}</code> ${esc(r.title)} → <code>${esc(r.on_fail)}</code> <span class="small">— ${esc(r.data)}</span>`)));
    const lines = $('term-lines');
    const beats = $('beats');
    if (!p) { $('rp-passport').innerHTML = '<div><dt>Passport</dt><dd>none issued yet — approve an application in <a href="' + ROOT + '/regulator">Review &amp; issue</a></dd></div>'; }
    else {
      const full = await api('GET', `/api/passports/${p.jti}`); const m = full.minimal;
      $('rp-passport').innerHTML = [['Passport', `<span class="mono">${esc(m.passport_id)}</span>`], ['Issuer', esc(m.issuer)], ['Agent', `<span class="mono">${esc(m.agent_id)}</span>`], ['Scope', `${esc(m.scope.task)} · ${esc(m.scope.tax_year)} · ${esc(m.scope.action_type.replace('_', ' '))} · hold above ${gbp(m.scope.escalation_threshold.amount)}`], ['Valid', `${d(m.issued_at)} → ${d(m.valid_until)}`], ['Status (live)', `<span id="rp-status">${tag(m.status)}</span> <button class="link small" id="rp-recheck" type="button">re-check</button>`], ['Agent key', `<span class="mono small">kid ${esc(m.agent_key_kid)}</span>`], ['Authority signature', `<span class="mono small">EdDSA · kid ${esc(m.signature_kid)}</span>`]].map(([k, val]) => `<div><dt>${k}</dt><dd>${val}</dd></div>`).join('');
      $('rp-recheck').onclick = async () => { const s = await api('GET', `/api/status/${p.jti}`); $('rp-status').innerHTML = tag(s.status); };
    }
    state.beats.forEach(b => {
      const btn = el('button', 'beat'); btn.type = 'button'; btn.disabled = !p;
      btn.innerHTML = `<span class="beat__label">${esc(b.label)}</span><span class="beat__expect">${esc(b.expect)}</span>`;
      btn.onclick = async () => {
        btn.disabled = true;
        try {
          const r = await api('POST', '/api/agent/act', { jti: p.jti, action: b.action, utr: b.utr, tax_year: b.tax_year, tax_due: b.tax_due, signer: b.signer });
          if (lines.querySelector('.terminal__hint')) lines.innerHTML = '';
          lines.append(termLine(b, r)); lines.scrollTop = lines.scrollHeight;
          const s = await api('GET', `/api/status/${p.jti}`); const rs = $('rp-status'); if (rs) rs.innerHTML = tag(s.status);
        } finally { btn.disabled = false; }
      };
      beats.append(el('li').appendChild(btn).parentElement);
    });
    function termLine(b, r) {
      const trace = r.trace.map(s => `<b>${esc(s.rule)}</b> ${s.ok ? '✓' : '✗'} ${esc(s.note)}`).join(' · ');
      return el('li', null, `<span class="t-time">${t(new Date().toISOString())}</span><span class="t-body">
        <span class="t-head"><span class="t-action">${esc(b.action)} · UTR ${esc(b.utr)} · ${esc(b.tax_year)}${b.tax_due ? ' · ' + gbp(b.tax_due) : ''}${b.signer === 'rogue' ? ' · signed with rogue key' : ''}</span><span class="t-verdict t-verdict--${r.decision}">${r.decision}</span><span class="t-rule">rule ${esc(r.rule)} · ${esc(r.code)}</span></span>
        <span class="t-reason">${esc(r.reason)}</span>
        <span class="t-trace">${trace}</span>
        <span class="t-meta">audit #${r.audit_id} <b>${esc(r.audit_hash.slice(0, 12))}</b> ← <b>${esc(r.prev_hash.slice(0, 12))}</b> · rule pack <b>${esc(r.rule_pack)}</b> · receipt signed by authority</span>
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
      const e = { ...r.entry }; delete e.ts; delete e.presented_token; if (e.request) delete e.request.agent_sig; delete e.trace;
      const tr = el('tr', null, `<td>${r.id}</td><td class="mono small">${t(r.ts)}</td><td>${esc(r.kind)}</td><td class="mono small">${esc(r.subject || '')}</td><td class="small">${esc(e.event || '')}${r.kind === 'verify' ? ` → <strong>${esc(e.decision)}</strong> ${esc(e.rule)} ${esc(e.code)}` : ''}${e.reason ? ` — ${esc(e.reason)}` : ''}${e.note ? ` — “${esc(e.note)}”` : ''}</td><td class="hash">${esc(r.hash.slice(0, 12))}<br>← ${esc(r.prev_hash.slice(0, 12))}</td><td class="small" id="au-r-${r.id}">${r.receipt ? '<span class="tag tag--green">receipt</span> ' : ''}${r.kind === 'verify' ? `<button class="link" data-replay="${r.id}" type="button">replay</button>` : ''}</td>`);
      tb.append(tr);
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
    if (rb) rb.onclick = async () => { if (confirm('Reset the whole demo? All applications, passports and audit entries are deleted.')) { await api('POST', '/api/reset'); location.href = ROOT + '/operator'; } };
  });

  return { operator, regulator, relying, audit };
})();
