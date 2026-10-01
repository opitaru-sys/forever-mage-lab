"""Headless browser check of the built page. Run from the repo root after the build:

    python src/build.py && python tests/page_check.py            (the models build.py found)
    python src/build.py --stubs && python tests/page_check.py    (the stub models)

Serves the repo on a local port and opens index.html in headless Chromium (Python Playwright). Google Fonts is
answered with an empty stylesheet so the check runs offline. It prints which models the page runs, then checks:
- no console errors and no uncaught page errors, on load and after every step
- every <img> has an embedded source and loads, and every icon the class data names is embedded
- setting race and level, applying a builder preset, adding and removing talent points, a #b- link (and bad ones),
  #race- and #lvl- links, element id links, raid toggles, segments and ranges, the item comparer and the dungeon filter
- hostile input: #race-constructor style hashes, and garbage or prototype-key values in every fml. storage key;
  after each, a reload must still initialize the page with no errors
- the copied builder link decodes at every level, including 1 to 9
- the class switch: the current class is a chip, each sibling link carries #go-<race>-<level> (no race when the
  sibling lacks it), and incoming #go- links set race and level, reject malformed input and never break a reload
- the stub banner shows when a stub model is loaded
- localStorage holds only fml. keys, and saved state survives a reload
- phone width has no sideways scroll, and the class colors apply in light and dark mode
Then it repeats with fixture content injected into CLASS, so the claim, test, spec card, proof table and planner
renderers run before the real content exists. Expected numbers come from the page's own talent rules and the
model's SPECS, so the shell check does not depend on what the models contain.
"""
import functools
import http.server
import json
import os
import sys
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
failures = []
passed = [0]


def check(name, fn):
    try:
        fn()
        passed[0] += 1
    except AssertionError as e:
        failures.append('%s: %s' % (name, e))
    except Exception as e:                      # a Playwright timeout or a JS error is a failed check too
        failures.append('%s: %s: %s' % (name, type(e).__name__, str(e).splitlines()[0] if str(e) else ''))


def assert_eq(a, b, what):
    assert a == b, '%s: got %r, expected %r' % (what, a, b)


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve():
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=ROOT))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


# fixture content: a legal 51-point order (checked in the page too), one of each claim group, two tests, proof tables
FIXTURE_JS = r"""
(() => {
  const order = [['ImprovedFrostbolt',5],['ElementalPrecision',5],['IceShards',5],['Frostbite',3],['PiercingIce',3],['IceLance',1],
    ['Shatter',3],['IceBlock',1],['ColdSnap',1],['FingersOfFrost',2],['WintersChill',5],['IceBarrier',1],['ArcaneFocus',5],
    ['ArcaneConcentration',5],['ArcaneImpact',3],['ArcaneGeometry',2],['Permafrost',1]];
  let held;
  Object.defineProperty(window, 'CLASS', { configurable: true, get() { return held; }, set(v) {
    v.planner.order = order;
    v.planner.phases = [{ from: 1, name: 'Fixture', rot: 'Fixture rotation', sub: 'fixture sub', steps: ['Frostbolt', 'Ice Lance', 'Wand'],
      extra: ['Mana', 'Fixture extra', 'fixture extra sub'] }];
    v.planner.gear = [{ from: 1, text: 'Fixture gear note.' }];
    v.presets = [{ id: 'fx', label: 'Fixture preset', order }];
    v.claims = [{ id: 'c-fx-proof', group: 'proof', title: 'Fixture proof claim', body: 'Body with a [link](#t1).' },
      { id: 'c-fx-test', group: 'test', title: 'Fixture test claim', body: ['Two', 'paragraphs'] }];
    v.tests = [{ id: 't1', when: 'Test 1 · Level 20 · beta', title: 'Fixture test one.', body: 'Do the thing.' },
      { id: 't2', when: 'Test 2 · Level 30 · beta', title: 'Fixture test two.', body: 'Do the other thing.' }];
    v.proof = { rule: { title: 'Fixture rule', intro: 'Intro.', head: ['Spell', 'Classic', 'Forever'], rows: [['Frostbolt', '515-555', '457-493']], so: '**So:** fixture.' },
      talentValues: { intro: 'TV intro.', head: ['Talent', 'Lvl 30'], rows: [['Shatter', '+1%']], note: 'TV note.' } };
    Object.keys(v.races).forEach(k => Object.assign(v.races[k], { level: 'Fixture leveling', levelPct: 1, pvp: ['Fixture PvP', 'detail'],
      verdict: 'Fixture verdict.', tip: 'Fixture tip.' }));
    held = v;
  } });
})();
"""

