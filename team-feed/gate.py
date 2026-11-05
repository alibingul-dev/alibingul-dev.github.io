"""Publishing gate for the AI Team Feed: public work only, no routine status lines.

Usage:
  python3 gate.py build < payload.json      print one thread (JSON list) for team-feed/feed.json
  python3 gate.py scan  FILE...             list leaks; exit 1 if any
  python3 gate.py redact FILE...            rewrite FILEs with leaks removed; exit 1 if anything changed

build payload (written by the GB wind outlook runner after the editor's PASS):
  {"rounds": [{"time": "05:31", "fail": "<FAIL line text>"}, ...],   # sent-back rounds, in order
   "readers": [{"read": "<R line 1>", "stop": "<R line 5>"}, ...],    # approved round's readers
   "approved_time": "05:40", "figures": 28, "mismatches": 0}

Rules (Ali, 4 Nov 2026): prompts, rule codes, task or chat ids, employer work and routine
status updates ("first draft submitted", "resubmitted", "posted") never go in.
Rules (Ali, 5 Nov 2026): agents' conversations with each other stay off the feed. Editor
rounds, reader-panel checks, approvals, missed-run and checker notes are internal; the run
record lives in status/status.json (Live Work Status). A thread may carry only the events in
PUBLIC_EVENTS (an agent's own note on its published post). build() therefore returns an
empty thread, and redact() drops every other event at write time.
"""
import json
import re
import sys

# Anything that names the machinery behind the posts rather than the work itself.
LEAK = re.compile(
    r"chat [0-9a-f]{8}-[0-9a-f-]{27}|\btrig_\w+|\bsession_\w+|\bcse_\w+|\bjob trig"
    r"|\bdecision \d+|\ballowed count|\bpost count|\bpanel ruling|\bexemption\b"
    r"|\b(?:tr|gb)_post\d\w*|\bpost[12]\b|\bwriter\.md|\beditor\.md|\breader\.md"
    r"|\bprompt\b|\btodoist\b|\bborusan\b|\benbw\b|\bsantral\b|⚙️|⚙",
    re.I)
CODE_PREFIX = re.compile(r"^\s*[a-h]\s*·\s*", re.I)        # "b · ", "e · " rule letters
PAREN_REF = re.compile(r"\s*\((?:decision|rule)[^)]*\)", re.I)
FILLER = re.compile(r"^(first draft\b|reworked the line\b|.*\bresubmitted\.?$|.*submitted for review\.?$|posted to linkedin\b)", re.I)
NEUTRAL = "Sent back for revision."
PUBLIC_EVENTS = {"agent_note"}   # 5 Nov 2026: nothing from internal review reaches the feed


def clean_reason(text):
    """An editor's catch in plain words, or the neutral line when it cannot be said publicly."""
    t = CODE_PREFIX.sub("", str(text or "")).strip()
    t = PAREN_REF.sub("", t).replace("⚙️", "").replace("⚙", "")
    t = re.sub(r"\s+", " ", t).strip(" ·")
    if not t or LEAK.search(t):
        return NEUTRAL
    return t[0].upper() + t[1:]


def short_reason(stop):
    """'Yes, too much jargon and figures.' -> 'too much jargon and figures'"""
    s = re.sub(r"^(yes|no)\b[\s,:.;-]*(i'?d stop[:,]?\s*)?", "", str(stop or ""), flags=re.I).strip(" .")
    return s[:1].lower() + s[1:] if s else ""


def build(p):
    """Internal review (editor rounds, readers, approval) is not published since 5 Nov 2026."""
    return []


def build_internal(p):
    """The review thread as it was published until 5 Nov 2026. Not called; kept for reference."""
    out = []
    for i, r in enumerate(p.get("rounds") or [], 1):
        out.append({"event": "sent_back", "agent": "AI Senior Editor", "initials": "SE",
                    "role": "round %d · sent back · %s UK" % (i, r.get("time", "")),
                    "text": clean_reason(r.get("fail"))})
    rd = [r for r in (p.get("readers") or []) if r.get("read")]
    if rd:
        stops = [r for r in rd if re.match(r"\s*yes", str(r.get("stop", "")), re.I)]
        read = clean_reason(rd[0]["read"])
        line = "Read it as: " + read.rstrip(".") + "."
        if stops:
            line += " %d of %d would scroll past: %s." % (len(stops), len(rd), short_reason(stops[0]["stop"]) or "too dense")
        else:
            line += " All %d would keep reading." % len(rd)
        out.append({"event": "readers", "agent": "AI Reader Panel", "initials": "RP",
                    "role": "%d readers" % len(rd), "text": line if not LEAK.search(line) else "Readers checked the post before approval."})
    n = len(p.get("rounds") or []) + 1
    out.append({"event": "approved", "agent": "AI Senior Editor", "initials": "SE",
                "role": "round %d · approved · %s UK" % (n, p.get("approved_time", "")),
                "text": "%s figures re-checked against the source, %s mismatches. Approved." % (p.get("figures", "?"), p.get("mismatches", "?"))})
    return out


def walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, path + "/" + str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, "%s[%d]" % (path, i))
    elif isinstance(obj, str):
        yield path, obj


def scan(obj):
    return [(p, s) for p, s in walk(obj) if LEAK.search(s) and not p.endswith("/about")]


def redact(obj):
    """Fail closed: a leaking status field is emptied; a leaking feed comment is reduced to a public form."""
    if isinstance(obj, dict):
        if "threads" in obj:
            for key, th in obj["threads"].items():
                kept = []
                for c in th:
                    if not isinstance(c, dict) or FILLER.match(str(c.get("text", ""))):
                        continue
                    if c.get("event") not in PUBLIC_EVENTS:
                        continue
                    c = dict(c)
                    if LEAK.search(str(c.get("text", ""))):
                        c["text"] = NEUTRAL if "sent back" in str(c.get("role", "")) else ""
                    if LEAK.search(str(c.get("role", ""))):
                        c["role"] = ""
                    if c.get("text"):
                        kept.append(c)
                obj["threads"][key] = kept
            return obj
        return {k: (None if isinstance(v, str) and LEAK.search(v) else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj


def main():
    cmd, files = sys.argv[1], sys.argv[2:]
    if cmd == "build":
        print(json.dumps(build(json.load(sys.stdin)), ensure_ascii=False, indent=2))
        return 0
    bad = 0
    for f in files:
        data = json.load(open(f, encoding="utf-8"))
        leaks = scan(data)
        if cmd == "redact" and "threads" in data:
            before = json.dumps(data, ensure_ascii=False, sort_keys=True)
            data = redact(data)
            changed = json.dumps(data, ensure_ascii=False, sort_keys=True) != before
        elif cmd == "redact":
            data = redact(data) if leaks else data
            changed = bool(leaks)
        else:
            changed = False
        for p, s in leaks:
            print("LEAK %s %s: %s" % (f, p, s[:120]))
        if cmd == "redact" and changed:
            with open(f, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=1)
                fh.write("\n")
            print("REDACTED", f)
        bad += 1 if (leaks or changed) else 0
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
