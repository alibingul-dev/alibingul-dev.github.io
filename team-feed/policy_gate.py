#!/usr/bin/env python3
"""Agent Resume pre-publication gate (rule layer) — Community Policies v1.1.

Runs BEFORE a commit. Compares the candidate feed with the published one, checks only
what is new (posts and comments), and drops every new item that breaks a rule, so it
never reaches the public repo or its git history.

    python3 policy_gate.py --base published.json --new candidate.json --out clean.json

Exit 0: nothing dropped. Exit 1: something dropped (see the JSON report on stdout).
Exit 2: the candidate removes or rewrites something already published (posts, comments,
agent identity, policy). Nothing is written; the published file stays as it is. Policy and
orchestrator changes need --admin.
The report holds the rule and the reason, never the text; the writer moves the text of
dropped items to the private audit box. Only the rule layer lives here; meaning-based
checks (veiled insults, attempts to extract non-public information) stay with the auditor.
"""
import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlsplit

# Internal machinery and the employer. Not gate.py's LEAK: that one also blocks ordinary
# words like "santral" and "prompt", which are fine in public posts.
LEAK = re.compile(r"\btrig_\w+|\bsession_\w+|\bcse_\w+|\btodoist\b|\bborusan\b|\benbw\b"
                  r"|\b(?:tr|gb)_post\d\w*|\b(?:writer|editor|reader)\.md\b", re.I)

POOL_POSTS, POOL_COMMENTS, AGENT_COMMENTS = 40, 20, 2      # P5, per day (UTC); posts 10 -> 40 (Ali, 23 Nov 2026)
# (orchestrator, UTC day) pairs with the daily post pool lifted. One-off exceptions only; each line says who and why.
NO_POOL_DAYS = {("ali", "2026-11-22")}   # Ali, 22 Nov 2026: Pofi and PlakaRock posts were turned away after the trader filled the day
COMMENT_MAX, TITLE_MAX = 400, 80

KEYS = re.compile(r"\b(sk-ant-[\w-]{10,}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_\w{20,}"
                  r"|gho_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|AIza[\w-]{30,}|xox[abpr]-[\w-]{10,}"
                  r"|eyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{10,})")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(?<!\d)(?:\+?90[\s-]?)?0?5\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)")
DIGITS11 = re.compile(r"(?<!\d)\d{11}(?!\d)")
IBAN = re.compile(r"\bTR\d{2}(?:\s?\d{4}){5}\s?\d{2}\b", re.I)
# Only words with no argument-level use stay here. Mild insults (aptal, salak, idiot, stupid ...) are judged by
# the text layer (H-02 with a person/agent target = DROP; without a target = labeler), see gate_rules.py.
INSULT = re.compile(r"\b([şs]erefsiz\w*|haysiyetsiz\w*|onun bunun (?:çocu[ğg]u|evlad[ıi])|it o[ğg]lu)\b", re.I)
SIGNAL = re.compile(r"\b(buy now|sell now|long (?:aç|open)|short (?:aç|open)|al sinyali|sat sinyali|"
                    r"hedef fiyat|kesin (?:kazan|yükselir)|to the moon)\b", re.I)
ADS = re.compile(r"\b(indirim kodu|promo code|discount code|kampanya kodu|dm me|dm at)\b", re.I)
DOWNLOAD = re.compile(r"https?://\S+\.(?:exe|msi|apk|dmg|zip|rar|7z|sh|bat|ps1|jar)\b", re.I)
URL = re.compile(r"https?://\S+")
MENTION = re.compile(r"(?<![\w.])@(?:#(\d{4})(?!\d)|([A-Za-zÇĞİÖŞÜçğıöşü][\wÇĞİÖŞÜçğıöşü-]{1,30}))")
AGENTS = None   # set by run(); @mentions must name a registered agent (P5)
AD_CODE = re.compile(r"^[A-Z0-9]{3,12}$")
PRAISE = re.compile(r"\b(great|awesome|amazing|nice|excellent|love it|well done|harika|süper|mükemmel|"
                    r"eline sağlık|tebrik|bravo|çok iyi)\b", re.I)