# the page's own rules, for expected values that do not depend on model content
CORE_JS = '() => TalentCore.make(CLASS.talents, CLASS.talentRules)'


def storage(page):
    return page.evaluate('() => Object.fromEntries(Object.keys(localStorage).map(k => [k, localStorage.getItem(k)]))')


def text(page, sel):
    return page.locator(sel).first.text_content()


def race_now(page):
    return page.evaluate('() => document.documentElement.dataset.race')


def set_hash(page, h):
    """Set location.hash and wait until the page's own hashchange handler has run (it was registered first)."""
    page.evaluate("""h => new Promise((res, rej) => {
        if (location.hash === h) return rej(new Error('the hash is already ' + h));
        const t = setTimeout(() => rej(new Error('no hashchange for ' + h)), 3000);
        window.addEventListener('hashchange', () => setTimeout(() => { clearTimeout(t); res(); }, 0), { once: true });
        location.hash = h;
    })""", h)


def points_text(page, L, build_js):
    """'<spent> of <points> points' for a build at level L, with spent capped at the level's points."""
    spent, pts = page.evaluate('([L, build]) => { const c = (%s)(); return [c.spent(c.clean(build)), c.points(L)]; }' % CORE_JS,
                               [L, page.evaluate(build_js)])
    return '%d of %d points' % (min(spent, pts), pts)


def open_page(browser, url, errors, **ctx):
    init = ctx.pop('init', None)
    context = browser.new_context(**ctx)
    if init:
        context.add_init_script(init)

    def route(r):
        u = r.request.url
        if u.startswith('http://127.0.0.1'):
            return r.continue_()
        if 'fonts.googleapis.com' in u:
            return r.fulfill(status=200, content_type='text/css', body='')
        errors.append('external request: ' + u)
        return r.fulfill(status=204, body='')
    context.route('**/*', route)
    page = context.new_page()
    page.on('console', lambda m: errors.append('console %s: %s' % (m.type, m.text)) if m.type == 'error' else None)
    page.on('pageerror', lambda e: errors.append('page error: %s' % e))
    page.goto(url, wait_until='load')
    return context, page


def initialized(page, errors, step):
    """The page finished its init: builder, race card, planner and raid results rendered, and nothing threw."""
    assert not errors, step + ': ' + '; '.join(errors)
    n_cells, n_talents, races = page.evaluate("() => [document.querySelectorAll('.tal').length, CLASS.talents.length, Object.keys(CLASS.races)]")
    assert_eq(n_cells, n_talents, step + ': talent cells')
    assert race_now(page) in races, step + ': data-race is %r' % race_now(page)
    assert text(page, '#raceCard h3'), step + ': race card'
    assert text(page, '#bPts'), step + ': builder points'
    assert 1 <= int(text(page, '#lvlBig')) <= 60, step + ': level'
    assert text(page, '#raidVerdict'), step + ': raid verdict'


