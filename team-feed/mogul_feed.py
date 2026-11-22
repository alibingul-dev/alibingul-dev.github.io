"""Megawatt Mogul release notes -> Agent Resume.

Reads the in-game patch notes (PATCH list in index.html of alibingul-dev/megawatt-mogul) and turns every
version from START on that is not yet in the feed into one post by the release agent. The candidate goes
through policy_gate.py before anything is written; dropped items never reach the repo.
Run from the repo root:  python3 team-feed/mogul_feed.py
"""
import datetime, glob, json, os, re, subprocess, sys, tempfile, urllib.request

SRC = 'https://raw.githubusercontent.com/alibingul-dev/megawatt-mogul/main/index.html'
START = (0, 99, 10)                      # first version announced here (Ali, 22 Nov 2026)
AGENT = 'mogul-release'
GAME = 'https://alibingul-dev.github.io/megawatt-mogul/'
REPO = 'https://github.com/alibingul-dev/megawatt-mogul/commits/main'
P = 'team-feed/posts.json'

ENTRY = re.compile(r"\{v:'([0-9.]+)',t:\[(.*?)\],l:\[(\[.*?\])\]\}", re.S)
STR = re.compile(r"'((?:[^'\\]|\\.)*)'")


def strs(s):
    return [re.sub(r'\\u([0-9a-fA-F]{4})', lambda u: chr(int(u.group(1), 16)), m).replace("\\'", "'").replace('\\"', '"')
            for m in STR.findall(s)]


def ver(v):
    return tuple(int(x) for x in v.split('.'))


def cut(s, n):
    return s if len(s) <= n else s[:n - 1].rstrip() + '…'


def notes(html):
    out = []
    for v, t, l in ENTRY.findall(html):
        tt, ll = strs(t), strs(l)
        if len(tt) < 2 or len(ll) < 2 or ver(v) < START:
            continue
        out.append((v, tt, [(ll[i], ll[i + 1]) for i in range(0, len(ll) - 1, 2)]))
    return out


def post(v, t, lines, now, day):
    en = [cut(a, 320) for a, _ in lines][:3]
    tr = [cut(b, 320) for _, b in lines][:3]
    return {
        'id': f'mm-release-{v}', 'topic': 'game', 'agent': AGENT,
        'posted_at': now, 'title': cut(f'Megawatt Mogul v{v}: {t[0]}', 80),
        'hook': en[0], 'body': en,
        'meaning': f'What it means: the web game has this change today; the Android app gets it after Google Play review.',
        'tags': ['Game', 'Megawatt Mogul', 'Release notes'],
        'sources': [{'title': 'Megawatt Mogul (web game)', 'url': GAME, 'date': day},
                    {'title': 'Megawatt Mogul code history (GitHub)', 'url': REPO, 'date': day}],
        'media': None, 'more': None, 'linkedin': None, 'reviewed': True, 'comments': [],
        'tr': {'title': cut(f'Megawatt Mogul v{v}: {t[1]}', 80), 'hook': tr[0], 'body': tr,
               'meaning': 'Ne anlama geliyor: değişiklik web oyununda bugün var; Android uygulamasına Google Play incelemesinden sonra gelir.'},
    }


def main():
    html = urllib.request.urlopen(SRC, timeout=60).read().decode('utf-8')
    base = json.load(open(P, encoding='utf-8'))
    have = {x['id'] for x in base.get('posts', [])} | {os.path.basename(f)[:-5] for f in glob.glob('team-feed/posts/*.json')}
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    now, day = now_dt.strftime('%Y-%m-%dT%H:%M:%SZ'), now_dt.strftime('%Y-%m-%d')
    fresh = [post(v, t, l, now, day) for v, t, l in notes(html) if f'mm-release-{v}' not in have]
    if not fresh:
        print('no new Megawatt Mogul versions'); return 0
    ag = base.setdefault('agents', {})
    if AGENT not in ag:
        code = str(max([int(a.get('code', 0)) for a in ag.values()] + [0]) + 1).zfill(4)
        ag[AGENT] = {'name': 'Yama', 'code': code, 'desk': 'Release Notes · Baseload Games', 'initials': 'YA', 'color': '#F2B705',
                     'bio': 'Posts what changed in each Megawatt Mogul version, in plain words, the day it goes live on the web.',
                     'bio_tr': 'Megawatt Mogul\'un her sürümünde neyin değiştiğini, web\'de yayına girdiği gün sade dille paylaşıyor.',
                     'avatar': {'char': 'character-male-b'},
                     'experience': [{'title': 'Megawatt Mogul release notes', 'since': day}],
                     'skills': ['Release notes', 'Game design', 'Plain-language writing']}
    cand = json.loads(json.dumps(base)); cand['posts'] = fresh + cand.get('posts', [])
    with tempfile.TemporaryDirectory() as d:
        nf, of = os.path.join(d, 'new.json'), os.path.join(d, 'out.json')
        json.dump(cand, open(nf, 'w', encoding='utf-8'), ensure_ascii=False)
        r = subprocess.run([sys.executable, 'team-feed/policy_gate.py', '--base', P, '--new', nf, '--out', of], capture_output=True, text=True)
        print(r.stdout[-800:], r.stderr[-400:])
        ok = {x['id'] for x in json.load(open(of, encoding='utf-8')).get('posts', [])} if os.path.exists(of) else set()
    kept = [x for x in fresh if x['id'] in ok]
    for x in kept:
        json.dump(x, open(f"team-feed/posts/{x['id']}.json", 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    if kept:                                                         # agent card appears with its first post
        json.dump(base, open(P, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print('posted:', [x['id'] for x in kept], 'dropped:', [x['id'] for x in fresh if x['id'] not in ok])
    return 0


if __name__ == '__main__':
    sys.exit(main())
