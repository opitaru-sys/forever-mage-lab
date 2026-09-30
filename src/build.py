"""Build the page from src/page.src.html, the class data, the talent engine, the page parts and the models.

Run from the repo root:  python src/build.py [--stubs]
Writes index.html (full document, for GitHub Pages) and src/artifact.html (fragment, for the claude.ai copy).
Uses model.js and leveling.js from the repo root when they exist, else the stubs in src/stubs/ (and says which).
--stubs forces the stubs even when the real models exist.
Fails loudly when a placeholder is missing or doubled, when an inserted file contains a placeholder, when an
inserted file could close its <script> early, or when the output contains an em or en dash.
"""
import base64
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHES = (chr(0x2013), chr(0x2014))


def fail(msg):
    sys.exit('build.py: ' + msg)


def rd(*p):
    with open(os.path.join(ROOT, *p), encoding='utf-8') as f:     # text mode: CRLF sources read as \n
        return f.read()


def wr(rel, text):
    with open(os.path.join(ROOT, rel), 'w', encoding='utf-8', newline='\r\n') as f:
        f.write(text)


def model(name, stub, force_stub):
    if not force_stub and os.path.exists(os.path.join(ROOT, name)):
        return rd(name), name
    return rd('src', 'stubs', stub), 'src/stubs/' + stub + ' (STUB)'


def fmt_num(v):
    return '%g' % v


def rank_texts(t, r):
    """Every rank's effect text for talent t, from its research record r.

    The top-rank text is the template: each number in it that equals a curve's top value becomes that curve's value
    at the rank (millisecond curves are compared in seconds). The template must reproduce the sourced rank-1 text
    exactly, or the talent must have at most 2 ranks (then both texts are sourced); otherwise the build fails.
    """
    m, top, first = t['m'], r['effectTopRank'], r['effectRank1']
    if m == 1:
        return [top]
    curves = []
    for k, v in t['perRank'].items():
        if isinstance(v, list) and len(v) == m and all(isinstance(x, (int, float)) for x in v):
            curves.append([x / 1000 for x in v] if k.endswith('Ms') else v)

    def at(i):
        def rep(mo):
            num = float(mo.group(0))
            for c in curves:
                if abs(c[-1] - num) < 1e-9:
                    return fmt_num(c[i])
            return mo.group(0)
        return re.sub(r'\d+(?:\.\d+)?', rep, top)

    if at(0) == first:
        return [at(i) for i in range(m - 1)] + [top]
    if m == 2:
        return [first, top]
    fail('cannot derive rank texts for %s: the template does not reproduce the rank 1 text' % t['k'])


def talent_texts(talents):
    research = json.loads(rd('data', 'mage_talents_research.json'))['talents']
    by_id = {r['spellId']: r for r in research}
    out = {}
    for t in talents:
        r = by_id.get(t['spellId'])
        if not r or r['name'] != t['n']:
            fail('no research record for talent %s (spell %s)' % (t['k'], t['spellId']))
        out[t['k']] = rank_texts(t, r)
    return out


def icons():
    names = [ln.strip() for ln in rd('assets', 'icons', 'ICONS.txt').splitlines()]
    names = [n for n in names if n and not n.startswith('#')]
    if len(set(names)) != len(names):
        fail('duplicate names in assets/icons/ICONS.txt')
    out = {}
    for n in sorted(names):
        path = os.path.join(ROOT, 'assets', 'icons', n + '.jpg')
        if not os.path.exists(path):
            fail('icon listed but missing: %s.jpg (run python assets/icons/fetch_icons.py)' % n)
        with open(path, 'rb') as f:
            out[n] = 'data:image/jpeg;base64,' + base64.b64encode(f.read()).decode()
    return out


def fill(src, parts):
    """Replace each /*SLOT*/ in src once, in a single pass, after checking every slot and every inserted part."""
    marks = {'/*%s*/' % k: v for k, v in parts.items()}
    for mark in marks:
        n = src.count(mark)
        if n != 1:
            fail('placeholder %s appears %d times in src/page.src.html (needs exactly 1)' % (mark, n))
    for name, text in parts.items():
        for mark in marks:
            if mark in text:
                fail('inserted part %s contains the placeholder %s' % (name, mark))
        low = text.lower()
        if '</script' in low:
            fail('inserted part %s contains "</script", which would end its script tag early' % name)
        if '<!--' in low and '<script' in low:
            fail('inserted part %s contains "<!--" and "<script", which can put the HTML parser in the double-escaped state' % name)
    pattern = re.compile('|'.join(re.escape(m) for m in marks))
    return pattern.sub(lambda mo: marks[mo.group(0)], src)


def main():
    force_stub = '--stubs' in sys.argv[1:]
    data = json.loads(rd('data', 'talents.json'))
    mdl, mdl_from = model('model.js', 'model.stub.js', force_stub)
    lvl, lvl_from = model('leveling.js', 'leveling.stub.js', force_stub)
    icon_map = icons()
    compact = dict(ensure_ascii=False, separators=(',', ':'))
    parts = {
        'TALENTS': json.dumps(data, **compact),
        'TALENT_TEXT': json.dumps(talent_texts(data['talents']), **compact),
        'CLASS': rd('src', 'class.js'),
        'TALENTCORE': rd('src', 'talentcore.js'),
        'MODEL': mdl,
        'LEVELING': lvl,
        'ICONS': json.dumps(icon_map),
        'CONTENT': rd('src', 'content.js'),
        'RAID': rd('src', 'raid.js'),
        'BUILDER': rd('src', 'builder.js'),
    }
    src = rd('src', 'page.src.html')
    body = fill(src, parts)
    for d in DASHES:
        if d in body:
            at = body.index(d)
            fail('the page contains an em or en dash near: %r' % body[max(0, at - 60):at + 20])
    end = body.index('</style>') + len('</style>')
    if '<script' in body[:end]:
        fail('a <script> comes before the first </style>; the head split would break')
    wr(os.path.join('src', 'artifact.html'), body)
    head_extra = ('<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                  '<meta name="darkreader-lock">\n<style>[hidden]{display:none!important}</style>\n')
    doc = '<!doctype html>\n<html lang="en">\n<head>\n' + head_extra + body[:end] + '\n</head>\n<body>\n' + body[end:] + '\n</body>\n</html>\n'
    wr('index.html', doc)
    print('raid model:', mdl_from)
    print('leveling model:', lvl_from)
    print('icons:', len(icon_map))
    print('index.html', len(doc), 'chars; src/artifact.html', len(body), 'chars')


if __name__ == '__main__':
    main()
