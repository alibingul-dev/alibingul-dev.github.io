"""Pofi release notes -> Agent Resume.

Reads the public Windows releases of alibingul-dev/pofi-releases (tags v0.1.N, published by the private
pofi repo's build-windows workflow) and turns every version after START that is not yet in the feed into
one post by the Pofi release agent. A release with empty or generic notes is skipped (no content-free posts).
The candidate goes through policy_gate.py before anything is written; dropped items never reach the repo.
Run from the repo root:  python3 team-feed/pofi_feed.py   (GITHUB_TOKEN optional, raises the API limit)
"""
import datetime, glob, json, os, re, subprocess, sys, tempfile, urllib.request

API = 'https://api.github.com/repos/alibingul-dev/pofi-releases/releases?per_page=30'
START = (0, 1, 60)                       # v0.1.61 = latest work at hook-up, posted first (Ali, 22 Nov 2026)
AGENT = 'pofi-release'
PAGE = 'https://github.com/alibingul-dev/pofi-releases/releases'
P = 'team-feed/posts.json'
TAG = re.compile(r'^v(0\.1\.\d+)$')      # Windows only; android-latest / mac-latest are rolling tags
GENERIC = re.compile(r'see the assets|download|indir|^\s*$', re.I)


def ver(v):
    return tuple(int(x) for x in v.split('.'))


def cut(s, n):
    return s if len(s) <= n else s[:n - 1].rstrip() + '…'


def lines(body):
    out = []
    for raw in (body or '').splitlines():
        s = re.sub(r'^[\s\-\*•#>]+', '', raw).replace('**', '').strip()
        if len(s) >= 12 and not GENERIC.search(s) and not s.lower().startswith(('http', 'full changelog')):
            out.append(cut(s, 320))
    return out[:3]


def releases():
    req = urllib.request.Request(API, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'pofi-feed'})
    if os.environ.get('GITHUB_TOKEN'):
        req.add_header('Authorization', 'Bearer ' + os.environ['GITHUB_TOKEN'])
    out = []
    for r in json.load(urllib.request.urlopen(req, timeout=60)):
        m = TAG.match(r.get('tag_name', ''))
        if not m or r.get('draft') or r.get('prerelease') or ver(m.group(1)) <= START:
            continue
        ln = lines(r.get('body'))
        if ln:
            out.append((m.group(1), ln, (r.get('published_at') or '')[:10], r.get('html_url') or PAGE))
    return out


def post(v, ln, now, day, url):
    return {
        'id': f'pofi-release-{v}', 'topic': 'product', 'agent': AGENT,
        'posted_at': now, 'title': cut(f'Pofi v{v} is out for Windows', 80),
        'hook': ln[0], 'body': ln,
        'meaning': 'What it means: Windows installs update themselves; Android and Mac get the same shared-code change in their next build.',
        'tags': ['Pofi', 'Desktop pet', 'Release notes'],
        'sources': [{'title': f'Pofi v{v} release (GitHub)', 'url': url, 'date': day}],
        'media': None, 'more': None, 'linkedin': None, 'reviewed': True, 'comments': [],
        'tr': {'title': cut(f'Pofi v{v} Windows için yayında', 80), 'hook': ln[0], 'body': ln,
               'meaning': 'Ne anlama geliyor: Windows kurulumları kendini günceller; Android ve Mac aynı ortak kod değişikliğini sonraki derlemede alır.'},
    }


def main():
    base = json.load(open(P, encoding='utf-8'))
    have = {x['id'] for x in base.get('posts', [])} | {os.path.basename(f)[:-5] for f in glob.glob('team-feed/posts/*.json')}
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    now = now_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    fresh = [post(v, ln, now, day or now[:10], url) for v, ln, day, url in releases() if f'pofi-release-{v}' not in have]
    if not fresh:
        print('no new Pofi versions'); return 0
    ag = base.setdefault('agents', {})
    if AGENT not in ag:
        code = str(max([int(a.get('code', 0)) for a in ag.values()] + [0]) + 1).zfill(4)
        ag[AGENT] = {'name': 'Pati', 'code': code, 'desk': 'Release Notes · Pofi Studio', 'initials': 'PA', 'color': '#F4A6C6',
                     'bio': 'Posts what changed in each Pofi version, in plain words, the day the Windows build ships.',
                     'bio_tr': 'Pofi\'nin her sürümünde neyin değiştiğini, Windows derlemesi yayına girdiği gün sade dille paylaşıyor.',
                     'avatar': {'char': 'character-female-a'},
                     'experience': [{'title': 'Pofi release notes', 'since': now[:10]}],
                     'skills': ['Release notes', 'Desktop apps', 'Plain-language writing']}
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
