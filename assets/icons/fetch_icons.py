"""Download the icons listed in ICONS.txt that are not in this folder yet.

Run from anywhere:  python assets/icons/fetch_icons.py
Source: Wowhead's image server, 36 px "medium" size. Existing files are never overwritten.
"""
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
URL = 'https://wow.zamimg.com/images/wow/icons/medium/%s.jpg'
JPEG_MAGIC = b'\xff\xd8\xff'


def names():
    with open(os.path.join(HERE, 'ICONS.txt'), encoding='utf-8') as f:
        rows = [ln.strip() for ln in f]
    return [r for r in rows if r and not r.startswith('#')]


def fetch(name):
    req = urllib.request.Request(URL % name, headers={'User-Agent': 'forever-mage-lab icon fetch'})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = r.read()
    if not data.startswith(JPEG_MAGIC):
        raise ValueError('not a JPEG')
    return data


def main():
    failed = []
    got = 0
    for n in names():
        path = os.path.join(HERE, n + '.jpg')
        if os.path.exists(path):
            continue
        try:
            data = fetch(n)
        except (urllib.error.URLError, ValueError, OSError) as e:
            failed.append('%s (%s)' % (n, e))
            continue
        with open(path, 'wb') as f:
            f.write(data)
        got += 1
    print('downloaded', got, 'icons')
    if failed:
        print('FAILED:', ', '.join(failed))
        sys.exit(1)


if __name__ == '__main__':
    main()
