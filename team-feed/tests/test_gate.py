#!/usr/bin/env python3
"""Run the agent-resume-gate corpus against policy_gate.scan_text.

PASS rows must produce no DROP/REVIEW/LABEL (zero false alarms is the hard requirement).
Violation rows are scored only when their rule is implemented in the text layer; labeler,
behaviour and structural rules are listed as not covered.
    python3 tests/test_gate.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import policy_gate as pg  # noqa: E402
pg.AUTHOR_GH = "alibingul-dev"

NOT_TEXT = {"G-01", "G-03", "G-06", "L-07", "B-05", "B-06", "B-07", "B-08", "B-09", "K-10", "S-07", "I-09", "C-02", "C-03",
            "T-01", "G-04", "Y-01", "Y-02", "Y-04", "Y-05", "C-04", "H-04"}
here = os.path.dirname(__file__)
rows = [json.loads(l) for l in open(os.path.join(here, "gate_corpus.jsonl"), encoding="utf-8") if l.strip()]
fa, ok, miss, skip = [], 0, [], []
for r in rows:
    t = r["text"].replace("<ZWSP>", "​")
    hits = pg.scan_text(t, "comment")
    w = pg.worst(hits)
    got = "PASS" if not w else ("REVIEW" if w[1] == "LABEL" else w[1])
    if r["expect"] == "PASS":
        if got != "PASS":
            fa.append((r["rule"], got, w[0], t[:70]))
        else:
            ok += 1
    elif r["rule"] in NOT_TEXT and got == "PASS":
        skip.append(r["rule"])
    elif got == "PASS" or (r["expect"] == "DROP" and got != "DROP"):
        miss.append((r["rule"], r["expect"], got, w and w[0], t[:70]))
    else:
        ok += 1
n_pass = sum(r["expect"] == "PASS" for r in rows)
print(f"rows {len(rows)} | PASS rows {n_pass}, false alarms {len(fa)} | caught or correct {ok} | missed {len(miss)} | not text-layer {len(skip)}")
for x in fa:
    print("FALSE ALARM", x)
for x in miss:
    print("MISSED", x)
print("not covered by text layer:", sorted(set(skip)))
sys.exit(1 if fa else 0)
