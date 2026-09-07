/* Action Terminal · one invoice, two worlds. Every step is a reveal. The "after" world uses the live verifier when a
   passport exists on this deployment and falls back to the seeded result otherwise. */
'use strict';
const AT = (() => {
  const $ = (id) => document.getElementById(id);
  const RM = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let speed = 1, token = 0, tab = 'before', live = null, played = { before: false, after: false };
  const wait = (ms) => new Promise(r => setTimeout(r, RM ? 0 : ms / speed));
  const on = (el) => { if (el) el.classList.add('is-on'); };

  const SEED = {
    trace: [['R.1', true, ''], ['R.2', true, ''], ['R.3', true, ''], ['R.4', true, ''], ['R.5', true, ''], ['R.6', false, '60-11-22 99887766 is not on the customer-signed mandate']],
    decision: 'DENY', rule: 'R.6', reason: '60-11-22 99887766 is not on the mandate.', audit_id: 17, audit_hash: '9c1e4b7d2a60', passport_id: 'AP-2026-0107',
  };

  function reset(t) {
    const root = $('sc-' + t);
    root.querySelectorAll('.is-on, .is-scan, .is-type, .is-go').forEach(x => x.classList.remove('is-on', 'is-scan', 'is-type', 'is-go'));
    root.querySelectorAll('input').forEach(i => { i.value = ''; });
    root.querySelectorAll('.chk li').forEach(li => { li.dataset.state = ''; li.querySelector('em').textContent = ''; });
    const pay = $('bf-pay'); if (pay) { pay.disabled = true; pay.textContent = 'Confirm payment'; }
    const st = $(t + '-agent-state'); if (st) st.textContent = 'waiting';
    $('sc-page').dataset.state = 'idle';
  }
  async function type(input, text, my) {
    input.classList.add('is-type');
    for (let i = 1; i <= text.length; i++) { if (my !== token) return; input.value = text.slice(0, i); await wait(26); }
    input.classList.remove('is-type');
  }

  // shared opening: the invoice, its tells, the scan, what the agent read
  async function opening(t, my) {
    on($(t + '-inv')); await wait(700); if (my !== token) return;
    for (const f of ['domain', 'details']) { on($(t + '-inv').querySelector(`[data-flag="${f}"]`)); await wait(600); if (my !== token) return; }
    if (t === 'after') { on($('after-intent')); await wait(1100); if (my !== token) return; }
    $(t + '-agent-state').textContent = 'reading'; on($(t + '-agent'));
    $(t + '-scan').classList.add('is-scan'); await wait(1500); if (my !== token) return;
    on($(t + '-hidden')); on($(t + '-inv').querySelector('[data-flag="hidden"]')); await wait(900); if (my !== token) return;
    for (const k of ['supplier', 'amount', 'account']) { on($(t + '-facts').querySelector(`[data-k="${k}"]`)); await wait(320); if (my !== token) return; }
    on($(t + '-agent-read')); $(t + '-agent-state').textContent = 'done'; await wait(800);
  }

  async function before(my) {
    await opening('before', my); if (my !== token) return;
    on($('before-open')); await wait(600); if (my !== token) return;
    on($('before-win')); await wait(400); if (my !== token) return;
    for (const [id, v] of [['bf-name', 'Fenwick Timber Ltd'], ['bf-sort', '60-11-22'], ['bf-acct', '99887766'], ['bf-amt', '2,500.00'], ['bf-ref', 'INV-9001']]) { await type($(id), v, my); if (my !== token) return; }
    await wait(300); on($('bf-cop')); await wait(800); if (my !== token) return;
    const pay = $('bf-pay'); pay.disabled = false; pay.classList.add('is-go'); await wait(900); if (my !== token) return;
    pay.classList.remove('is-go'); pay.textContent = 'Sent'; on($('bf-done')); await wait(900); if (my !== token) return;
    on($('bf-stamp')); $('sc-page').dataset.state = 'lost'; await wait(1000); if (my !== token) return;
    on($('before-after'));
  }

  async function after(my) {
    const r = live || SEED;
    $('after-pid').textContent = r.passport_id; $('pp-id').textContent = r.passport_id;
    $('after-audit').textContent = `#${r.audit_id} ${(r.audit_hash || '').slice(0, 10)}`;
    $('after-src').textContent = live ? '· live verifier' : '· seeded';
    await opening('after', my); if (my !== token) return;
    on($('after-sign')); await wait(800); if (my !== token) return;
    on($('after-win')); on($('after-ask')); await wait(900); if (my !== token) return;
    on($('after-pp')); await wait(1600); if (my !== token) return;
    on($('after-chk'));
    const byRule = Object.fromEntries(r.trace.map(t => [t[0], t]));
    let stopped = false;
    for (const li of $('after-chk').children) {
      const tr = byRule[li.dataset.c];
      if (stopped || !tr) { li.dataset.state = 'skip'; await wait(90); continue; }
      li.dataset.state = 'checking'; await wait(330); if (my !== token) return;
      li.dataset.state = tr[1] ? 'pass' : (r.decision === 'ESCALATE' ? 'hold' : 'fail');
      if (!tr[1]) { li.querySelector('em').textContent = tr[2]; stopped = true; }
      await wait(150);
    }
    await wait(500); if (my !== token) return;
    $('after-word').textContent = r.decision === 'DENY' ? 'Denied' : r.decision === 'ESCALATE' ? 'Held for a person' : 'Allowed';
    $('after-reason').textContent = r.reason; $('after-verdict').dataset.decision = r.decision;
    on($('after-verdict')); $('sc-page').dataset.state = r.decision === 'ALLOW' ? 'lost' : 'saved'; await wait(900); if (my !== token) return;
    for (const x of ['intent', 'audit']) { on($('after-conseq').querySelector(`[data-x="${x}"]`)); await wait(700); if (my !== token) return; }
    on($('after-after'));
  }

  async function play() {
    token++; const my = token; reset(tab); played[tab] = true; label();
    $('sc-page').dataset.state = 'running';
    if (tab === 'before') await before(my); else await after(my);
  }
  function skip() { token++; const my = token; const s = speed; speed = 1000; reset(tab); played[tab] = true; label(); (tab === 'before' ? before(my) : after(my)).finally(() => { speed = s; }); }
  function label() { $('sc-play-label').textContent = played[tab] ? 'Run it again' : 'Run the agent'; }
  function show(t) {
    tab = t; token++;
    for (const x of ['before', 'after']) { $('sc-' + x).hidden = x !== t; $('tab-' + x).setAttribute('aria-selected', String(x === t)); }
    $('sc-page').dataset.tab = t; reset(t); label();
  }
  async function loadLive() {
    try {
      const st = await (await fetch('/api/state')).json();
      const p = (st.passports || []).find(x => x.status === 'active' && x.mandate_signed) || null;
      if (!p) return;
      const r = await (await fetch('/api/agent/invoice', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ passport_id: p.passport_id, invoice_id: 'INV-9001-poisoned' }) })).json();
      const res = r.result;
      live = { trace: res.trace.map(t => [t.rule, t.ok, t.note]), decision: res.decision, rule: res.rule, reason: `${res.rule}: ${res.reason}.`, audit_id: res.audit_id, audit_hash: res.audit_hash, passport_id: p.passport_id };
      const m = (await (await fetch(`/api/passports/${p.passport_id}`)).json()).minimal;
      if (m) {
        $('pp-model').textContent = `${m.model || m.agent}, approved once by the authority`;
        $('pp-scope').textContent = `£${Number(m.scope.per_payment_limit.amount).toLocaleString('en-GB')} a payment · £${Number(m.scope.monthly_limit_per_account.amount).toLocaleString('en-GB')} an account a month`;
      }
      $('sc-live-note').textContent = 'The refusal is the live verifier on this deployment; its record is in the Audit.';
    } catch (e) { live = null; }
  }
  function init() {
    $('tab-before').onclick = () => show('before'); $('tab-after').onclick = () => show('after');
    $('sc-play').onclick = play; $('sc-skip').onclick = skip;
    document.addEventListener('keydown', (e) => { if (e.key === 'ArrowRight') show('after'); if (e.key === 'ArrowLeft') show('before'); if (e.key === ' ' && e.target === document.body) { e.preventDefault(); play(); } });
    show('before'); loadLive();
  }
  return { init, show, play, skip };
})();
