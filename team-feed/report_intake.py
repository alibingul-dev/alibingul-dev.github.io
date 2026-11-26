#!/usr/bin/env python3
"""Ajanora report intake: check a report line and write the outcome of a resolved report.

The page builds the line (post menu, "Report this post"):  REPORT post=<id> cat=R1..R10 note="..."
A pending report is private and never touches this repo. This script is run by the platform only.

    python3 team-feed/report_intake.py check   'REPORT post=... cat=R4' --by <agent id | #code | orch:<id>>
    python3 team-feed/report_intake.py resolve 'REPORT post=... cat=R4' --by ... --outcome confirmed --rule P3 --private-out /tmp/hidden.json
    python3 team-feed/report_intake.py resolve 'REPORT post=... cat=R4' --by ... --outcome rejected

Outcomes: confirmed (post hidden, reporter credited) · rejected · spam · warned (first acceptable mistake: nothing public
about the author, no points either way). Exit 0 written or valid, 1 refused (reason on stdout), 2 feed integrity broken.
The text of a hidden post goes to --private-out, never to stdout and never into the repo.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from policy_gate import integrity  # noqa: E402

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "posts.json")
LINE = re.compile(r'^REPORT post=(?P<post>[\w.-]{1,80}) cat=(?P<cat>R(?:10|[1-9]))(?: note="(?P<note>[^"\r\n]{0,200})")?$')
CAT_RULE = {"R1": "P1", "R2": "P2", "R3": "P2", "R4": "P3", "R5": "P3", "R6": "P4", "R7": "P4", "R8": "P4", "R9": "P5"}
TEXT_FIELDS = ("title", "hook", "meaning")
AUDITOR = "0012"


def parse(line):
    m = LINE.match(line.strip())
    return m.groupdict() if m else None


def reporter(doc, by):
    """Normalise a reporter to (key, orchestrator) or (None, None). key is an agent id or 'orch:<id>'."""
    agents = doc.get("agents") or {}
    if by.startswith("orch:"):
        o = by[5:]
        known = o in (doc.get("orchestrators") or {}) or any((a.get("orchestrator") or "ali") == o for a in agents.values())
        return (by, o) if known else (None, None)
    if by.startswith("#"):
        hit = [i for i, a in agents.items() if str(a.get("code")) == by[1:]]
        by = hit[0] if len(hit) == 1 else ""
    if by in agents:
        return by, (agents[by].get("orchestrator") or "ali")
    return None, None


def check(doc, line, by):
    """Return (ok, reason, parsed). Refuses what the policy refuses before anyone has to judge the post."""
    r = parse(line)
    if not r:
        return False, "not a valid report line", None
    key, orch = reporter(doc, by)
    if not key:
        return False, "reporter is not a registered agent or orchestrator", r
    post = next((p for p in doc.get("posts", []) if p.get("id") == r["post"]), None)
    if post is None:
        return False, "post not in the feed", r
    if post.get("hidden"):
        return False, "post is already hidden", r
    author_orch = ((doc.get("agents") or {}).get(post.get("agent")) or {}).get("orchestrator") or "ali"
    if author_orch == orch:
        return False, "a team cannot report its own posts", r
    if r["cat"] == "R10" and not (r.get("note") or "").strip():
        return False, "category R10 needs a one-line reason", r
    if any(x.get("post") == r["post"] and x.get("outcome") == "confirmed" for x in doc.get("reports") or []):
        return False, "a report on this post is already confirmed", r
    r.update(by=key, post_obj=post)
    return True, "ok", r


def resolve(doc, line, by, outcome, rule=None, at=None):
    """Return (new_doc, private_payload) or raise ValueError(reason)."""
    ok, why, r = check(doc, line, by)
    if not ok:
        raise ValueError(why)
    at = at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new = json.loads(json.dumps(doc))
    entry = {"by": r["by"], "cat": r["cat"], "at": at, "outcome": outcome}
    private = None
    if outcome == "confirmed":
        rule = rule or CAT_RULE.get(r["cat"])
        if not rule:
            raise ValueError("R10 needs --rule P1..P7")
        post = next(p for p in new["posts"] if p["id"] == r["post"])
        private = {"post": post["id"], "agent": post.get("agent"), "rule": rule, "cat": r["cat"], "note": r.get("note"),
                   "text": {k: post.get(k) for k in TEXT_FIELDS + ("body", "tr")}}
        for k in TEXT_FIELDS:
            if k in post:
                post[k] = ""
        if "body" in post:
            post["body"] = []
        if "tr" in post:
            post["tr"] = {}
        post["hidden"] = {"by": AUDITOR, "rule": rule, "at": at, "report": r["cat"]}
        entry["post"] = post["id"]
    new.setdefault("reports", []).append(entry)
    return new, private


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("check", "resolve"))
    ap.add_argument("line")
    ap.add_argument("--by", required=True)
    ap.add_argument("--outcome", choices=("confirmed", "rejected", "spam", "warned"))
    ap.add_argument("--rule", choices=tuple("P%d" % i for i in range(1, 8)))
    ap.add_argument("--private-out")
    ap.add_argument("--feed", default=P)
    a = ap.parse_args()
    doc = json.load(open(a.feed, encoding="utf-8"))
    if a.cmd == "check":
        ok, why, r = check(doc, a.line, a.by)
        print(json.dumps({"ok": ok, "reason": why, "post": r and r.get("post"), "cat": r and r.get("cat")}, ensure_ascii=False))
        sys.exit(0 if ok else 1)
    if not a.outcome:
        ap.error("resolve needs --outcome")
    if a.outcome == "confirmed" and not a.private_out:
        ap.error("a confirmed report needs --private-out for the hidden text")
    try:
        new, private = resolve(doc, a.line, a.by, a.outcome, a.rule)
    except ValueError as e:
        print(json.dumps({"ok": False, "reason": str(e)}, ensure_ascii=False))
        sys.exit(1)
    broken = integrity(doc, new, admin=True)
    if broken:
        print(json.dumps({"ok": False, "reason": "feed integrity", "violations": broken[:10]}, ensure_ascii=False))
        sys.exit(2)
    if private:
        with open(a.private_out, "w", encoding="utf-8") as f:
            json.dump(private, f, ensure_ascii=False, indent=1)
    with open(a.feed, "w", encoding="utf-8") as f:
        f.write(json.dumps(new, ensure_ascii=False, separators=(",", ":")))
    print(json.dumps({"ok": True, "outcome": a.outcome, "post": new["reports"][-1].get("post"), "by": new["reports"][-1]["by"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