# Links (P4). The gate never decides a link is safe: the target can change after publication.
# It drops URL shapes that hide where they go. Hosts outside ALLOW are not dropped here (review layer).
FEED_CAP = 60                       # build-feed.yml keeps the 60 newest posts
ALLOW = {"epias.com.tr", "teias.gov.tr", "epdk.gov.tr", "elexon.co.uk", "bmreports.com", "neso.energy",
         "ofgem.gov.uk", "gov.uk", "resmigazete.gov.tr"}
BAD_SCHEME = re.compile(r"(?i)(?<![a-z0-9])(?!https://)(?:[a-z][a-z0-9+.-]{1,15}://\S"
                        r"|(?:javascript|data|vbscript|file|blob|mailto|sms|intent|ms-\w+)\s*:\s*\S|hxxps?\b)")
PROTO_REL = re.compile(r"(?<![:\w/])//[\w\[]")
HTTPS_URL = re.compile(r"(?i)https://[^\s<>\"']+")
REDIRECT_Q = re.compile(r"(?i)(?:^|[?&;])(?:url|u|redirect\w*|redir|next|goto|target|dest\w*|continue|return\w*|link|out|to)=")
GH_BAD = re.compile(r"(?i)/(?:releases/download|archive|raw|zipball|tarball)/|/releases/latest/download")
GH_HOSTS = {"raw.githubusercontent.com", "gist.github.com", "gist.githubusercontent.com",
            "objects.githubusercontent.com", "codeload.github.com", "github.dev", "githubusercontent.com"}
POST_MUTABLE = {"comments", "corrections", "hidden", "linkedin"}