def base_run(browser, url):
    errors = []
    context, page = open_page(browser, url, errors, viewport={'width': 1280, 'height': 900})
    models = page.evaluate("() => [window.MageModel && MageModel.STUB ? 'stub' : 'real', window.LevelingModel && LevelingModel.STUB ? 'stub' : 'real']")
    print('page_check: raid model %s, leveling model %s' % tuple(models))
    is_stub = 'stub' in models
    has_specs = page.evaluate('() => MageModel.SPECS.length > 0')

    def no_errors(step):
        assert not errors, step + ': ' + '; '.join(errors)

    check('loads with no console errors', lambda: initialized(page, errors, 'load'))
    check('stub banner matches the models', lambda: assert_eq(page.locator('#stubBar').is_visible(), is_stub, 'banner visible'))

    def images():
        bad = page.evaluate("""() => [...document.images].filter(i => i.hidden || !i.getAttribute('src') || !i.src.startsWith('data:image/') || !i.complete || !i.naturalWidth)
            .map(i => (i.id || i.className) + ' ' + (i.alt || ''))""")
        assert not bad, 'unresolved images: %s' % bad
        cells, talents = page.evaluate("() => [document.querySelectorAll('.tal img').length, CLASS.talents.length]")
        assert_eq(cells, talents, 'talent cell icons')
        assert_eq(page.locator('.race-seg img').count(), 2 * page.evaluate('() => Object.keys(CLASS.races).length'), 'race picker portraits')
    check('every <img> resolves', images)

    def named_icons():
        missing = page.evaluate("""() => {
          const C = window.CLASS, I = window.FML_ICONS;
          const names = [C.icon, ...C.treeIcons, ...Object.values(C.talentIcons), ...Object.values(C.spellIcons),
            ...Object.values(C.races).flatMap(r => [r.icon, ...r.racials.map(x => x[2])]), ...C.specCards.map(s => s.icon),
            ...(C.siblings || []).map(s => s.icon)];
          return names.filter(n => !I[n]);
        }""")
        assert not missing, 'icons named but not embedded: %s' % missing
    check('every icon the class data names is embedded', named_icons)

    def race():
        page.click('.race-seg[data-compact="0"] button[data-race="undead"]')
        assert_eq(race_now(page), 'undead', 'data-race')
        assert_eq(storage(page).get('fml.race'), '"undead"', 'fml.race')
        assert 'Undead' in text(page, '#raceCard h3')
        page.click('#raidControls .race-seg button[data-race="skyborne"]')
        assert_eq(race_now(page), 'skyborne', 'data-race from the calculator picker')
        assert 'Skyborne High Order' in text(page, '#raceCard h3')
        no_errors('race')
    check('set race', race)

    def race_options():
        opts = page.evaluate("() => MageModel.OPTIONS.filter(o => o.race).map(o => [o.id, [].concat(o.race)])")
        for rid in ('human', 'gnome'):
            page.click('.race-seg[data-compact="0"] button[data-race="%s"]' % rid)
            for oid, races in opts:
                assert_eq(page.locator('#row-' + oid).is_hidden(), rid not in races, '%s row for %s' % (oid, rid))
        no_errors('race options')
    check('race-only raid options follow the race', race_options)

    def level():
        page.fill('#lvlNum', '42')
        page.dispatch_event('#lvlNum', 'change')
        assert_eq(text(page, '#lvlBig'), '42', 'planner level')
        assert_eq(text(page, '#bLevel'), '42', 'builder level')
        assert_eq(text(page, '#dngLvl'), '42', 'dungeon level')
        assert_eq(storage(page).get('fml.level'), '42', 'fml.level')
        page.click('#lvlChips button[data-l="20"]')
        assert_eq(text(page, '#lvlBig'), '20', 'chip level')
        page.click('#lvlUp')
        assert_eq(text(page, '#lvlBig'), '21', 'step up')
        no_errors('level')
    check('set level', level)

    def preset():
        btn = page.locator('#bPresets button[data-id^="s:"]').first
        if not has_specs or not btn.count():
            print('page_check: no raid spec presets (SPECS is empty), preset step uses Clear only')
            page.locator('#bPresets button[data-id="clear"]').click()
            assert text(page, '#bPts').startswith('0 of ')
            return
        spec_id = btn.get_attribute('data-id')[2:]
        build_js = '() => MageModel.SPECS.find(s => s.id === %s).talents' % json.dumps(spec_id)
        page.click('#lvlChips button[data-l="40"]')
        btn.click()
        assert_eq(text(page, '#bPts'), points_text(page, 40, build_js), 'preset at 40')
        assert_eq(btn.get_attribute('aria-pressed'), 'true', 'preset marked')
        assert page.locator('.tal.some, .tal.max').count() > 0
        page.click('#lvlChips button[data-l="50"]')
        assert_eq(text(page, '#bPts'), points_text(page, 50, build_js), 'preset follows the level to 50')
        assert 'fml.builder' in storage(page)
        no_errors('preset')
    check('apply a builder preset', preset)

    def points():
        page.click('#lvlChips button[data-l="50"]')
        page.locator('#bPresets button[data-id="clear"]').click()
        assert_eq(text(page, '#bPts'), '0 of 41 points', 'cleared')
        cell = page.locator('.tal[data-k="ArcaneFocus"]')
        cell.click(); cell.click()
        assert_eq(text(page, '#bPts'), '2 of 41 points', 'two points added')
        assert 'Arcane spells by 2%' in text(page, '#bInfoNow'), 'rank text from the research file'
        cell.click(button='right')
        assert_eq(text(page, '#bPts'), '1 of 41 points', 'right click removes')
        page.locator('.tal[data-k="ArcaneSubtlety"]').click()
        assert_eq(text(page, '#bPts'), '1 of 41 points', 'row 2 stays locked')
        assert 'Needs 5 points in Arcane' in text(page, '#bInfoLock')
        assert text(page, '#bRot'), 'rotation label'
        no_errors('points')
    check('add and remove talent points', points)

    def link_levels():
        page.locator('#bPresets button[data-id="clear"]').click()
        for L in (1, 5, 9, 10, 33, 60):
            page.fill('#lvlNum', str(L)); page.dispatch_event('#lvlNum', 'change')
            if L >= 10:
                page.locator('.tal[data-k="ArcaneFocus"]').click()
            h = page.locator('#bLink').input_value().split('#', 1)[1]
            d = page.evaluate('h => { const c = (%s)(); return c.decode(h); }' % CORE_JS, h)
            assert d, 'the copied link does not decode at level %d: %s' % (L, h)
            assert_eq(d['level'], max(10, L), 'link level at level %d' % L)
        no_errors('link levels')
    check('the copied link decodes at levels 1 to 60', link_levels)

    def b_link():
        build_js = ('() => MageModel.SPECS.length ? MageModel.SPECS[MageModel.SPECS.length - 1].talents : CLASS.specCards[0].build')
        link = page.evaluate('() => { const c = (%s)(); return c.encode(60, c.clean((%s)()), 2); }' % (CORE_JS, build_js))
        set_hash(page, '#' + link)
        assert_eq(text(page, '#bLevel'), '60', 'decoded level')
        assert_eq(text(page, '#bPts'), points_text(page, 60, build_js), 'decoded build')
        assert_eq(page.eval_on_selector('#bGear', 'e => e.value'), '2', 'gear')
        assert page.locator('#bLink').input_value().endswith('#' + link), 'the copy link reproduces the link'
        before = text(page, '#bPts')
        for bad in ('#b-60-' + '9' * 54 + '-1', '#' + link + '%0A', '#' + link[:-1] + '3', '#b-9-' + '0' * 54 + '-1'):
            set_hash(page, bad)
            assert_eq(text(page, '#bPts'), before, 'bad link %s changed the build' % bad[:20])
            assert_eq(text(page, '#bLevel'), '60', 'bad link changed the level')
        good = page.evaluate('() => { const c = (%s)(); const r = c.empty(); r.ArcaneFocus = 3; return c.encode(20, r, 1); }' % CORE_JS)
        set_hash(page, '#' + good)
        assert_eq(text(page, '#bLevel'), '20', 'a good link after the bad ones takes effect')
        assert_eq(text(page, '#bPts'), '3 of 11 points', 'good link build')
        no_errors('#b- link')
    check('open #b- links, good and bad', b_link)

    def race_link():
        set_hash(page, '#race-gnome')
        assert_eq(race_now(page), 'gnome', '#race-gnome')
        for bad in ('#race-nobody', '#race-constructor', '#race-__proto__', '#race-tostring', '#race-hasownproperty'):
            set_hash(page, bad)
            assert_eq(race_now(page), 'gnome', bad + ' ignored')
            assert_eq(storage(page).get('fml.race'), '"gnome"', bad + ' not saved')
        set_hash(page, '#race-troll')
        assert_eq(race_now(page), 'troll', 'a good race link after the bad ones takes effect')
        set_hash(page, '#lvl-24')
        assert_eq(text(page, '#lvlBig'), '24', '#lvl-24')
        set_hash(page, '#changelog')
        assert page.evaluate("() => document.getElementById('changelog').open"), '#changelog opens its details'
        set_hash(page, '#v-dng')
        no_errors('hash links')
    check('open #race-, #lvl- and element links, including prototype names', race_link)

    def raid():
        before = storage(page).get('fml.calc1')
        boxes = page.locator('#raidControls input[type=checkbox]:visible')
        if boxes.count():
            box = boxes.first
            box.click()
            calc = json.loads(storage(page)['fml.calc1'])
            assert_eq(calc[box.get_attribute('id')[4:]], box.is_checked(), 'toggle saved')
            assert before != storage(page)['fml.calc1']
        segs = page.locator('#raidControls .seg:not(.race-seg) button')
        if segs.count():
            seg = segs.last
            seg.click()
            assert_eq(seg.get_attribute('aria-pressed'), 'true', 'segment pressed')
        for sel in ('#opt-spN', '#opt-critN'):
            assert page.locator(sel).count() == 1, 'OPTIONS has no %s control (CONTRACTS section 3 lists it)' % sel[5:-1]
        page.fill('#opt-spN', '800'); page.dispatch_event('#opt-spN', 'change')
        page.fill('#opt-critN', '15'); page.dispatch_event('#opt-critN', 'change')
        calc = json.loads(storage(page)['fml.calc1'])
        sp_opt = page.evaluate("() => MageModel.OPTIONS.find(o => o.id === 'sp')")
        assert_eq(calc['sp'], max(sp_opt['min'], min(sp_opt['max'], 800)), 'spell power saved')
        assert abs(calc['crit'] - 0.15) < 1e-9 or page.evaluate("() => { const o = MageModel.OPTIONS.find(o => o.id === 'crit'); return o.max < 0.15 || o.min > 0.15; }"), \
            'crit typed in percent, saved as a fraction: %r' % calc['crit']
        if has_specs:
            assert page.locator('.bar-row').count() >= 1
        assert text(page, '#raidVerdict')
        page.fill('#bSp', '80'); page.dispatch_event('#bSp', 'input')
        assert text(page, '#cmpOut'), 'item comparer answered'
        page.click('#dngSide button[data-v="all"]')
        assert_eq(storage(page).get('fml.dngAll'), 'true', 'dungeon filter saved')
        no_errors('raid')
    check('raid options, weights, compare and dungeon filter', raid)

    def keys():
        bad = [k for k in storage(page) if not k.startswith('fml.')]
        assert not bad, 'foreign keys: %s' % bad
        need = {'fml.race', 'fml.level', 'fml.dngAll', 'fml.calc1', 'fml.builder'}
        assert need <= set(storage(page)), 'missing %s' % (need - set(storage(page)))
    check('localStorage only has fml. keys', keys)

    def reload():
        race_before, pts_before = race_now(page), text(page, '#bPts')
        page.evaluate("() => { history.replaceState(null, '', location.pathname); }")
        page.reload(wait_until='load')
        initialized(page, errors, 'reload')
        assert_eq(race_now(page), race_before, 'race after reload')
        assert_eq(text(page, '#lvlBig'), '24', 'level after reload')
        assert_eq(text(page, '#bPts').split(' of ')[0], pts_before.split(' of ')[0], 'builder after reload')
    check('saved state survives a reload', reload)

    def garbage():
        values = {
            'race': ['"constructor"', '"__proto__"', 'not json', '42', '{"a":1}', 'null', '"toString"'],
            'level': ['"abc"', '{}', '1e9', '-5', 'true', 'not json', '"__proto__"'],
            'dngAll': ['"yes"', '[1]', 'not json', '{}', 'null', '0', '"true"'],
            'calc1': ['"x"', '[1,2]', '{"sp":"800","crit":null,"__proto__":{"sp":1},"constructor":5}', 'not json', 'null', '42', '{"sp":1e99,"gearHit":-4}'],
            'builder': ['"x"', '[]', '{"ranks":{"__proto__":5,"constructor":3,"ArcaneFocus":"9"},"gear":"2","preset":"constructor"}',
                        '{"ranks":[1,2,3],"gear":7,"preset":{"a":1}}', 'not json', '{"ranks":{"ArcanePower":1},"preset":"__proto__"}', 'null'],
            'tests': ['"x"', '[true]', 'not json', '{"__proto__":{"t1c":true}}', 'null', '7', '{"t1c":"yes"}'],
        }
        for i in range(7):
            round_values = {k: v[i] for k, v in values.items()}
            page.evaluate("vals => { localStorage.clear(); Object.entries(vals).forEach(([k, v]) => localStorage.setItem('fml.' + k, v)); }", round_values)
            page.reload(wait_until='load')
            initialized(page, errors, 'garbage storage round %d %s' % (i, round_values))
            bad = [k for k in storage(page) if not k.startswith('fml.')]
            assert not bad, 'foreign keys after garbage: %s' % bad
            page.locator('.tal[data-k="ArcaneFocus"]').click()      # still interactive
            assert not errors, 'after a click in round %d: %s' % (i, '; '.join(errors))
    check('garbage and prototype-key storage values never break init', garbage)

    def class_switch():
        assert page.locator('#classNav').is_visible(), 'class switch visible'
        cur = page.locator('#classNav [aria-current="page"]')
        assert_eq(cur.count(), 1, 'one current class chip')
        assert_eq(cur.evaluate('e => e.tagName'), 'SPAN', 'the current class is a chip, not a link')
        assert_eq(cur.text_content().strip(), page.evaluate('() => CLASS.name'), 'current class name')
        sibs = page.evaluate('() => CLASS.siblings')
        assert_eq(page.locator('#classNav a').count(), len(sibs), 'one link per sibling class')
        wl = [s for s in sibs if s['id'] == 'warlock'][0]
        link = page.locator('#classNav a', has_text=wl['name'])
        href = lambda: link.get_attribute('href')
        page.click('.race-seg[data-compact="0"] button[data-race="undead"]')
        page.fill('#lvlNum', '33'); page.dispatch_event('#lvlNum', 'change')
        assert_eq(href(), wl['url'] + '#go-undead-33', 'href after race and level')
        page.click('.race-seg[data-compact="0"] button[data-race="skyborne"]')
        assert_eq(href(), wl['url'] + '#go-33', 'a race the sibling lacks is left out')
        page.click('#lvlUp')
        assert_eq(href(), wl['url'] + '#go-34', 'href follows the level')
        page.click('.race-seg[data-compact="0"] button[data-race="orc"]')
        assert_eq(href(), wl['url'] + '#go-orc-34', 'href follows the race')
        set_hash(page, '#lvl-12')
        assert_eq(href(), wl['url'] + '#go-orc-12', 'href follows a #lvl- link')
        no_errors('class switch')
    check('class switch links carry race and level', class_switch)

    def go_links():
        def at(race, level, what):
            assert_eq((race_now(page), text(page, '#lvlBig')), (race, level), what)
        page.click('.race-seg[data-compact="0"] button[data-race="human"]')
        set_hash(page, '#go-undead-24')
        at('undead', '24', '#go-undead-24')
        assert_eq(storage(page).get('fml.race'), '"undead"', 'race saved')
        assert_eq(storage(page).get('fml.level'), '24', 'level saved')
        set_hash(page, '#go-skyborne-30')
        at('skyborne', '30', '#go-skyborne-30')
        set_hash(page, '#go-40')
        at('skyborne', '40', '#go-40 sets the level only')
        set_hash(page, '#go-constructor-24')
        at('skyborne', '24', '#go-constructor-24 keeps the race and sets the level')
        assert_eq(storage(page).get('fml.race'), '"skyborne"', 'constructor not saved')
        page.evaluate("() => history.replaceState(null, '', location.pathname + '#go-constructor-25')")
        page.reload(wait_until='load')
        initialized(page, errors, 'reload on #go-constructor-25')
        at('skyborne', '25', 'reload on #go-constructor-25')
        set_hash(page, '#go-hasownproperty-26')
        at('skyborne', '26', 'prototype name keeps the race')
        set_hash(page, '#go-99')
        at('skyborne', '60', '#go-99 clamps to 60')
        set_hash(page, '#go-0')
        at('skyborne', '1', '#go-0 clamps to 1')
        for bad in ('#go-troll-24%0A', '#go-troll-24%0D', '#go-troll-24%0D%0A', '#go-troll-24x', '#go-troll-245', '#go--24',
                    '#go-Troll-24', '#go-troll-24-', '#xgo-troll-24', '#go-__proto__-24', '#go-troll', '#go-', '#go-troll-%32%34%20'):
            set_hash(page, bad)
            at('skyborne', '1', bad + ' changes nothing')
        set_hash(page, '#go-troll-12')
        at('troll', '12', 'a good #go- link after the bad ones takes effect')
        set_hash(page, '#b-12-' + '0' * 54 + '-1')
        assert_eq(text(page, '#bPts'), '0 of 3 points', 'the #b- route still works next to #go-')
        set_hash(page, '#race-gnome')
        assert_eq(race_now(page), 'gnome', 'the #race- route still works next to #go-')
        no_errors('#go- links')
    check('incoming #go- links from a sibling class page', go_links)

    todo = page.locator('.todo').count()
    context.close()
    return todo


