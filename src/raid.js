  // ================================================================ raid calculator, stat weights and item compare
  // Spliced into the page script by src/build.py, so it shares the page's scope. Controls are rendered from
  // MageModel.OPTIONS, results come from rank(), weights from statWeights() and the comparer from compareItems()
  // (CONTRACTS section 3). Settings are saved under <prefix>calc1; the race lives in state.race, not here.
  // Speed: a slider drag ('input') re-ranks the bars, the verdict, the comparer and the race card only. Stat weights
  // (all specs, about 200 to 500 ms) and the race table wait for 'change', when the drag ends.
  // Reads from the page: C, state, store, obj, $, el, icon, rich, clamp, announce, renderRaceCard, renderRaceTable.
  // Provides: modelOpts, raidGain, buildRaidControls, wireRaid, syncRaceOptions, renderRaid.
  // Optional OPTIONS fields the page understands beyond the contract: race ('human' or a list: show only for those
  // races), group (legend for a run of toggles), scale (display multiplier; crit and gearHit default to 100, as percent).
  const M = window.MageModel;
  const OPTS = M.OPTIONS.filter(o => o.id !== 'race');
  const SPEC = Object.fromEntries(M.SPECS.map(s => [s.id, s]));
  const NO_SPECS = 'No raid builds yet: the raid model is not wired.';
  const scaleOf = o => o.scale || ((o.id === 'crit' || o.id === 'gearHit') && o.max <= 1 ? 100 : 1);
  const tidy = x => Number(x.toPrecision(12));
  function snap(o, v) {
    const c = clamp(v, o.min, o.max, M.DEFAULTS[o.id]);
    return o.step ? tidy(Math.min(o.max, o.min + Math.round((c - o.min) / o.step) * o.step)) : c;
  }
  function validOpt(o, v) {
    const d = M.DEFAULTS[o.id];
    if (o.type === 'toggle') return typeof v === 'boolean' ? v : d;
    if (o.type === 'seg') return (o.choices || []).some(c => c[0] === v) ? v : d;
    if (o.type === 'range') return typeof v === 'number' && Number.isFinite(v) ? snap(o, v) : d;
    return d;
  }
  const calcSaved = obj(store.get('calc1', {}));
  const calc = Object.fromEntries(OPTS.map(o => [o.id, validOpt(o, calcSaved[o.id])]));
  const saveCalc = () => store.set('calc1', calc);
  const modelOpts = race => Object.assign({}, M.DEFAULTS, calc, { race });
  const appliesTo = o => !o.race || [].concat(o.race).includes(state.race);
  const shown = o => tidy(calc[o.id] * scaleOf(o));
  const afterCalc = light => { renderRaid(light); renderRaceCard(); if (!light) renderRaceTable(); };
  const settled = () => { saveCalc(); announce($('raidVerdict').textContent); };

  // ---------------------------------------------------------------- controls
  function untestedChip(node, o) { if (o.untested) node.append(' ', el('span', 'chip c-test mini', 'untested')); return node; }
  function rangeCtrl(o) {
    const s = scaleOf(o), row = el('div', 'ctrl'); row.id = 'row-' + o.id;
    const r = el('input'), n = el('input');
    r.type = 'range'; r.id = 'opt-' + o.id;
    n.type = 'number'; n.id = 'opt-' + o.id + 'N'; n.inputMode = 'decimal'; n.setAttribute('aria-label', o.label + ', typed');
    [r, n].forEach(i => { i.min = tidy(o.min * s); i.max = tidy(o.max * s); i.step = o.step ? tidy(o.step * s) : 'any'; });
    const setV = (v, light) => {
      const num = Number(v);
      if (v === '' || !Number.isFinite(num)) return;
      calc[o.id] = snap(o, num / s); afterCalc(light);
    };
    r.addEventListener('input', e => setV(e.target.value, true));
    r.addEventListener('change', () => { afterCalc(false); settled(); });
    n.addEventListener('change', e => { setV(e.target.value, false); e.target.value = shown(o); settled(); });
    const lab = el('label', '', o.label); lab.htmlFor = r.id;
    row.append(untestedChip(lab, o), r, n);
    if (o.hint) row.appendChild(rich(el('span', 'hint'), o.hint));
    return row;
  }
  function toggleCtrl(o) {
    const row = el('div', 'toggle'); row.id = 'row-' + o.id;
    const lab = el('label', 'check'), cb = el('input');
    cb.type = 'checkbox'; cb.id = 'opt-' + o.id;
    cb.addEventListener('change', e => { calc[o.id] = e.target.checked; afterCalc(); settled(); });
    lab.append(cb, ' ' + o.label);
    row.appendChild(untestedChip(lab, o));
    if (o.hint) row.appendChild(rich(el('span', 'hint'), o.hint));
    return row;
  }
  function segCtrl(o) {
    const fs = el('fieldset'); fs.id = 'row-' + o.id;
    const seg = el('div', 'seg compact'); seg.id = 'opt-' + o.id; seg.setAttribute('role', 'group'); seg.setAttribute('aria-label', o.label);
    o.choices.forEach(([v, label], i) => {
      const b = el('button', '', label); b.type = 'button'; b.dataset.i = i;
      b.addEventListener('click', () => { calc[o.id] = v; afterCalc(); settled(); });
      seg.appendChild(b);
    });
    fs.append(untestedChip(el('legend', '', o.label), o), seg);
    if (o.hint) fs.appendChild(rich(el('span', 'hint'), o.hint));
    return fs;
  }
  function buildRaidControls() {
    const box = $('raidControls'); box.textContent = '';
    const raceFs = el('fieldset'), rs = el('div', 'seg compact race-seg');
    rs.dataset.compact = '1'; raceFs.append(el('legend', '', 'Race'), rs); box.appendChild(raceFs);
    let group = null;
    OPTS.forEach(o => {
      if (o.type === 'toggle' && !o.race) {
        const g = o.group || 'Options';
        if (!group || group.dataset.g !== g) { group = el('fieldset', 'fightset'); group.dataset.g = g; group.appendChild(el('legend', '', g)); box.appendChild(group); }
        group.appendChild(toggleCtrl(o));
        return;
      }
      group = null;
      if (o.type === 'toggle') box.appendChild(toggleCtrl(o));
      else if (o.type === 'range') box.appendChild(rangeCtrl(o));
      else if (o.type === 'seg') box.appendChild(segCtrl(o));
      else console.error('Unknown option type for ' + o.id + ': ' + o.type);
    });
    const lg = $('raidLegend'); lg.textContent = '';
    C.trees.forEach((n, t) => { const s = el('span'); s.append(el('span', 'sw t' + t), n); lg.appendChild(s); });
    lg.append(el('span', '', 'Shades: damage by source'), el('span', '', 'Gap is versus the leader'));
  }
  function syncRaceOptions() { OPTS.forEach(o => { const row = $('row-' + o.id); if (row) row.hidden = !appliesTo(o); }); }
  function syncControls() {
    OPTS.forEach(o => {
      const c = $('opt-' + o.id);
      if (!c) return;
      if (o.type === 'range') {
        const n = $('opt-' + o.id + 'N'), v = shown(o);
        if (document.activeElement !== c) c.value = v;
        if (document.activeElement !== n) n.value = v;
        c.setAttribute('aria-valuetext', o.label + ': ' + v);
      } else if (o.type === 'toggle') c.checked = calc[o.id] === true;
      else if (o.type === 'seg') c.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(o.choices[Number(b.dataset.i)][0] === calc[o.id])));
    });
  }

  // ---------------------------------------------------------------- results
  const treeOf = id => (SPEC[id] && Number.isInteger(SPEC[id].tree) ? SPEC[id].tree : 0);
  const partList = r => Object.entries(obj(r.parts)).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
  function partsSummary(r) {
    const parts = partList(r), sum = parts.reduce((a, [, v]) => a + v, 0);
    if (!sum) return '';
    const share = v => Math.round(v / sum * 100) + '%';
    const rest = parts.slice(3).reduce((a, [, v]) => a + v, 0);
    return parts.slice(0, 3).map(([k, v]) => k + ' ' + share(v)).concat(rest ? ['other ' + share(rest)] : []).join(' · ');
  }
  function barParts(r, max) {
    const parts = partList(r), sum = parts.reduce((a, [, v]) => a + v, 0);
    if (!sum) { const d = el('div', 'bar-part'); d.style.width = (r.total / max * 100) + '%'; return [d]; }
    return parts.map(([k, v], i) => {
      const d = el('div', 'bar-part p' + Math.min(i, 3));
      d.style.width = (v / sum * r.total / max * 100) + '%';   // parts drawn to the total, in case they do not add up exactly
      d.title = k + ': ' + Math.round(v) + ' dps';
      return d;
    });
  }
  // the race card and table: the top build with no racials, ranked once per settings change, then one specTotal()
  // per race (specTotal equals rank()'s total for a spec)
  let gainKey = '', gainTop = null;
  function raidGain(race) {
    const key = JSON.stringify(calc);
    if (key !== gainKey) { gainTop = M.rank(modelOpts('none')).find(x => x.viable !== false) || null; gainKey = key; }
    if (!gainTop || !gainTop.total) return 0;
    const mine = M.specTotal(modelOpts(race), gainTop.id);
    return Number.isFinite(mine) ? (mine / gainTop.total - 1) * 100 : 0;
  }
  let lastOrder = [];
  function renderRaid(light) {
    const res = M.rank(modelOpts(state.race)), live = res.filter(r => r.viable !== false);
    const max = (live[0] && live[0].total) || 1;
    const bars = $('bars'); bars.textContent = '';
    const moved = lastOrder.length && res.some((r, i) => lastOrder[i] !== r.id);
    res.forEach((r, i) => {
      const dead = r.viable === false, t = treeOf(r.id);
      const row = el('div', 'bar-row t' + t + (i === 0 && !dead ? ' win' : '') + (dead ? ' dead' : '') + (moved && lastOrder[i] !== r.id ? ' moved' : ''));
      const name = el('div', 'bar-name'), st = el('strong');
      st.append(icon(C.treeIcons[t], 's', ''), r.name);
      name.append(st, rich(el('span', 'cap'), dead ? 'Not viable: ' + (r.reason || 'not at these settings') : (SPEC[r.id] && SPEC[r.id].note) || ''));
      if (!dead) name.appendChild(el('span', 'cap parts', partsSummary(r)));
      const track = el('div', 'bar-track'); track.setAttribute('aria-hidden', 'true');
      if (!dead) barParts(r, max).forEach(d => track.appendChild(d));
      const gap = dead ? 'out' : i === 0 ? 'best' : '−' + ((1 - r.total / max) * 100).toFixed(1) + '%';
      row.append(name, track, el('div', 'bar-val', dead ? 'n/a' : Math.round(r.total) + ' dps'), el('div', 'bar-gap', gap));
      bars.appendChild(row);
    });
    if (moved) setTimeout(() => document.querySelectorAll('.bar-row.moved').forEach(x => x.classList.remove('moved')), 700);
    lastOrder = res.map(r => r.id);
    renderVerdict(live);
    syncControls(); renderCompare(res);
    if (!light) renderWeights(res);
  }
  function renderVerdict(live) {
    const a = live[0], b = live[1];
    const lead = a && b ? (a.total / b.total - 1) * 100 : null;
    $('tieNote').hidden = lead === null || lead >= 1;
    $('raidVerdict').textContent = !M.SPECS.length ? NO_SPECS : !a ? 'No build is viable at these settings.'
      : !b ? a.name + ' is the only viable build at these settings.'
      : a.name + ' leads ' + b.name + ' by ' + lead.toFixed(1) + '%.';
    $('stripName').textContent = a ? '#1 ' + a.name : '';
    $('stripVal').textContent = a ? Math.round(a.total) + ' dps' : '';
    $('stripGap').textContent = lead === null ? '' : '+' + lead.toFixed(1) + '% over #2';
  }

  // ---------------------------------------------------------------- stat weights and item compare
  const W_COLS = [['sp', '+1 spell power', null], ['crit', '+1% crit', 'critInSp'], ['hit', '+1% hit', 'hitInSp'],
    ['int', '+1 Intellect', 'intInSp'], ['spirit', '+1 Spirit', 'spiritInSp'], ['mp5', '+1 mp5', 'mp5InSp']];
  const fmt = v => (Math.abs(v) >= 10 ? v.toFixed(1) : Math.abs(v) >= 1 ? v.toFixed(2) : v.toFixed(3));
  function renderWeights(res) {
    const o = modelOpts(state.race), tb = $('weights');
    tb.textContent = '';
    const out = new Set(res.filter(r => r.viable === false).map(r => r.id));
    M.SPECS.filter(s => !out.has(s.id)).forEach(s => {
      const w = M.statWeights(o, s.id), tr = el('tr'), th = el('th');
      th.scope = 'row'; th.style.whiteSpace = 'nowrap'; th.append(icon(C.treeIcons[treeOf(s.id)], 's', ''), ' ' + s.name); tr.appendChild(th);
      W_COLS.forEach(([k, lab, inSp]) => {
        const td = el('td', 'r'), v = w[k]; td.dataset.label = lab;
        if (k === 'hit' && !(v > 0)) td.appendChild(el('span', 'na', 'capped'));
        else if (!Number.isFinite(v)) td.appendChild(el('span', 'na', 'n/a'));
        else {
          td.appendChild(el('span', '', fmt(v) + ' dps'));
          if (inSp && Number.isFinite(w[inSp])) td.appendChild(el('span', 'insp', fmt(w[inSp]) + ' SP'));
        }
        tr.appendChild(td);
      });
      tb.appendChild(tr);
    });
  }
  // item fields: [input id suffix, compareItems key, divisor]; crit and hit are typed in percent, passed as fractions
  const ITEM = [['Sp', 'sp', 1], ['Crit', 'crit', 100], ['Hit', 'hit', 100], ['Int', 'int', 1], ['Spirit', 'spirit', 1], ['Mp5', 'mp5', 1]];
  const itemFrom = side => Object.fromEntries(ITEM.map(([id, k, div]) => { const e = $(side + id); return [k, clamp(e.value, Number(e.min), Number(e.max), 0) / div]; }));
  function renderCompare(res) {
    const sel = $('cmpSpec'), out = $('cmpOut');
    if (!M.SPECS.length) { out.textContent = NO_SPECS; return; }
    if (!sel.options.length) {
      M.SPECS.forEach(s => { const op = el('option', '', s.name); op.value = s.id; sel.appendChild(op); });
      sel.value = (res[0] || M.SPECS[0]).id;
    }
    const name = sel.options[sel.selectedIndex].textContent;
    out.textContent = '';
    if (res.some(x => x.id === sel.value && x.viable === false)) { out.textContent = name + ' is not viable at these settings.'; return; }
    const r = M.compareItems(modelOpts(state.race), sel.value, itemFrom('a'), itemFrom('b'));
    if (Math.abs(r.diff) < 0.05) { out.textContent = 'The alternative makes no difference for ' + name + '.'; return; }
    const bold = el('b', '', Math.abs(r.diff).toFixed(1) + ' dps (' + (r.pct >= 0 ? '+' : '') + r.pct.toFixed(1) + '%)');
    out.append('The alternative ' + (r.diff > 0 ? 'gains ' : 'loses '), bold, ' for ' + name + ', from ' + Math.round(r.base) + ' to ' + Math.round(r.swapped) + '.');
  }
  function wireRaid() {
    const again = () => renderCompare(M.rank(modelOpts(state.race)));
    ITEM.forEach(([id]) => ['a', 'b'].forEach(side => $(side + id).addEventListener('input', again)));
    $('cmpSpec').addEventListener('change', () => { again(); announce($('cmpOut').textContent); });
  }
