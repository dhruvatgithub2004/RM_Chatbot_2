"""Improvement 01: the prompt is built to fit the model's context window.

Background (measured on qwen3:8b through Ollama, see md_files/improvements/01_context_fit_and_latency.md): a prompt over the window
is silently cut at the START, so the model loses its rules and invents the missing facts. These tests keep every prompt inside the
window, keep the rules at the head, and check the views list the right clients. Offline: the model is never called.
"""
import pytest

from app import audit, config, copilot, knowledge, models as m, prompt_budget as pb
from app.db import SessionLocal
from app.guard_rules import GroundingContext
from app.readers import ClientReader, PortfolioReader

QUESTIONS = ["Portfolio summary", "Lending opportunities?", "Which clients are flagged?", "Cross-sell candidates?", "What are the package fees?",
             "Which clients have the highest balance?", "Which clients have a recommended rate change?", "Who is dormant?",
             "Who should I pitch first?", "Which products does the bank offer?", "Which clients in Dubai have a lending pitch?",
             "What are the loan terms for a Small Business Loan?", "Which clients are dormant and high risk?", "Which clients have declining volume?"]


@pytest.fixture(scope="module")
def reader():
    with SessionLocal() as s:
        yield PortfolioReader(s)


def msgs(q):
    return [{"role": "user", "text": q}]


def head_of(system):
    return system.split("=== ")[0]


# ── the portfolio chat ──────────────────────────────────────────────────────
def test_every_portfolio_prompt_fits_the_window_with_the_rules_at_the_head(reader):
    for q in QUESTIONS:
        system = copilot.portfolio_prompt(reader, msgs(q))["system"]
        assert pb.estimate(system, copilot._history(msgs(q))) <= pb.prompt_limit(), q
        assert system.startswith(("You are the RM Co-pilot", "Answer the RM using only")), q


def test_the_old_full_dump_did_not_fit_and_the_new_prompt_is_a_fraction_of_it(reader):
    rows = reader.portfolio_rows()
    old = "x" * len(copilot.portfolio_context(reader, rows, None))                 # every client, every field: what used to be sent
    assert pb.data_tokens(old) > pb.prompt_limit()
    new = copilot.portfolio_prompt(reader, msgs("Portfolio summary"))["system"]
    assert pb.estimate(new, []) < pb.data_tokens(old) / 5


def test_header_counts_cover_all_clients_whatever_is_listed(reader):
    rows = reader.portfolio_rows()
    header = copilot.portfolio_header(reader, rows)
    assert f"clients={len(rows)} " in header
    assert f"flagged_for_attention={sum(1 for r in rows if r['flagged'])} (" in header
    assert f"dormant_terminals_now={sum(1 for r in rows if r['dormant_days'])} (" in header
    assert f"rate_change_recommended={sum(1 for r in rows if r['rate_change'])} (" in header
    total = f"{sum(r['vol_t30'] or 0 for r in rows):,.0f}"
    assert f"total_volume_last30d_aed={total}" in header


def test_views_list_the_clients_the_question_is_about(reader):
    rows = reader.portfolio_rows()

    def plan(q, compact=False):
        return copilot._plan(rows, q, compact)

    _, lending, _, _ = plan("Lending opportunities?")
    assert lending and all(r["pitch"].startswith("Lending") for r in lending)
    assert [r["pitch_rank"] for r in lending] == sorted(r["pitch_rank"] for r in lending)          # strongest pitch first
    _, cross, _, _ = plan("Cross-sell candidates?")
    assert cross and all(r["pitch"].startswith("Cross-sell") or r["ntb"] for r in cross)
    _, rates, _, _ = plan("Which clients have a recommended rate change?")
    assert len(rates) == sum(1 for r in rows if r["rate_change"]) and all(r["rate_change"] for r in rates)   # "recommended" is not a pitch word here
    _, dormant, _, _ = plan("Who is dormant?")
    assert dormant and all(r["dormant_days"] for r in dormant)
    _, dubai, _, _ = plan("Which clients in Dubai have a lending pitch?")
    assert dubai and all(r["city"] == "Dubai" and r["pitch"].startswith("Lending") for r in dubai)
    _, balance, _, _ = plan("Which clients have the highest balance?")
    assert [r["balance"] for r in balance] == sorted((r["balance"] for r in balance), reverse=True)
    name = next(r["name"] for r in rows if sum(1 for x in rows if x["name"] == r["name"]) == 1)
    fields, named, _, _ = plan(f"Tell me about {name}")
    assert [r["name"] for r in named] == [name] and fields == copilot.ALL_FIELDS


def test_a_partial_list_says_so(reader):
    _, body = copilot.portfolio_context_parts(reader, None, "Which clients have the highest balance?")
    first = body.split("\n", 1)[0]
    assert f"listed={config.PORTFOLIO_ROW_LIMIT}" in first and "NOT LISTED:" in first
    _, pitches = copilot.portfolio_context_parts(reader, None, "Lending opportunities?")
    assert "listed=5 " in pitches.split("\n", 1)[0]      # a pitch takes about 60 reply tokens to write up, so 5 fit the reply limit
    assert "list is partial" in copilot.SYSTEM_RULES and "list is partial" in copilot.PORTFOLIO_FILTER_RULES


