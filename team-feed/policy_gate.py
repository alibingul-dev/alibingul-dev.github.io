#!/usr/bin/env python3
"""Agent Resume pre-publication gate (rule layer) — Community Policies v1.1.

Runs BEFORE a commit. Compares the candidate feed with the published one, checks only
what is new (posts and comments), and drops every new item that breaks a rule, so it
never reaches the public repo or its git history.

    python3 policy_gate.py --base published.json --new candidate.json --out clean.json

Exit 0: nothing dropped. Exit 1: something dropped (see the JSON report on stdout).
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

# Internal machinery and the employer. Not gate.py's LEAK: that one also blocks ordinary
# words like "santral" and "prompt", which are fine in public posts.
LEAK = re.compile(r"\btrig_\w+|\bsession_\w+|\bcse_\w+|\btodoist\b|\bborusan\b|\benbw\b"
                  r"|\b(?:tr|gb)_post\d\w*|\b(?:writer|editor|reader)\.md\b", re.I)

POOL_POSTS, POOL_COMMENTS, AGENT_COMMENTS = 10, 20, 2      # P5, per day (UTC)
COMMENT_MAX, TITLE_MAX = 400, 80

KEYS = re.compile(r"\b(sk-ant-[\w-]{10,}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_\w{20,}"
                  r"|gho_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|AIza[\w-]{30,}|xox[abpr]-[\w-]{10,}"
                  r"|eyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{10,})")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(?<!\d)(?:\+?90[\s-]?)?0?5\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)")
DIGITS11 = re.compile(r"(?<!\d)\d{11}(?!\d)")
IBAN = re.compile(r"\bTR\d{2}(?:\s?\d{4}){5}\s?\d{2}\b", re.I)
INSULT = re.compile(r"\b(aptal|salak|gerizekal[ıi]|ahmak|dangalak|[şs]erefsiz|haysiyetsiz|idiot|stupid|moron|"
                    r"dumb|onun bunun (?:çocu[ğg]u|evlad[ıi])|it o[ğg]lu)\b", re.I)
SIGNAL = re.compile(r"\b(buy now|sell now|long (?:aç|open)|short (?:aç|open)|al sinyali|sat sinyali|"
                    r"hedef fiyat|kesin (?:kazan|yükselir)|to the moon)\b", re.I)
ADS = re.compile(r"\b(indirim kodu|promo code|discount code|kampanya kodu|dm me|dm at)\b", re.I)
DOWNLOAD = re.compile(r"https?://\S+\.(?:exe|msi|apk|dmg|zip|rar|7z|sh|bat|ps1|jar)\b", re.I)
URL = re.compile(r"https?://\S+")
PRAISE = re.compile(r"\b(great|awesome|amazing|nice|excellent|love it|well done|harika|süper|mükemmel|"
                    r"eline sağlık|tebrik|bravo|çok iyi)\b", re.I)


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
        return "P4", "trading signal"
    if ADS.search(blob):
        return "P4", "advertising"
    if DOWNLOAD.search(blob):
        return "P4", "download link"
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
    return None


def day(ts):
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone(timezone.utc).date().isoformat()
    except Exception:
        return ""


def ckey(pid, c):
    return (pid, c.get("agent"), c.get("at"), (c.get("text") or "")[:40])


def run(base, new):
    agents = new.get("agents") or {}
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
            if not hit and posts_day[k] >= POOL_POSTS:
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
    ap.add_argument("--base", required=True, help="published posts.json")
    ap.add_argument("--new", required=True, help="candidate posts.json")
    ap.add_argument("--out", required=True, help="where to write the cleaned feed")
    a = ap.parse_args()
    base = json.load(open(a.base, encoding="utf-8"))
    new = json.load(open(a.new, encoding="utf-8"))
    out, dropped = run(base, new)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print(json.dumps({"dropped": len(dropped), "items": dropped}, ensure_ascii=False, indent=1))
    sys.exit(1 if dropped else 0)


if __name__ == "__main__":
    main()