def fixture_run(browser, url):
    errors = []
    context, page = open_page(browser, url, errors, viewport={'width': 1280, 'height': 900}, init=FIXTURE_JS)

    def content():
        initialized(page, errors, 'fixture load')
        legal = page.evaluate("""() => { const c = TalentCore.make(CLASS.talents, CLASS.talentRules), o = c.expand(CLASS.planner.order);
            for (let L = 10; L <= 60; L++) if (!c.buildOk(c.fromOrder(o, L), L)) return L; return 0; }""")
        assert_eq(legal, 0, 'fixture order illegal at level')
        assert page.locator('#c-fx-proof').count() == 1 and page.locator('#c-fx-test').count() == 1
        assert 'Checked by the model' in text(page, '#claimList')
        assert page.locator('#testList li').count() == 2
        page.click('#t1c')
        assert_eq(json.loads(storage(page)['fml.tests']), {'t1c': True}, 'test tick saved')
        set_hash(page, '#t2')
        set_hash(page, '#c-fx-test')
        assert page.evaluate("() => document.getElementById('c-fx-test').open")
        assert page.locator('#ruleBody table tbody tr').count() == 1
        assert page.locator('#talentValues table').count() == 1
        page.click('#lvlChips button[data-l="30"]')
        assert page.locator('#pCombo img').count() == 3
        assert page.locator('#pTal li.fresh').count() == 1
        assert page.locator('#pExtra').is_visible()
        page.click('#bPresets button[data-id="plan"]')
        assert_eq(text(page, '#bPts'), '21 of 21 points', 'page plan preset')
        assert 'page plan' in text(page, '#bVs')
        page.locator('#bPresets button[data-id="p:fx"]').click()
        assert page.locator('#specCards .tt a').count() >= 1
        page.locator('#specCards .tt a').first.click()
        page.wait_for_function("() => document.getElementById('bLevel').textContent === '60'", timeout=3000)
        assert_eq(page.locator('#claimList .todo, #testList .todo, #ruleBody .todo').count(), 0, 'content placeholders left')
        assert not errors, '; '.join(errors)
    check('fixture content renders and works', content)
    context.close()


