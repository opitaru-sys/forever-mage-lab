  // ================================================================ content: text slots, verdicts, glossary, spec cards, proof,
  // claims, tests, method and the stub banner. Spliced into the page script by src/build.py, so it shares the page's scope.
  // Reads from the page: C, core, store, obj, $, el, icon, ICONS, rich. Provides: renderContent.
  const T = C.text;
  const CLAIM_GROUPS = [['proof', 'c-proof', 'Checked by the model'], ['test', 'c-test', 'Needs an in-game test'],
    ['bust', 'c-bust', 'Busted'], ['known', 'c-known', 'Known and confirmed']];

  function fillText() {
    document.querySelectorAll('[data-text]').forEach(n => {
      const k = n.dataset.text;
      if (typeof T[k] !== 'string') console.error('CLASS.text has no string for the slot "' + k + '".');
      rich(n, typeof T[k] === 'string' ? T[k] : '');
    });
    const ci = $('classIco'); ci.alt = C.name + ' class icon';
    if (ICONS[C.icon]) ci.src = ICONS[C.icon]; else ci.hidden = true;
  }

  function renderStart() {
    const ul = $('verdictList'); ul.textContent = '';
    T.verdict.forEach(v => {
      const li = el('li'); li.id = v.id;
      const body = el('span'); body.appendChild(rich(el('span'), v.body));
      if (v.link) { const a = el('a', 'go', v.link[1]); a.href = v.link[0]; body.append(el('br'), a); }
      li.append(el('span', 'k', v.k), body);
      ul.appendChild(li);
    });
    const dl = $('gloss'); dl.textContent = '';
    T.glossary.forEach(([dt, dd]) => dl.append(rich(el('dt'), dt), rich(el('dd'), dd)));
  }

  // one tooltip-style card; the point split, talent lines and builder link come from the build itself
  function specCard(s) {
    const r = core.clean(s.build), card = el('div', 'tt');
    const nr = el('div', 'name-row'); nr.append(icon(s.icon, '', ''), rich(el('span', 'name'), s.name));
    card.append(nr, rich(el('span', 'sub'), s.sub || ''), el('span', 'split', C.trees.map((n, t) => n + ' ' + core.treeSpent(r, t)).join(' · ')));
    if (s.use) card.appendChild(rich(el('span', 'use'), s.use));
    const ul = el('ul');
    C.trees.forEach((n, t) => {
      const lines = {};
      C.talents.filter(x => x.t === t && r[x.k]).forEach(x => { (lines[x.r >> 1] = lines[x.r >> 1] || []).push(x.n + ' ' + r[x.k]); });
      Object.keys(lines).sort((a, b) => a - b).forEach(i => ul.appendChild(el('li', '', lines[i].join(', '))));
    });
    card.appendChild(ul);
    if (s.grey) card.appendChild(rich(el('span', 'grey'), s.grey));
    const maxL = core.rules.maxLevel;
    if (core.buildOk(r, maxL)) { const a = el('a', '', 'Open in the talent builder'); a.href = '#' + core.encode(maxL, r, core.rules.gears[core.rules.gears.length - 1]); card.appendChild(a); }
    else console.error('Spec card "' + s.name + '" is not a legal build.');
    return card;
  }
  function renderSpecCards() {
    const box = $('specCards'); box.textContent = '';
    C.specCards.forEach(s => box.appendChild(specCard(s)));
    if (!C.specCards.length) console.error('CLASS.specCards is empty.');
  }

  // a data table: head [...], rows [[row header, cell, ...], ...], align optional per column ('r' right aligned)
  function tableBlock(label, t) {
    const wrap = el('div', 'tbl scrollx'); wrap.setAttribute('role', 'region'); wrap.setAttribute('aria-label', label); wrap.tabIndex = 0;
    const align = i => (t.align ? t.align[i] || '' : i ? 'r' : '');
    const table = el('table'), hr = el('tr');
    t.head.forEach((h, i) => { const th = el('th', align(i), h); th.scope = 'col'; hr.appendChild(th); });
    const thead = el('thead'); thead.appendChild(hr);
    const tb = el('tbody');
    t.rows.forEach(row => {
      const tr = el('tr');
      row.forEach((c, i) => {
        if (!i) { const th = rich(el('th'), c); th.scope = 'row'; tr.appendChild(th); } else tr.appendChild(rich(el('td', align(i)), c));
      });
      tb.appendChild(tr);
    });
    table.append(thead, tb); wrap.appendChild(table);
    return wrap;
  }
  function renderProof() {
    const rule = C.proof.rule, rb = $('ruleBody');
    rb.textContent = '';
    rich($('rule'), rule ? rule.title : '');
    if (rule) {
      if (rule.intro) rb.appendChild(rich(el('p'), rule.intro));
      rb.append(el('p', 'note swipe', 'Swipe the table sideways for all columns.'), tableBlock(rule.title, rule));
      if (rule.so) rb.appendChild(rich(el('p'), rule.so));
    } else console.error('CLASS.proof.rule is missing.');

    const box = $('claimList'); box.textContent = '';
    CLAIM_GROUPS.forEach(([g, chip, label]) => {
      const list = C.claims.filter(c => c.group === g);
      if (!list.length) return;
      const p = el('p', 'group-h'); p.appendChild(el('span', 'chip ' + chip, label + ' · ' + list.length)); box.appendChild(p);
      list.forEach(c => {
        const d = el('details'); d.id = c.id;
        const body = el('div', 'dbody');
        [].concat(c.body).forEach(t => body.appendChild(rich(el('p'), t)));
        d.append(rich(el('summary'), c.title), body);
        box.appendChild(d);
      });
    });
    if (!C.claims.length) console.error('CLASS.claims is empty.');

    const tv = C.proof.talentValues, tvb = $('talentValues');
    tvb.textContent = '';
    if (tv) {
      if (tv.intro) tvb.appendChild(rich(el('p'), tv.intro));
      tvb.append(el('p', 'note swipe', 'Swipe the table sideways for all columns.'), tableBlock('Talent point values', tv));
      if (tv.note) tvb.appendChild(rich(el('p', 'note'), tv.note));
    } else console.error('CLASS.proof.talentValues is missing.');
  }

  function renderTests() {
    const ul = $('testList'); ul.textContent = '';
    const ticks = obj(store.get('tests', {}));
    C.tests.forEach(t => {
      const li = el('li'); li.id = t.id;
      const lab = el('label'), cb = el('input'); cb.type = 'checkbox'; cb.id = t.id + 'c'; cb.checked = ticks[cb.id] === true;
      const tx = el('span');
      tx.append(rich(el('span', 'when'), t.when), el('br'), rich(el('b'), t.title), document.createTextNode(' '), rich(el('span'), t.body));
      lab.append(cb, tx); li.appendChild(lab); li.classList.toggle('done', cb.checked);
      cb.addEventListener('change', () => {
        const cur = Object.assign({}, obj(store.get('tests', {})), { [cb.id]: cb.checked });
        store.set('tests', cur); li.classList.toggle('done', cb.checked);
      });
      ul.appendChild(li);
    });
    if (!C.tests.length) console.error('CLASS.tests is empty.');
  }

  const listInto = (id, items) => { const ul = $(id); ul.textContent = ''; items.forEach(t => ul.appendChild(rich(el('li'), t))); };
  function renderMethod() {
    const mt = $('methodText'); mt.textContent = '';
    T.method.forEach(p => mt.appendChild(rich(el('p'), p)));
    listInto('changeList', T.changelog);
    listInto('sourceList', T.sources);
    const rep = $('reportLine'); rep.textContent = '';
    const a = el('a', '', 'Report it on GitHub'); a.href = C.resultsUrl; a.target = '_blank'; a.rel = 'noopener';
    rep.append('Got a result? ', a, ', or reply in the thread where you found this page.');
    const code = $('codeLine'); code.textContent = '';
    const b = el('a', '', 'read or run them'); b.href = C.repoUrl; b.target = '_blank'; b.rel = 'noopener';
    code.append('The models are open source: ', b, '.');
  }

  function renderStubBar() {
    const stubs = [['raid', window.MageModel], ['leveling', window.LevelingModel]].filter(([, m]) => m && m.STUB).map(([n]) => n);
    $('stubBar').hidden = !stubs.length;
    $('stubText').textContent = stubs.length ? 'Models not wired yet: the ' + stubs.join(' and ') + ' model' + (stubs.length > 1 ? 's are stubs' : ' is a stub')
      + ' with fake numbers. Nothing on this page is a result.' : '';
  }

  function renderContent() {
    fillText(); renderStart(); renderSpecCards(); renderProof(); renderTests(); renderMethod(); renderStubBar();
  }
