"""Time the real model on the real prompts. (Improvement 01.) Needs the local model running (backend/run_ollama.ps1).

    cd backend
    python -m evals.latency_probe

For each question it builds the portfolio prompt exactly as the app does, sends it to the local model with the app's settings, and
prints what the model server reports: tokens processed, seconds to read the prompt, tokens written, seconds to write them, and the
wall time. If tokens processed is far below the prompt's estimated size, the server cut the prompt (see app/prompt_budget.py).
"""
import json
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config, copilot, prompt_budget as pb  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.readers import PortfolioReader  # noqa: E402

QUESTIONS = ["Portfolio summary", "Lending opportunities?", "What are the package fees?", "Which clients are flagged?", "Which clients have the highest balance?"]

with SessionLocal() as s:
    reader = PortfolioReader(s)
    print(f"{'question':42} {'est':>5} {'read':>5} {'read s':>7} {'wrote':>6} {'write s':>8} {'wall s':>7}")
    for q in QUESTIONS:
        m = [{"role": "user", "text": q}]
        system = copilot.portfolio_prompt(reader, m)["system"]
        payload = {"model": config.LLM_MODEL, "stream": False, "think": False, "keep_alive": config.OLLAMA_KEEP_ALIVE,
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": q}],
                   "options": {"num_predict": config.LLM_MAX_TOKENS, "num_ctx": config.OLLAMA_NUM_CTX, "temperature": 0.2}}
        t0 = time.time()
        res = json.load(urlopen(Request(config.OLLAMA_BASE_URL + "/api/chat", data=json.dumps(payload).encode(),
                                        headers={"Content-Type": "application/json"}), timeout=600))
        print(f"{q:42} {pb.estimate(system, []):>5} {res.get('prompt_eval_count', 0):>5} {res.get('prompt_eval_duration', 0) / 1e9:>7.1f} "
              f"{res.get('eval_count', 0):>6} {res.get('eval_duration', 0) / 1e9:>8.1f} {time.time() - t0:>7.1f}")
