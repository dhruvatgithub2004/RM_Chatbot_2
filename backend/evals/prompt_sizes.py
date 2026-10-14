"""How big is each prompt, and does it fit the model's window? (Improvement 01.) Offline: no model calls.

    cd backend
    python -m evals.prompt_sizes

Prints the estimated token size of the portfolio prompt for a set of typical questions and the merchant prompt across every client,
against the limit (window less the reply and a safety margin). The estimate uses the characters-per-token ratios measured on
qwen3:8b (app/prompt_budget.py); in 19 live calls it ran 2% to 34% above the count the model server reported, never below.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import copilot, prompt_budget as pb  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.readers import ClientReader, PortfolioReader  # noqa: E402

QUESTIONS = ["Portfolio summary", "Lending opportunities?", "Which clients are flagged?", "Cross-sell candidates?", "What are the package fees?",
             "Which clients have the highest balance?", "Which clients have a recommended rate change?", "Who is dormant?", "Who should I pitch first?",
             "Which products does the bank offer?", "Which clients in Dubai have a lending pitch?", "Tell me about Miller Technologies",
             "What are the loan terms for a Small Business Loan?", "Which clients are dormant and high risk?", "Which clients have declining volume?"]
FOLLOW_UP = [{"role": "user", "content": "x" * 300}, {"role": "assistant", "content": "y" * 1400}, {"role": "user", "content": "Next question?"}]

with SessionLocal() as s:
    reader = PortfolioReader(s)
    limit = pb.prompt_limit()
    print(f"window {pb.config.PROMPT_TOKENS} tokens | reply reserve {pb.config.LLM_MAX_TOKENS} | prompt limit {limit} tokens\n")
    print(f"{'portfolio question':56} {'est tokens':>10}  {'clients listed':>14}")
    for q in QUESTIONS:
        m = [{"role": "user", "text": q}]
        p = copilot.portfolio_prompt(reader, m)
        listed = p["system"].split("listed=")[1].split(" ")[0]
        print(f"{q:56} {pb.estimate(p['system'], copilot._history(m)):>10}  {listed:>14}")
    old = pb.data_tokens(copilot.portfolio_context(reader, reader.portfolio_rows(), None))
    print(f"\nfor comparison, every client with every field (the old prompt's data alone): about {old} tokens ({'over' if old > limit else 'under'} the limit)\n")
    for label, q in [("knowledge: core only", "Summarize this client"), ("knowledge: + packages", "What are the package fees?"),
                     ("knowledge: + packages + loans", "What are the package fees and loan terms?")]:
        sizes = [pb.estimate(copilot.merchant_prompt(ClientReader(s, mid), [{"role": "user", "text": q}])["system"], []) for mid, _ in reader.directory_names()]
        worst = max(sizes) + sum(pb.prose_tokens(h["content"]) for h in FOLLOW_UP)
        print(f"merchant chat, {label:30} first turn: median {sorted(sizes)[len(sizes) // 2]:5}, max {max(sizes):5} | with a follow-up turn, max {worst:5} "
              f"({'fits' if worst <= limit else 'OVER'})")
