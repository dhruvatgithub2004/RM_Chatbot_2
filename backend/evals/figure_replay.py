"""Replay the real model answers in the audit log through the figure check. (Improvement 02.) Offline: no model calls.

    cd backend
    python -m evals.figure_replay

For every chat the model answered, rebuilds the context the answer is checked against and runs the current rules. Prints each answer
the rules would now block, with the figures they object to, so a person can judge whether each block is a real error or a false alarm.
Answers that were already blocked at the time are not in `mode == llm`, so they are not replayed.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config, copilot, guard_rules as g  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.readers import ClientReader, PortfolioReader  # noqa: E402

n = blocked = 0
with SessionLocal() as s:
    reader = PortfolioReader(s)
    rows, directory = reader.portfolio_rows(), reader.directory_names()
    for line in open(config.AUDIT_LOG_PATH, encoding="utf-8"):
        d = json.loads(line)
        if d.get("event") != "chat" or d.get("mode") != "llm":
            continue
        q, answer = d["question"], d["reply"]
        if d["scope"] == "portfolio":
            p = copilot.portfolio_prompt(reader, [{"role": "user", "text": q}])
            ctx = copilot._portfolio_grounding(rows, p["facts"] + "\n" + p["kb"])
        else:
            rd = ClientReader(s, d["merchant_id"])
            detail = rd.detail()
            p = copilot.merchant_prompt(rd, [{"role": "user", "text": q}])
            me = g.ClientFacts(d["merchant_id"], detail["name"], detail["profile"]["risk_segment"], False, False,
                               tuple(detail["profile"]["existing_products"]), None)
            ctx = g.GroundingContext("client", [me], directory, d["merchant_id"], p["data"] + "\n" + p["kb"])
        n += 1
        found = [v for v in g.check_answer(q, answer, ctx) if v.hard and v.rule == "ungrounded_number"]
        if found:
            blocked += 1
            print(f"\n[{d['scope']}] {q}\n  objects to: {[str(v) for v in found][:5]}\n  answer: {answer[:300]!r}")
print(f"\nmodel answers replayed: {n} | would now be blocked on a figure: {blocked}")
