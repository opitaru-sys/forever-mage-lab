  // ================================================================ talent builder
  // Spliced into the page script by src/build.py, so it shares the page's scope. Talents, positions, ranks and
  // prerequisites come from CLASS (data/talents.json); the rules and the share link come from src/talentcore.js.
  // Reads from the page: C, core, state, store, obj, $, el, icon, ICONS, rich, announce, setLevel, TBY, hasPlan, planAt.
  // Provides to the page: renderBuilder, builderFollowLevel, decodeBuild, wireBuilder.
  const TAL = C.talents;
  const SCORED = new Set(window.LevelingModel.SCORED || []);
  const shortName = n => C.shortReplace.reduce((s, [a, b]) => s.split(a).join(b), n).split(' ').map(w => C.shortWords[w] || w).join(' ');
  const gearOk = g => C.builder.gears.some(([v]) => v === g);

  // presets: the page plan, CLASS.presets, then the raid model's specs (filled main tree first), then Clear.
  // Each preset follows the level until you edit the build.
  function presetList() {
    const list = [];
    if (hasPlan) list.push({ id: 'plan', label: 'Page plan', at: L => core.fromOrder(planAt(L), L) });
    C.presets.forEach(p => { const order = core.expand(p.order); list.push({ id: 'p:' + p.id, label: p.label, at: L => core.fromOrder(order, L) }); });
    (window.MageModel.SPECS || []).forEach(s => {
      try {
        const order = core.orderFor(s.talents, s.tree);
        list.push({ id: 's:' + s.id, label: s.name, at: L => core.fromOrder(order, L) });
      } catch (e) { console.error('Raid spec ' + s.id + ' is not a legal build: ' + e.message); }
    });
    list.push({ id: 'clear', label: 'Clear', at: () => core.empty() });
    return list;
  }
  const PRESETS = presetList();
  const presetById = id => PRESETS.find(p => p.id === id);

  const bsaved = obj(store.get('builder', {}));
  const savedRanks = core.clean(bsaved.ranks);
  const B = {
    ranks: core.buildOk(savedRanks, core.rules.maxLevel) ? savedRanks : core.empty(),
    gear: gearOk(bsaved.gear) ? bsaved.gear : C.builder.gears[0][0],
    preset: typeof bsaved.preset === 'string' && presetById(bsaved.preset) ? bsaved.preset : null,   // a loaded preset follows the level
    sel: TAL[0].k, tree: 0,
  };
  const saveB = () => store.set('builder', { ranks: core.compact(B.ranks), gear: B.gear, preset: B.preset });
  const canAdd = x => core.canAdd(B.ranks, x.k, state.level);
  const canRemove = x => core.canRemove(B.ranks, x.k);

  function builderFollowLevel() {
    const p = B.preset && presetById(B.preset);
    if (!p) return;
    B.ranks = p.at(state.level); saveB();
  }
  function applyPreset(id) {
    const p = presetById(id);
    if (!p) return;
    B.preset = id === 'clear' ? null : id;
    B.ranks = p.at(state.level);
    saveB(); renderBuilder(); announce('Preset loaded. ' + $('bSummary').textContent);
  }

  function talentCell(x) {
    const scored = SCORED.has(x.k), rk = B.ranks[x.k], addable = canAdd(x);
    const b = el('button', 'tal ' + (scored ? 's-yes' : 's-no'));
    b.type = 'button'; b.dataset.k = x.k;
    b.style.gridRow = String(x.r + 1); b.style.gridColumn = String(x.c + 1);
    if (rk >= x.m) b.classList.add('max'); else if (rk) b.classList.add('some');
    if (!rk && !addable) b.classList.add('locked'); else if (rk < x.m && addable) b.classList.add('avail');
    if (x.k === B.sel) b.classList.add('sel');
    const icw = el('span', 'icw'); icw.append(icon(C.talentIcons[x.k], '', ''), el('span', 'tr', rk + '/' + x.m));
    b.append(icw, el('span', 'tn', shortName(x.n)));
    b.setAttribute('aria-label', x.n + ', ' + rk + ' of ' + x.m + (scored ? '' : ', not in the score') + '. Press to add a point, Shift press to remove one.');
    b.addEventListener('click', e => { B.sel = x.k; step(x, e.shiftKey ? -1 : +1); });
    b.addEventListener('contextmenu', e => { e.preventDefault(); B.sel = x.k; step(x, -1); });
    b.addEventListener('focus', () => { if (B.sel !== x.k) { B.sel = x.k; renderInfo(); markSel(); } });
    return b;
  }
  function renderBuilder() {
    const L = state.level;
    $('bLevel').textContent = L;
    $('bPts').textContent = core.spent(B.ranks) + ' of ' + core.points(L) + ' points';
    C.trees.forEach((tn, t) => {
      const grid = $('bTree' + t); grid.textContent = '';
      $('bTreeHead' + t).textContent = tn + ' ' + core.treeSpent(B.ranks, t);
      TAL.filter(x => x.t === t).forEach(x => grid.appendChild(talentCell(x)));
    });
    document.querySelectorAll('#bTabs button').forEach(b => b.setAttribute('aria-pressed', String(Number(b.dataset.t) === B.tree)));
    document.querySelectorAll('.btree').forEach(n => n.classList.toggle('on', Number(n.dataset.t) === B.tree));
    document.querySelectorAll('#bPresets button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.id === B.preset)));
    $('bGear').value = String(B.gear);
    renderInfo(); renderScore();
  }
  function markSel() { document.querySelectorAll('.tal').forEach(b => b.classList.toggle('sel', b.dataset.k === B.sel)); }
  // A tap must not move the trees. The score panel above them can change height (a note appears, a line wraps), so
  // after a render scroll by however far the trees moved, instantly (the page otherwise scrolls smoothly for links).
  function holdStill(node, top0) {
    const d = node.getBoundingClientRect().top - top0;
    if (Math.abs(d) < 0.5) return;
    const html = document.documentElement, was = html.style.scrollBehavior;
    html.style.scrollBehavior = 'auto';
    window.scrollBy(0, d);
    html.style.scrollBehavior = was;
  }
  function step(x, dir) {
    if (dir > 0 && canAdd(x)) { B.ranks = Object.assign({}, B.ranks, { [x.k]: B.ranks[x.k] + 1 }); B.preset = null; }
    else if (dir < 0 && canRemove(x)) { B.ranks = Object.assign({}, B.ranks, { [x.k]: B.ranks[x.k] - 1 }); B.preset = null; }
    else {
      renderInfo(); markSel();
      announce(x.n + ': ' + (dir > 0 ? core.lockReason(B.ranks, x.k, state.level, C.trees) || 'cannot add.' : 'cannot remove, other talents depend on it.'));
      return;
    }
    const trees = document.querySelector('.btrees'), top0 = trees.getBoundingClientRect().top;
    saveB(); renderBuilder(); announce(x.n + ' ' + B.ranks[x.k] + ' of ' + x.m + '. ' + $('bSummary').textContent);
    holdStill(trees, top0);
    const again = document.querySelector('.tal[data-k="' + x.k + '"]'); if (again) again.focus({ preventScroll: true });
  }
  const rankText = (x, rk) => { const t = C.talentText[x.k]; return t && t[rk - 1] ? t[rk - 1] : 'No rank text for rank ' + rk + '.'; };
  function renderInfo() {
    const x = TBY[B.sel], rk = B.ranks[x.k], scored = SCORED.has(x.k);
    $('bInfoName').textContent = x.n;
    const ii = $('bInfoIco'), src = ICONS[C.talentIcons[x.k]];
    if (src) { ii.src = src; ii.hidden = false; } else ii.hidden = true;
    $('bInfoRank').textContent = 'Rank ' + rk + '/' + x.m + ' · ' + C.trees[x.t];
    $('bInfoNow').textContent = rk ? rankText(x, rk) : 'Not taken.';
    $('bInfoNext').textContent = rk < x.m ? 'Next rank: ' + rankText(x, rk + 1) : '';
    $('bInfoTag').textContent = scored ? 'Counts in the score' : 'Not in the score';
    $('bInfoTag').className = 'chip ' + (scored ? 'c-proof' : 'c-known');
    const why = core.lockReason(B.ranks, x.k, state.level, C.trees);
    $('bInfoLock').textContent = rk < x.m && why ? why : '';
    $('bMinus').disabled = !canRemove(x); $('bPlus').disabled = !canAdd(x);
    $('bInfo').scrollTop = 0;   // long text scrolls inside the fixed-height panel: each render starts at the talent's name
  }

  // the leveling score (CONTRACTS section 4): seconds per kill including rest and walking.
  // A throwing or partial model result is logged as a console error and shown as n/a, so the page keeps working.
  const hasScore = r => !!r && [r.spk, r.ttk, r.rest].every(Number.isFinite) && r.spk > 0;
  function evaluate(L, ranks, opts) {
    try { return window.LevelingModel.evaluate(L, core.compact(ranks), B.gear, opts); }
    catch (e) { console.error('LevelingModel.evaluate failed at level ' + L + ': ' + e.message); return null; }
  }
  function renderScore() {
    const L = state.level, notes = [], opts = { race: state.race, hpMults: C.builder.hpMults };
    const mine = evaluate(L, B.ranks, opts);
    const ok = hasScore(mine);
    $('bSpk').textContent = ok ? mine.spk.toFixed(1) + ' s' : 'n/a';
    $('bKph').textContent = ok ? Math.round(3600 / mine.spk) + ' kills an hour' : '';
    $('bSplit').textContent = ok ? mine.ttk.toFixed(1) + ' s fighting, ' + Math.round(mine.spk - mine.ttk - mine.rest) + ' s walking, ' + mine.rest.toFixed(1) + ' s resting' : '';
    const vs = $('bVs');
    vs.className = 'bvs';
    const plan = hasPlan && ok ? evaluate(L, core.fromOrder(planAt(L), L), opts) : null;
    if (hasScore(plan)) {
      const diff = (plan.spk / mine.spk - 1) * 100, same = Math.abs(diff) < 0.5;
      vs.textContent = same ? 'About the same as the page plan at level ' + L + '.'
        : (diff > 0 ? diff.toFixed(1) + '% faster' : (-diff).toFixed(1) + '% slower') + ' than the page plan at level ' + L + ' (' + plan.spk.toFixed(1) + ' s per kill).';
      if (!same) vs.classList.add(diff > 0 ? 'up' : 'down');
    } else if (hasPlan) vs.textContent = 'No comparison with the page plan at level ' + L + ': the model returned no score.';
    else vs.textContent = 'No page plan to compare with.';
    let rot = 'n/a';
    if (ok && mine.policy !== undefined && mine.policy !== null) {
      try { rot = String(window.LevelingModel.policyLabel(mine.policy)); }
      catch (e) { console.error('LevelingModel.policyLabel failed: ' + e.message); }
    }
    $('bRot').textContent = rot;
    const unscored = TAL.filter(x => B.ranks[x.k] && !SCORED.has(x.k)).map(x => x.n);
    if (unscored.length) notes.push('Not in the score: ' + unscored.join(', ') + '.');
    const used = core.spent(B.ranks);
    if (used > core.points(L)) notes.push('This build spends ' + used + ' points, more than level ' + L + ' has.');
    const nl = $('bNotes'); nl.textContent = '';
    notes.forEach(n => nl.appendChild(el('li', '', n)));
    $('bSummary').textContent = $('bSpk').textContent + ' per kill. ' + vs.textContent;
    // the link level is the current level, raised to the lowest level that holds the build and kept inside the
    // decoder's accepted range, so a copied link always decodes (below level 10 it carries level 10)
    const R = core.rules, linkL = Math.min(R.maxLevel, Math.max(R.firstLevel, L, used + R.firstLevel - 1));
    $('bLink').value = location.href.split('#')[0] + '#' + core.encode(linkL, B.ranks, B.gear);
  }

  // share links (CONTRACTS section 5): #b-<level>-<one digit per talent>-<gear>
  function decodeBuild(h) {
    const d = core.decode(h);
    if (!d) return false;
    B.ranks = d.ranks; B.gear = d.gear; B.preset = null;
    saveB(); setLevel(d.level, false);
    return true;
  }

  function wireBuilder() {
    const pr = $('bPresets');
    PRESETS.forEach(p => { const b = el('button', '', p.label); b.type = 'button'; b.dataset.id = p.id; b.addEventListener('click', () => applyPreset(p.id)); pr.appendChild(b); });
    const gs = $('bGear');
    C.builder.gears.forEach(([v, l]) => { const o = el('option', '', l); o.value = String(v); gs.appendChild(o); });
    gs.addEventListener('change', e => { const g = Number(e.target.value); if (gearOk(g)) B.gear = g; saveB(); renderBuilder(); announce($('bSummary').textContent); });
    const tabs = $('bTabs');
    C.trees.forEach((n, t) => {
      $('bTree' + t).setAttribute('aria-label', n + ' talents');
      const b = el('button', '', n); b.type = 'button'; b.dataset.t = t;
      b.addEventListener('click', () => { B.tree = t; renderBuilder(); });
      tabs.appendChild(b);
    });
    $('bMinus').addEventListener('click', () => step(TBY[B.sel], -1));
    $('bPlus').addEventListener('click', () => step(TBY[B.sel], +1));
    $('bLvlDown').addEventListener('click', () => setLevel(state.level - 1, true));
    $('bLvlUp').addEventListener('click', () => setLevel(state.level + 1, true));
    $('bCopy').addEventListener('click', () => {
      const v = $('bLink').value;
      const done = ok => { $('bCopy').textContent = ok ? 'Copied' : 'Select and copy'; setTimeout(() => { $('bCopy').textContent = 'Copy link'; }, 1600); };
      try { navigator.clipboard.writeText(v).then(() => done(true), () => { $('bLink').select(); done(false); }); }
      catch (e) { $('bLink').select(); done(false); }
    });
    // a fresh builder starts on the page plan and follows the level, as if its preset had been pressed
    if (!core.spent(B.ranks) && hasPlan) { B.preset = 'plan'; B.ranks = core.fromOrder(planAt(state.level), state.level); }
  }