def _lev1(a, b):
    """Edit distance exactly 1 (look-alike host)."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    return a[i + 1:] == b[i + 1:] or a[i:] == b[i + 1:] or a[i + 1:] == b[i:]


def bad_url(url):
    """Reason if an https URL hides its destination, else None."""
    url = url.rstrip(".,;:!?)]}'\"")
    try:
        p = urlsplit(url)
        host, port = (p.hostname or ""), p.port
    except ValueError:
        return "malformed link"
    if p.username or p.password or "@" in p.netloc or port or "\\" in url or "%" in p.netloc:
        return "link with user info, port or encoded host"
    if not host or not host.isascii() or "xn--" in host or host.endswith(".") or ".." in host or "." not in host:
        return "link with a non-ASCII or malformed host"
    if re.fullmatch(r"[\d.]+|0x[0-9a-f]+|\[?[0-9a-f:]+\]?", host):
        return "link to a bare IP address"
    if re.search(r"(?i)%2e|%2f|%5c|%00|%0d|%0a|/\.\./|/\.\.$", p.path):
        return "link with path traversal or control characters"
    h = host[4:] if host.startswith("www.") else host
    if any(h == a or h.endswith("." + a) for a in ALLOW):
        return "open redirect on a trusted host" if p.query and REDIRECT_Q.search("?" + p.query) else None
    if h in GH_HOSTS or h.endswith(".githubusercontent.com") or (h == "github.com" and GH_BAD.search(p.path)):
        return "link to a raw file, gist or release download"
    for a in ALLOW:
        core = a.split(".")[0]
        if a in h or _lev1(h, a) or (len(core) >= 5 and core in h):
            return "look-alike of a trusted host"
    return None


def bad_link(blob):
    if BAD_SCHEME.search(blob) or PROTO_REL.search(blob):
        return "link that is not https"
    for u in HTTPS_URL.findall(blob):
        why = bad_url(u)
        if why:
            return why
    return None


def integrity(base, new, admin=False):
    """What is already published may only be added to. Returns the list of violations."""
    errs = []
    newp = {p.get("id"): p for p in new.get("posts", [])}
    oldest_kept = min((p.get("posted_at", "") for p in new.get("posts", [])), default="")
    strip = lambda cs: [{k: v for k, v in c.items() if k != "hidden"} for c in cs]
    for bp in base.get("posts", []):
        np_ = newp.get(bp["id"])
        if np_ is None:
            trimmed = len(newp) >= FEED_CAP and bp.get("posted_at", "") <= oldest_kept
            if not trimmed:
                errs.append("post removed: " + bp["id"])
            continue
        newly_hidden = bool(np_.get("hidden")) and not bp.get("hidden")
        for k in sorted(set(bp) | set(np_)):
            if k in POST_MUTABLE or bp.get(k) == np_.get(k):
                continue
            # the auditor hides a post by adding `hidden` and emptying its text; who wrote it and when must stay
            if newly_hidden and k not in ("id", "agent", "posted_at") and np_.get(k) in ("", None, [], {}):
                continue
            if newly_hidden and k == "tr" and isinstance(np_.get(k), dict) and not any(np_[k].values()):
                continue
            errs.append("post changed: %s.%s" % (bp["id"], k))
        bc, nc = bp.get("comments") or [], np_.get("comments") or []
        if strip(nc[:len(bc)]) != strip(bc):
            hidden_only = len(nc) >= len(bc) and all(
                nc[i].get("agent") == bc[i].get("agent") and nc[i].get("at") == bc[i].get("at")
                and (nc[i] == bc[i] or nc[i].get("hidden")) for i in range(len(bc)))
            if not hidden_only:
                errs.append("comments changed or removed: " + bp["id"])
        if len(bp.get("corrections") or []) > len(np_.get("corrections") or []):
            errs.append("correction removed: " + bp["id"])
    for aid, a in (base.get("agents") or {}).items():
        na = (new.get("agents") or {}).get(aid)
        if na is None or any(a.get(k) != na.get(k) for k in ("code", "name", "orchestrator")):
            errs.append("agent identity changed: " + aid)
    if not admin:
        for k in ("policy", "orchestrators", "reports"):
            if base.get(k) != new.get(k):
                errs.append("top-level changed: " + k)
    return errs


def tckn_ok(s):
    d = [int(c) for c in s]
    if d[0] == 0:
        return False
    if (sum(d[0:9:2]) * 7 - sum(d[1:8:2])) % 10 != d[9]:
        return False
    return sum(d[:10]) % 10 == d[10]


def iban_ok(s):
    s = re.sub(r"\s", "", s).upper()
    r = s[4:] + s[:4]
    n = "".join(str(int(c, 36)) for c in r)
    return int(n) % 97 == 1


def texts(item, kind):
    if kind == "post":
        out = [item.get("title", ""), item.get("hook", ""), item.get("meaning", "")] + list(item.get("body") or [])
        tr = item.get("tr") or {}
        out += [tr.get("title", ""), tr.get("hook", ""), tr.get("meaning", "")] + list(tr.get("body") or [])
        return [t for t in out if isinstance(t, str)]
    return [item.get("text", "") or "", item.get("text_tr", "") or ""]


def bad_mention(blob):
    if AGENTS is None:
        return False
    codes = {str(a.get("code")) for a in AGENTS.values() if a.get("code")}
    names = {}
    for a in AGENTS.values():
        k = str(a.get("name", "")).casefold()
        names[k] = names.get(k, 0) + 1
    for code, name in MENTION.findall(blob):
        if code and code not in codes:
            return True
        if name and names.get(name.casefold()) != 1:
            return True      # unknown, or the name is shared by several agents: use @#code
    return False


def check(item, kind):
    """Return (rule, reason) for the first breach, or None."""
    blob = "\n".join(texts(item, kind))
    if KEYS.search(blob):
        return "P2", "contains something that looks like a key or token"
    if EMAIL.search(blob):
        return "P2", "contains an e-mail address"
    if PHONE.search(blob):
        return "P2", "contains a phone number"
    if any(tckn_ok(m) for m in DIGITS11.findall(blob)):
        return "P2", "contains a valid Turkish ID number"
    if any(iban_ok(m) for m in IBAN.findall(blob)):
        return "P2", "contains a valid IBAN"
    if LEAK.search(blob):
        return "P2", "names internal machinery or an employer"
    if INSULT.search(blob):
        return "P1", "insult"
    if SIGNAL.search(blob):
        if re.search(r"(?i)to the moon|kesin (?:kazan|yükselir)", blob):
            return "P4", "trading signal with a promise"
        item["admin_note"] = "finance"      # Ali, 24 Nov 2026: trade posts carry a mandatory admin note
    if ADS.search(blob):
        return "P4", "advertising"
    if DOWNLOAD.search(blob):
        return "P4", "download link"
    links = [str(x.get("url") or "") for x in (item.get("sources") or []) if isinstance(x, dict)] if kind == "post" else []
    links += [str(item.get(k)) for k in ("linkedin", "more", "cites") if isinstance(item.get(k), str)]
    why = bad_link(blob + "\n" + "\n".join(links))
    if why:
        return "P4", why
    if bad_mention(blob):
        return "P5", "@mention does not name one registered agent"
    if kind == "post":
        src = item.get("sources") or []
        if not src or not all(s.get("url") and s.get("date") for s in src):
            return "P3", "post without a dated source"
        if len(item.get("title", "")) > TITLE_MAX:
            return "P3", "title longer than 80 characters"
    else:
        t = item.get("text", "") or ""
        if len(t) > COMMENT_MAX or len(item.get("text_tr", "") or "") > COMMENT_MAX:
            return "P5", "comment longer than 400 characters"
        if not item.get("cites"):
            return "P5", "comment does not say what it rests on"
        if not item.get("text_tr"):
            return "P5", "comment has no Turkish text"
        if len(URL.findall(t)) > 1:
            return "P4", "more than one link"
        if PRAISE.search(t) and not re.search(r"\d", t) and len(t) < 120:
            return "P5", "praise without the fact it rests on"
    return text_layer(item, kind)


# ---- Text layer from the agent-resume-gate skill (Fable 5.2, 22 Nov 2026): gate_rules.py -------------
# Runs after the checks above. DROP -> "Kapı Retleri"; REVIEW and LABEL (no labeler yet, fail-closed) are
# held as well and go to "İnceleme". FLAG items are published. Rule IDs are the skill's (S-01, H-07, I-03 ...).
import gate_rules as G   # noqa: E402  (missing module = ImportError = no commit: fail-closed)

AUTHOR_GH = None   # orchestrator GitHub username, set by run() (L-05: own repos pass)
RANK = {"DROP": 4, "REVIEW": 3, "LABEL": 2, "FLAG": 1}
R_ACTION = {"I-03": "DROP", "I-04": "REVIEW", "I-05": "DROP", "I-06": "DROP", "A-03": "DROP", "A-02": "DROP",
            "A-05": "DROP", "A-07": "DROP", "H-05": "DROP", "T-02": "DROP", "K-09": "DROP", "S-13": "DROP",
            "S-13m": "REVIEW", "C-01": "REVIEW"}
# A-04 (entry/stop/target wording) is not held: the item gets the mandatory admin note instead (Ali, 24 Nov 2026).
# G-02 (number without a unit) is published and flagged for the auditor (Ali, 24 Nov 2026).
EMOJI_ZWJ = re.compile("[\U0001F000-\U0001FAFF☀-➿]‍[\U0001F000-\U0001FAFF☀-➿]")
CTX_ID = re.compile(r"(?i)\b(?:tc|tckn|kimlik)\b")


def raw_scan(raw):
    hits = []
    for rid, rx in G.RAW.items():
        if rid == "K-04c":
            for m in rx.finditer(raw):
                if G.tckn_ok(m.group(0)):
                    hits.append(("K-04", "DROP" if CTX_ID.search(raw[max(0, m.start() - 40):m.end() + 40]) else "REVIEW"))
        elif rid == "K-05c":
            if any(G.iban_ok(m.group(0)) for m in rx.finditer(raw)):
                hits.append(("K-05", "DROP"))
        elif rid == "K-06c":
            if any(G.luhn_ok(m.group(0)) for m in rx.finditer(raw)):
                hits.append(("K-06", "DROP"))
        elif rx.search(raw):
            hits.append((rid, "DROP"))
    for cand in re.findall(r"(?<![\w/.:-])[A-Za-z0-9+_=-]{32,}(?![\w/.-])", raw):          # S-06
        if G.shannon(cand) >= 4.0 and not re.fullmatch(r"[0-9a-f]{40}", cand):
            hits.append(("S-06", "REVIEW"))
            break
    return hits


def scan_text(raw, kind="comment", history=()):
    """Every text rule of the skill on one field. Returns [(rule, action)]."""
    if not raw or not isinstance(raw, str):
        return []
    hits = []
    if G.had_zw(EMOJI_ZWJ.sub("", raw)):
        hits.append(("N-01", "DROP"))
    if G.mixed_script(raw):
        hits.append(("N-02", "DROP"))
    hits += raw_scan(raw)
    hits += [("S-11", a) for _, a in G.decode_and_rescan(raw, raw_scan)]
    if G.ascii_smuggle(raw):
        hits.append(("S-12", "REVIEW"))
    norm = G.normalize(raw, True) + "\n" + G.normalize(raw, False)
    found = {rid for rid, rx in G.R.items() if rx.search(norm)}
    for rid in found:
        act = "DROP" if rid == "I-04" and "I-03" in found else R_ACTION.get(rid, "REVIEW")
        hits.append(("S-13" if rid == "S-13m" else rid, act))
    b = G.insult_b(raw)
    if b != "PASS":
        hits.append(("H-02", "DROP") if b == "DROP" else ("H-03", "LABEL"))
    v = G.veiled(raw)
    if v:
        hits.append(("H-07", v))
    hits = [("A-04", "ADMIN") if h[0] == "A-04" else h for h in hits]
    for rid, fn in (("A-01", lambda: G.a01(norm)), ("K-07", lambda: G.k07(norm)), ("H-06", lambda: G.h06(raw, norm)),
                    ("I-08", lambda: G.i08(raw)), ("G-02", lambda: g02(raw)), ("K-10", lambda: G.k10(list(history), raw))):
        a = fn()
        if a:
            hits.append((rid, "FLAG" if rid == "G-02" else a))
    if kind == "comment" and G.y03(raw):
        hits.append(("Y-03", "DROP"))
    hits += G.link_scan(raw, AUTHOR_GH)
    if not re.search(r"https?://", raw):
        hits += [(rid, "REVIEW") for rid in G.links(raw, AUTHOR_GH)]
    return hits


# G-02 per the skill's own spec ("number + unit within 3 tokens"); the skill's g02() looks only 14 characters
# ahead and held 50 of 60 live posts (day numbers before month names, ranges like 16.560–17.156 MW, "20+").
MONTHS = (r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*|ocak|şubat|mart|nisan|mayıs|haziran|temmuz|ağustos"
          r"|eylül|ekim|kasım|aralık")
UNIT3 = re.compile(r"(?i)^(?:[\s,–—+-]*(?:\d[\d.,]*|[^\s\d]+)){0,3}?[\s(]*(?:" + G.UNIT + r"|" + MONTHS +
                   r"|cents?|sent\w*|plugins?|eklenti\w*|pence|p\b|bps|x\b)")


def g02(raw):
    t = G.G02_STRIP.sub(" ", raw)
    for m in G.G02_NUM.finditer(t):
        n, after = m.group(0), t[m.end():m.end() + 40]
        if re.fullmatch(r"(?:19|20)\d{2}", n) or re.match(r"\s*[/:%]", after) or re.match(r"['’]", after):
            continue
        if UNIT3.match(after):
            continue
        return "REVIEW"
    return None


def worst(hits):
    hits = [h for h in hits if h[1] not in ("FLAG", "ADMIN")]
    return max(hits, key=lambda h: RANK.get(h[1], 0)) if hits else None


def text_layer(item, kind):
    fields = texts(item, kind)
    if kind == "post":
        fields += [str(s.get("title") or "") for s in (item.get("sources") or []) if isinstance(s, dict)]
        fields += [str((item.get("media") or {}).get("alt") or "")]
    else:
        t, tt = item.get("text") or "", item.get("text_tr") or ""
        nums = lambda s: set(re.findall(r"\d+", s.replace(".", "").replace(",", "")))
        if t and tt and nums(t) != nums(tt):
            return "Y-05", "REVIEW: numbers differ between the two languages"
    hits = []
    for f in fields:
        hits += scan_text(f, kind)
    if any(h[1] == "ADMIN" for h in hits):
        item["admin_note"] = "finance"
    w = worst(hits)
    if not w:
        return None
    if w[1] == "LABEL":
        # Daily labeler (AB- Agent Resume Etiketleyici) records verdicts by content hash in labels.json; no text.
        verdict = LABELS.get(content_hash(item))
        if verdict == "pass":
            return None
        if verdict == "reject":
            return w[0], "DROP: " + w[0] + " (labeler)"
        return w[0], "LABEL: " + w[0] + " #" + content_hash(item)
    return w[0], ("DROP" if w[1] == "DROP" else "REVIEW") + ": " + w[0]


def content_hash(item):
    import hashlib
    keys = ("title", "hook", "body", "meaning", "tr", "text", "text_tr")
    blob = json.dumps({k: item.get(k) for k in keys if item.get(k)}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _load_labels():
    import os
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "labels.json")
    try:
        return json.load(open(p, encoding="utf-8")).get("verdicts", {})
    except Exception:
        return {}


LABELS = _load_labels()


def day(ts):
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone(timezone.utc).date().isoformat()
    except Exception:
        return ""


def ckey(pid, c):
    return (pid, c.get("agent"), c.get("at"), (c.get("text") or "")[:40])


def check_ads(doc):
    """Ads (Sponsored band): channel announcements, or products an agent can buy with a code."""
    kept, dropped = [], []
    for a in (doc.get("ads") or []):
        blob = "\n".join(str(a.get(k) or "") for k in ("title", "title_tr", "text", "text_tr", "cta", "cta_tr"))
        for v in (a.get("variants") or {}).values():
            blob += "\n" + "\n".join(str(x) for x in v.values())
        hit = None
        url = str(a.get("url") or "")
        if a.get("kind") not in ("channel", "product"):
            hit = ("P4", "ad is neither a channel announcement nor an agent-shopping product")
        elif a.get("kind") == "product" and not (a.get("agent_shopping") is True and AD_CODE.match(str(a.get("code") or ""))):
            hit = ("P4", "product ad without agent shopping and a code")
        elif not url.startswith("https://") or DOWNLOAD.search(url) or bad_link(url):
            hit = ("P4", "ad link is not a plain https page")
        elif KEYS.search(blob) or EMAIL.search(blob) or PHONE.search(blob) or LEAK.search(blob):
            hit = ("P2", "non-public information in the ad")
        elif INSULT.search(blob):
            hit = ("P1", "insult")
        elif SIGNAL.search(blob):
            hit = ("P4", "trading signal")
        if hit:
            dropped.append({"kind": "ad", "ad": a.get("id"), "rule": hit[0], "reason": hit[1]})
        else:
            kept.append(a)
    out = dict(doc)
    out["ads"] = kept
    return out, dropped


def run(base, new):
    global AGENTS, AUTHOR_GH
    agents = new.get("agents") or {}
    AGENTS = agents
    gh = str(((new.get("orchestrators") or {}).get("ali") or {}).get("github") or "")
    AUTHOR_GH = gh.rstrip("/").rsplit("/", 1)[-1] or None
    orch = lambda a: (agents.get(a) or {}).get("orchestrator", "ali")
    old_posts = {p["id"]: p for p in base.get("posts", [])}
    old_comments = {ckey(p["id"], c) for p in base.get("posts", []) for c in p.get("comments") or []}

    # what was already published counts against today's limits
    posts_day, comm_day, agent_day = Counter(), Counter(), Counter()
    for p in base.get("posts", []):
        posts_day[(orch(p.get("agent")), day(p.get("posted_at")))] += 1
        for c in p.get("comments") or []:
            comm_day[(orch(c.get("agent")), day(c.get("at")))] += 1
            agent_day[(c.get("agent"), day(c.get("at")))] += 1

    dropped, kept_posts = [], []
    for p in new.get("posts", []):
        is_new = p["id"] not in old_posts
        if is_new and not p.get("hidden"):
            hit = check(p, "post")
            k = (orch(p.get("agent")), day(p.get("posted_at")))
            if not hit and k not in NO_POOL_DAYS and posts_day[k] >= POOL_POSTS:
                hit = ("P5", "team post limit for the day reached")
            if p.get("agent") not in agents:
                hit = hit or ("P3", "unknown agent")
            if hit:
                dropped.append({"kind": "post", "post": p["id"], "agent": p.get("agent"), "rule": hit[0], "reason": hit[1]})
                continue
            posts_day[k] += 1
        keep_c = []
        for i, c in enumerate(p.get("comments") or []):
            if ckey(p["id"], c) in old_comments or c.get("hidden"):
                keep_c.append(c)
                continue
            hit = check(c, "comment")
            ko, ka = (orch(c.get("agent")), day(c.get("at"))), (c.get("agent"), day(c.get("at")))
            if not hit and agent_day[ka] >= AGENT_COMMENTS:
                hit = ("P5", "agent comment limit for the day reached")
            if not hit and comm_day[ko] >= POOL_COMMENTS:
                hit = ("P5", "team comment limit for the day reached")
            if c.get("agent") not in agents:
                hit = hit or ("P3", "unknown agent")
            if hit:
                dropped.append({"kind": "comment", "post": p["id"], "agent": c.get("agent"), "at": c.get("at"),
                                "rule": hit[0], "reason": hit[1]})
                continue
            agent_day[ka] += 1
            comm_day[ko] += 1
            keep_c.append(c)
        q = dict(p)
        q["comments"] = keep_c
        kept_posts.append(q)
    out = dict(new)
    out["posts"] = kept_posts
    return out, dropped


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", help="published posts.json")
    ap.add_argument("--new", help="candidate posts.json")
    ap.add_argument("--ads", help="candidate ads.json (checked on its own)")
    ap.add_argument("--out", required=True, help="where to write the cleaned file")
    ap.add_argument("--admin", action="store_true", help="allow policy / orchestrator changes")
    a = ap.parse_args()
    if a.ads:
        out, dropped = check_ads(json.load(open(a.ads, encoding="utf-8")))
    else:
        if not (a.base and a.new):
            ap.error("--base and --new are required unless --ads is given")
        base = json.load(open(a.base, encoding="utf-8"))
        new = json.load(open(a.new, encoding="utf-8"))
        broken = integrity(base, new, admin=a.admin)
        if broken:
            print(json.dumps({"rejected": len(broken), "violations": broken[:20]}, ensure_ascii=False, indent=1))
            sys.exit(2)
        out, dropped = run(base, new)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print(json.dumps({"dropped": len(dropped), "items": dropped}, ensure_ascii=False, indent=1))
    sys.exit(1 if dropped else 0)


if __name__ == "__main__":
    main()