def test_the_room_left_in_the_window_caps_the_rows(reader):
    _, full = copilot.portfolio_context_parts(reader, None, "Which clients have the highest balance?", budget_chars=100_000)
    _, tight = copilot.portfolio_context_parts(reader, None, "Which clients have the highest balance?", budget_chars=120)
    assert len(tight.splitlines()) < len(full.splitlines()) and "NOT LISTED:" in tight.split("\n", 1)[0]


def test_a_fee_question_gets_the_knowledge_page_and_no_client_rows(reader):
    p = copilot.portfolio_prompt(reader, msgs("What are the package fees?"))
    assert "## 3. Packages, charges" in p["system"] and "matching_clients=0 listed=0" in p["system"]
    assert "## 4. Business loans" not in p["system"]
    assert knowledge.for_question("Portfolio summary") == ""


def test_knowledge_parts_are_chosen_by_the_question():
    core, fees, loans = (knowledge.for_question(q, always_core=True) for q in ("best cross-sell?", "what are the fees?", "what is the loan tenure?"))
    assert "## 2. Allowed products" in core and "## 3. Packages" not in core and "## 4. Business loans" not in core
    assert "## 3. Packages" in fees and "## 4. Business loans" in loans
    assert knowledge.build() == knowledge.KNOWLEDGE_PATH.read_text(encoding="utf-8")        # the whole page is unchanged


# ── long conversations ──────────────────────────────────────────────────────
def test_long_history_drops_the_oldest_turns_and_keeps_the_newest_question():
    chat = []
    for i in range(6):
        chat += [{"role": "user", "text": f"question {i} " + "q" * 900}, {"role": "bot", "text": f"answer {i} " + "a" * 900}]
    chat.append({"role": "user", "text": "the newest question"})
    h = copilot._history(chat)
    assert h[-1]["content"] == "the newest question" and h[0]["role"] == "user"
    assert sum(len(x["content"]) for x in h) <= config.HISTORY_MAX_CHARS + len("the newest question")
    assert len(h) < 12 and "question 0" not in h[0]["content"]


def test_a_single_very_long_question_is_kept_whole():
    h = copilot._history([{"role": "user", "text": "z" * 7000}])
    assert len(h) == 1 and len(h[0]["content"]) == 7000


# ── the merchant chat ───────────────────────────────────────────────────────
def test_every_merchant_prompt_fits_even_on_a_follow_up_turn(reader):
    follow_up = [{"role": "user", "content": "x" * 300}, {"role": "assistant", "content": "y" * 1400}, {"role": "user", "content": "Next question?"}]
    worst = 0
    with SessionLocal() as s:
        for mid, _ in reader.directory_names():
            p = copilot.merchant_prompt(ClientReader(s, mid), msgs("What are the package fees and loan terms?"))   # the largest knowledge case
            worst = max(worst, pb.estimate(p["system"], follow_up))
            assert p["system"].startswith("You are the RM Co-pilot")
    assert worst <= pb.prompt_limit()


def test_merchant_chat_sends_only_the_knowledge_it_needs_and_a_compact_context(reader):
    mid = reader.directory_names()[0][0]
    with SessionLocal() as s:
        p = copilot.merchant_prompt(ClientReader(s, mid), msgs("Summarize this client"))
    assert "## 2. Allowed products" in p["system"] and "## 3. Packages" not in p["system"]
    assert "volume_bars" not in p["data"] and "daily_last_30_days (date|volume_aed|txns|terminal|card_type)" in p["data"]
    assert pb.estimate(p["system"], []) < 5200      # was 7,170 to 7,791 with the whole page and the long JSON


# ── a prompt that cannot fit is never sent ──────────────────────────────────
def test_an_over_budget_prompt_is_answered_from_data_and_never_sent_to_the_model(monkeypatch):
    monkeypatch.setattr(config, "GUARDRAILS_ENABLED", False)
    monkeypatch.setattr(config, "CHAT_CACHE_ENABLED", False)
    monkeypatch.setattr(copilot.llm, "complete", lambda *a, **k: pytest.fail("the model must not be called with an oversize prompt"))
    huge = "RULES\n=== DATA (one client per line) ===\n" + "1|2|3|" * 20_000
    out = copilot._answer(huge, msgs("Portfolio summary"), lambda: "data-only answer", GroundingContext("portfolio", [], []))
    assert out["mode"] == "data" and out["reply"] == "data-only answer"
    last = open(config.AUDIT_LOG_PATH, encoding="utf-8").read().strip().splitlines()[-1]
    assert '"event": "prompt_over_budget"' in last


def test_token_counts_are_audited_but_not_sent_to_the_browser(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    def fake_complete(system, messages, **kw):
        copilot.llm._usage.value = dict(prompt_tokens=123, reply_tokens=45, prompt_s=0.5, reply_s=1.5)
        return "29 clients are flagged for attention."

    monkeypatch.setattr(config, "GUARDRAILS_ENABLED", False)
    monkeypatch.setattr(config, "CHAT_CACHE_ENABLED", False)
    monkeypatch.setattr(copilot.llm, "complete", fake_complete)
    r = TestClient(app).post("/api/copilot/portfolio", json={"messages": [{"role": "user", "text": "How many clients are flagged?"}]})
    assert r.status_code == 200 and r.json()["mode"] == "llm" and "usage" not in r.json()
    import json
    line = json.loads(open(config.AUDIT_LOG_PATH, encoding="utf-8").read().strip().splitlines()[-1])
    assert line["usage"]["prompt_tokens"] == 123 and isinstance(line["usage"]["prompt_tokens_estimated"], int)