def phone_and_themes(browser, url):
    for scheme, accent in (('light', '#2F4FAE'), ('dark', '#86A6F2')):
        errors = []
        context, page = open_page(browser, url, errors, viewport={'width': 375, 'height': 800}, color_scheme=scheme, is_mobile=True, has_touch=True)

        def phone():
            wide = page.evaluate('() => document.documentElement.scrollWidth - document.documentElement.clientWidth')
            assert wide <= 0, 'page scrolls sideways by %dpx at 375px' % wide
            assert page.locator('#bTabs').is_visible(), 'tree tabs show on phones'
            box = page.locator('#classNav').bounding_box()
            assert page.locator('#classNav').is_visible() and box['x'] >= 0 and box['x'] + box['width'] <= 375, 'class switch fits the phone width'
            assert_eq(page.locator('.toc a[href^="http"], .toc .classnav').count(), 0, 'the class switch stays out of the section nav')
            assert_eq(page.locator('.btree.on').count(), 1, 'one tree at a time')
            page.locator('#bTabs button').nth(2).click()
            assert page.locator('.btree.t2').is_visible()
            got = page.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()")
            assert_eq(got.upper(), accent.upper(), scheme + ' accent')
            assert not errors, '; '.join(errors)
        check('phone width and %s colors' % scheme, phone)
        context.close()


def main():
    if not os.path.exists(os.path.join(ROOT, 'index.html')):
        sys.exit('index.html is missing: run python src/build.py first')
    httpd = serve()
    url = 'http://127.0.0.1:%d/index.html' % httpd.server_address[1]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            todo = base_run(browser, url)
            fixture_run(browser, url)
            phone_and_themes(browser, url)
        finally:
            browser.close()
            httpd.shutdown()
    print('TODO-CONTENT placeholders visible on the page: %d' % todo)
    if failures:
        print('FAILED %d of %d checks:' % (len(failures), len(failures) + passed[0]))
        for f in failures:
            print('  ' + f)
        sys.exit(1)
    print('All %d page checks passed.' % passed[0])


if __name__ == '__main__':
    main()
