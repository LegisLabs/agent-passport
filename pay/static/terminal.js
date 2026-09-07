/* Action Terminal · the scenario. One invoice, two worlds. Presentation: every step is a reveal; the "after" world
   uses the live verifier when a passport exists on this deployment and falls back to the seeded result otherwise. */
'use strict';
const AT = (() => {
  const $ = (id) => document.getElementById(id);
  const RM = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let speed = 1, token = 0, tab = 'before', live = null;
  const wait = (ms) => new Promise(r => setTimeout(r, RM ? 0 : ms / speed));
  const on = (el, cls = 'is-on') => { if (el) el.classList.add(cls); };
  const off = (el, cls = 'is-on') => { if (el) el.classList.remove(cls); };
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  const STEPS = {
    before: ['An invoice arrives', 'The agent reads it', 'It fills in the bank form', 'The money is gone'],
    after: ['The same invoice arrives', 'The agent reads it, having declared its intent', 'The bank calls the passport', 'Nine checks, one refusal'],
  };
  const SEED = {
    trace: [['R.1', true, 'authority signature verifies'], ['R.2', true, 'registry status active'], ['R.3', true, 'customer signature verifies; agent identity bound to this assurance'], ['R.4', true, 'instruction signature matches the agent key'], ['R.5', true, 'customer signature verifies'], ['R.6', false, 'payee account 60-11-22 99887766 is not on the customer-signed allowlist']],
    decision: 'DENY', rule: 'R.6', code: 'PAYEE_NOT_ON_MANDATE', reason: 'payee account 60-11-22 99887766 (Fenwick Timber Ltd) is not on the customer-signed mandate',
    audit_id: 17, audit_hash: '9c1e4b7d2a60', violation: { id: 3, status: 'OPEN' }, instruction_hash: 'a3f09c1d77b2', passport_id: 'AP-2026-0107', kid: 'pQxn4k4ZtG4q1phx',
  };

  function setSteps(active) {
    const ol = $('sc-steps'); ol.innerHTML = '';
    STEPS[tab].forEach((s, i) => { const li = document.createElement('li'); li.textContent = s; if (i < active) li.className = 'done'; if (i === active) li.className = 'now'; ol.append(li); });
  }
  function resetTab(t) {
    const root = $('sc-' + t);
    root.querySelectorAll('.is-on, .is-scan, .is-fill, .is-type, .is-go').forEach(x => x.classList.remove('is-on', 'is-scan', 'is-fill', 'is-type', 'is-go'));
    root.querySelectorAll('input').forEach(i => { i.value = ''; });
    root.querySelectorAll('.chk li').forEach(li => { li.dataset.state = ''; li.querySelector('em').textContent = ''; });
    const pay = $('bf-pay'); if (pay) { pay.disabled = true; pay.textContent = 'Confirm payment'; }
    setSteps(-1);
  }
  async function type(input, text, my) {
    input.classList.add('is-type');
    for (let i = 1; i <= text.length; i++) { if (my !== token) return; input.value = text.slice(0, i); await wait(28); }
    input.classList.remove('is-type');
  }

  // ── act 1 and 2 are shared: the invoice arrives, a person's cues, the scan, the extraction ──
  async function actInvoice(t, my) {
    setSteps(0);
    on($(t + '-inv')); await wait(900); if (my !== token) return;
    for (const f of ['domain', 'details', 'urgency']) { on($(t + '-inv').querySelector(`[data-flag="${f}"]`)); on($(t + '-human').querySelector(`[data-cue="${f}"]`)); await wait(650); if (my !== token) return; }
    on($(t + '-human')); await wait(700);
  }
  async function actRead(t, my) {
    setSteps(1);
    if (t === 'after') { on($('after-intent')); await wait(1100); if (my !== token) return; }
    $(t + '-agent-state').textContent = 'reading'; on($(t + '-agent'));
    $(t + '-scan').classList.add('is-scan'); await wait(1600); if (my !== token) return;
    on($(t + '-hidden')); on($(t + '-inv').querySelector('[data-flag="hidden"]')); on($(t + '-human').querySelector('[data-cue="hidden"]')); await wait(900); if (my !== token) return;
    for (const k of ['supplier', 'invoice', 'amount', 'sort', 'account', 'changed']) { on($(t + '-facts').querySelector(`[data-k="${k}"]`)); await wait(260); if (my !== token) return; }
    on($(t + '-agent-read')); $(t + '-agent-state').textContent = 'done'; await wait(900);
  }

  // ── before: the form, the payment, the loss ──
  async function playBefore(my) {
    await actInvoice('before', my); if (my !== token) return;
    await actRead('before', my); if (my !== token) return;
    setSteps(2); on($('before-open')); on($('before-arrow')); await wait(700); if (my !== token) return;
    on($('before-win')); await wait(500); if (my !== token) return;
    await type($('bf-name'), 'Fenwick Timber Ltd', my); if (my !== token) return;
    await type($('bf-sort'), '60-11-22', my); if (my !== token) return;
    await type($('bf-acct'), '99887766', my); if (my !== token) return;
    await type($('bf-amt'), '£2,500.00', my); if (my !== token) return;
    await type($('bf-ref'), 'INV-9001', my); if (my !== token) return;
    await wait(400); on($('bf-cop')); await wait(900); if (my !== token) return;
    const pay = $('bf-pay'); pay.disabled = false; pay.classList.add('is-go'); await wait(900); if (my !== token) return;
    pay.textContent = 'Sending…'; pay.classList.remove('is-go'); await wait(800); if (my !== token) return;
    pay.textContent = 'Sent'; on($('bf-done')); setSteps(3); await wait(1000); if (my !== token) return;
    on($('bf-stamp')); await wait(1200); if (my !== token) return;
    on($('before-after')); setSteps(4);
  }

  // ── after: the passport, the checks, the refusal ──
  async function playAfter(my) {
    const r = live || SEED;
    $('after-hash').textContent = (r.instruction_hash || '').slice(0, 12); $('after-kid').textContent = r.kid; $('after-pid').textContent = r.passport_id; $('pp-id').textContent = r.passport_id;
    $('after-audit').textContent = `#${r.audit_id} ${(r.audit_hash || '').slice(0, 12)}`; $('after-vio').textContent = r.violation ? `#${r.violation.id} ${r.violation.status}` : 'recorded';
    $('after-src').textContent = live ? 'live result from the verifier' : 'seeded result';
    await actInvoice('after', my); if (my !== token) return;
    await actRead('after', my); if (my !== token) return;
    setSteps(2); on($('after-sign')); on($('after-arrow')); await wait(900); if (my !== token) return;
    on($('after-win')); await wait(500); if (my !== token) return;
    for (const k of ['recv', 'status', 'verify']) { on($('after-req').querySelector(`[data-r="${k}"]`)); await wait(700); if (my !== token) return; }
    on($('after-pp')); await wait(1800); if (my !== token) return;
    setSteps(3); on($('after-chk'));
    const byRule = Object.fromEntries(r.trace.map(t => [t[0], t]));
    let stopped = false;
    for (const li of $('after-chk').children) {
      const tr = byRule[li.dataset.c];
      if (stopped || !tr) { li.dataset.state = 'skip'; li.querySelector('em').textContent = 'not evaluated · denied by default'; await wait(120); continue; }
      li.dataset.state = 'checking'; await wait(380); if (my !== token) return;
      li.dataset.state = tr[1] ? 'pass' : (r.decision === 'ESCALATE' ? 'hold' : 'fail'); li.querySelector('em').textContent = tr[2];
      if (!tr[1]) stopped = true;
      await wait(200);
    }
    await wait(500); if (my !== token) return;
    $('after-word').textContent = r.decision; $('after-cite').textContent = r.decision === 'ALLOW' ? `all nine checks passed · ${r.code}` : `${r.rule} · ${r.code}`; $('after-reason').textContent = r.reason;
    $('after-verdict').dataset.decision = r.decision; on($('after-verdict')); await wait(900); if (my !== token) return;
    for (const x of ['intent', 'violation', 'audit', 'money']) { on($('after-conseq').querySelector(`[data-x="${x}"]`)); await wait(650); if (my !== token) return; }
    on($('after-stamp')); await wait(1000); if (my !== token) return;
    on($('after-after')); setSteps(4);
  }

  async function play() {
    token++; const my = token; resetTab(tab); $('sc-play').textContent = 'Replay';
    if (tab === 'before') await playBefore(my); else await playAfter(my);
  }
  function skip() {
    token++; const saved = speed; speed = 1000; const my = token;
    (tab === 'before' ? playBefore(my) : playAfter(my)).finally(() => { speed = saved; });
  }
  function show(t) {
    tab = t; token++;
    for (const x of ['before', 'after']) { $('sc-' + x).hidden = x !== t; $('tab-' + x).setAttribute('aria-selected', String(x === t)); resetTab(x); }
    $('sc-page').dataset.tab = t; $('sc-play').textContent = 'Play';
    play();
  }
  async function loadLive() {
    // the "after" world prefers the real verifier: the seeded demo passport reading the altered invoice
    try {
      const st = await (await fetch('/api/state')).json();
      const p = (st.passports || []).find(x => x.status === 'active' && x.mandate_signed) || null;
      if (!p) return;
      const r = await (await fetch('/api/agent/invoice', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ passport_id: p.passport_id, invoice_id: 'INV-9001-poisoned' }) })).json();
      const res = r.result;
      live = { trace: res.trace.map(t => [t.rule, t.ok, t.note]), decision: res.decision, rule: res.rule, code: res.code, reason: res.reason, audit_id: res.audit_id, audit_hash: res.audit_hash,
               violation: res.violation, instruction_hash: (res.signature || {}).instruction_hash || '', passport_id: p.passport_id, kid: (res.signature || {}).agent_kid || SEED.kid };
      const m = (await (await fetch(`/api/passports/${p.passport_id}`)).json()).minimal;
      if (m) { $('pp-model').textContent = `${m.model || m.agent} · ${m.provider}`; $('pp-agent').textContent = `${m.agent} · ${m.agent_id}`; $('pp-scope').textContent = `${m.scope.suppliers} payees · £${Number(m.scope.per_payment_limit.amount).toLocaleString('en-GB')} per payment · £${Number(m.scope.monthly_limit_per_account.amount).toLocaleString('en-GB')} per account in 30 days`; }
      $('sc-live-note').textContent = 'The "after" verdict is the live verifier on this deployment; the record it writes is in the Audit.';
    } catch (e) { live = null; }
  }
  function init() {
    $('tab-before').onclick = () => show('before'); $('tab-after').onclick = () => show('after');
    $('sc-play').onclick = play; $('sc-skip').onclick = skip; $('sc-speed').onchange = (e) => { speed = Number(e.target.value); };
    document.addEventListener('keydown', (e) => { if (e.key === 'ArrowRight') show('after'); if (e.key === 'ArrowLeft') show('before'); if (e.key === ' ' && e.target === document.body) { e.preventDefault(); play(); } });
    loadLive().finally(() => { setSteps(-1); play(); });
  }
  return { init, show, play, skip };
})();
