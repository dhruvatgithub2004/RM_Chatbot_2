"""Deterministic guardrail rules for the co-pilots. No LLM and no NeMo import: plain, testable Python.

These are the hard guarantees. `guardrails.py` registers them as NeMo Guardrails actions (input and output rails), and also
calls them directly if NeMo cannot be loaded, so the protection never depends on an LLM-based check.

  * is_action_request  - INPUT rail: the user asks the bot to approve / send / change something. The co-pilot recommends, the RM decides.
  * check_answer       - OUTPUT rail: checks a model answer against the data the model was given.
        hard rules (block the answer):
          other_client        client chat names a client other than the one in scope
          condition_mismatch  the question filters on dormant / risk segment / flagged and the answer lists a client that does not match
          forbidden_claim     the bot claims to have approved / sent / changed something, or guarantees an outcome
          rate_quote          quotes a suggested rate for a client with no rate change recommended
          product_policy      recommends a not-pitchable product, or one the client already holds
          ungrounded_number   an AED amount, percentage, day or month count, or client count that is not in the data the model was given
                              (for a client named in the answer: that client's figures, the portfolio totals, the knowledge page, or a
                              number the RM wrote in the question). Rounding is allowed to the precision the answer states.

The rules are deliberately conservative: a sentence that contains a negation ("not dormant", "no suggested rate") is skipped,
so a correct answer is not blocked. Blocking a wrong answer is cheap, because the caller falls back to the data-only answer.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cached_property

from . import catalogue


# ── data the rules check against ────────────────────────────────────────────
@dataclass(frozen=True)
class ClientFacts:
    merchant_id: str
    name: str
    risk: str                      # Low | Medium | High
    dormant: bool
    flagged: bool
    held: tuple[str, ...] = ()
    rate_change: bool | None = None
    figures: tuple[tuple[str, float], ...] = ()    # (kind, value) of every number the model was shown for this client; kind is pct, days or any


@dataclass
class Violation:
    rule: str
    detail: str
    hard: bool = True

    def __str__(self) -> str:
        return f"{self.rule}: {self.detail}"


@dataclass
class GroundingContext:
    scope: str                                              # "portfolio" | "client"
    clients: list[ClientFacts]                              # portfolio: every client; client scope: the one client
    directory: list[tuple[str, str]] = field(default_factory=list)   # (merchant_id, name) of every client
    current_id: str | None = None
    reference_text: str = ""                                # the data and knowledge page given to the model (for numbers)
    violations: list[Violation] = field(default_factory=list)        # filled in by the output rail

    @cached_property
    def _names_re(self):
        names = sorted({c.name for c in self.clients}, key=len, reverse=True)
        return re.compile(r"(?<!\w)(" + "|".join(re.escape(n) for n in names) + r")(?!\w)", re.I) if names else None

    @cached_property
    def _by_name(self) -> dict[str, list[ClientFacts]]:
        out: dict[str, list[ClientFacts]] = {}
        for c in self.clients:
            out.setdefault(c.name.lower(), []).append(c)
        return out

    @cached_property
    def _others_re(self):
        parts = []
        current_name = next((n for i, n in self.directory if i == self.current_id), "").lower()
        for mid, name in self.directory:
            if mid == self.current_id or name.lower() == current_name:
                continue
            parts += [re.escape(name), id_pattern(mid)]
        return re.compile(r"(?<![A-Za-z0-9])(" + "|".join(parts) + r")(?![A-Za-z0-9])", re.I) if parts else None

    @cached_property
    def product_terms(self) -> set[str]:
        """Product names a question may refer to: those in the data's held lists, and the catalogue names."""
        return {h for c in self.clients for h in c.held} | set(catalogue.BY_NAME)

    @cached_property
    def numbers(self) -> list[float]:
        return numbers_in(self.reference_text)

    @cached_property
    def pct_numbers(self) -> list[float]:
        """Numbers the reference text writes as percentages."""
        return [float(m.group(1)) for m in _PCT.finditer(self.reference_text)]

    @cached_property
    def day_numbers(self) -> list[float]:
        """Numbers the reference text writes as days."""
        return [float(m.group(1)) for m in _DURATION.finditer(self.reference_text) if m.group(2).lower().startswith("day")]

    def clients_in(self, unit: str) -> list[list[ClientFacts]]:
        """Distinct clients named in a sentence. Duplicate business names map to a group of clients."""
        if not self._names_re:
            return []
        seen, out = set(), []
        for m in self._names_re.finditer(unit):
            key = m.group(1).lower()
            if key not in seen:
                seen.add(key)
                out.append(self._by_name[key])
        return out


# ── shared helpers ──────────────────────────────────────────────────────────
_SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "bn": 1e9, "billion": 1e9}
_NUM = re.compile(r"(?<![A-Za-z0-9])(\d[\d,]*(?:\.\d+)?)(?:\s*(k|thousand|m|million|bn|billion)\b)?", re.I)


def numbers_in(text: str) -> list[float]:
    """Every number in a text. A number written with a scale ("27k", "5 million") is listed both as written and scaled."""
    out: list[float] = []
    for m in _NUM.finditer(text):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        out.append(v)
        if m.group(2):
            out.append(v * _SCALE[m.group(2).lower()])
    return out


def id_pattern(mid: str) -> str:
    """Regex for a merchant ID that also matches separated spellings ('MER 2002', 'mer-2002')."""
    m = re.fullmatch(r"([A-Za-z]+)(\d+)", mid)
    return rf"{re.escape(m.group(1).lower())}[\s\-_]*{m.group(2)}" if m else re.escape(mid.lower())


_NEG = re.compile(r"\b(?:no|not|none|never|without|neither|nor|except|excluding|but)\b|n't\b", re.I)


def _units(text: str):
    """Sentences and bullet lines, with markdown emphasis removed."""
    for line in text.replace("**", "").splitlines():
        line = line.strip(" -*•\t")
        for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", line):
            if s.strip():
                yield s.strip()


# ── INPUT rail: the user asks the bot to act ────────────────────────────────
_ACTION_VERBS = (r"approve|sanction|execute|book|submit|process|send|email|forward|change|update|set|increase|decrease|raise|lower|"
                 r"reduce|waive|activate|deactivate|close|open|disburse")
_ACTION_OBJECTS = r"loan|facility|limit|rate|mdr|offer|pitch|proposal|application|account|terminal|fee|charge|package|card"
_LEAD = (r"(?:^|[.!?]\s+)(?:please\s+|kindly\s+)?(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?|go\s+ahead\s+and\s+|"
         r"i\s+(?:want|need)\s+you\s+to\s+|you\s+(?:should|must|need\s+to)\s+|just\s+)?")
_ACTION_RE = re.compile(_LEAD + rf"(?:{_ACTION_VERBS})\b(?!\s+(?:me|us)\b)[^.?!\n]{{0,60}}?\b(?:{_ACTION_OBJECTS})\b", re.I)


def is_action_request(text: str) -> bool:
    """True when the user asks the co-pilot itself to approve, send, change or book something."""
    return bool(_ACTION_RE.search(text.strip()))


# ── OUTPUT rail: checks on a model answer ───────────────────────────────────
_FILTERS = {
    "dormant": (r"\bdormant\b|\binactive\b", "dormant", lambda c: c.dormant),
    "high": (r"\bhigh[\s-]*risk\b", "in the High risk segment", lambda c: c.risk == "High"),
    "medium": (r"\bmedium[\s-]*risk\b", "in the Medium risk segment", lambda c: c.risk == "Medium"),
    "low": (r"\blow[\s-]*risk\b", "in the Low risk segment", lambda c: c.risk == "Low"),
    "flagged": (r"\bflagged\b|\battention\b", "flagged for attention", lambda c: c.flagged),
}


_NEG_BEFORE = r"\b(?:not|non|no|without|except|excluding|exclude|never|aren't|isn't)\b[\w\s,-]{0,25}$"
_HOLD_VERB = re.compile(r"\b(?:hold|holds|holding|have|has|own|owns|using|uses|use|with|on)\b", re.I)
# a question that is about pitching, gaps or hypotheticals is not asking who *holds* a product
NOT_A_HOLD_QUESTION = re.compile(r"\b(?:could|should|would|might|need|needs|candidate|candidates|pitch|offer|cross[- ]sell|recommend|suggest|"
                                  r"eligible|suitable|fit|lack|lacking|missing|without|not|no|don't|doesn't)\b|n't\b", re.I)


def question_conditions(question: str, ctx: "GroundingContext") -> tuple[list[tuple[str, Callable[[ClientFacts], bool]]], str]:
    """The conditions a question filters on (dormant, risk segment, flagged, holds a product), skipping negated ones, and whether
    they combine with 'all' or 'any'. Each condition is (description of what a listed client must be, predicate over ClientFacts)."""
    q = question.lower()
    conds: list[tuple[str, Callable[[ClientFacts], bool]]] = []
    for pat, label, pred in _FILTERS.values():
        m = re.search(pat, q)
        if m and not re.search(_NEG_BEFORE, q[:m.start()]):
            conds.append((label, pred))
    if _HOLD_VERB.search(q) and not NOT_A_HOLD_QUESTION.search(q):
        for term in sorted(ctx.product_terms, key=len, reverse=True):
            if re.search(rf"(?<!\w){re.escape(term.lower())}(?!\w)", q):
                conds.append((f"a holder of {term}", lambda c, t=term: _holds(c, t)))
                break
    return conds, ("any" if re.search(r"\b(?:or|either)\b", q) else "all")


_FORBIDDEN = [
    (re.compile(r"\b(?:i|we)\s+(?:have\s+|'ve\s+|will\s+|'ll\s+|just\s+)?(?:approved|sanctioned|submitted|sent|emailed|booked|executed|"
                r"updated|changed|processed|increased|reduced|activated|disbursed)\b", re.I), "claims to have taken an action"),
    (re.compile(r"\b(?:i|we)\s+(?:will|'ll|can|shall)\s+(?:now\s+|go\s+ahead\s+and\s+)?(?:approve|sanction|submit|send|email|book|execute|process|"
                r"change|update|activate|disburse|waive|increase|reduce)\b[^.\n]{0,40}?\b(?:" + _ACTION_OBJECTS + r")\b", re.I), "offers to take an action"),
    (re.compile(r"\b(?:has|have)\s+been\s+(?:approved|sanctioned|submitted|sent|executed|processed|disbursed)\b", re.I), "claims an action was taken"),
    (re.compile(r"\bguarantee[sd]?\b", re.I), "guarantees an outcome"),
    (re.compile(r"\bbureau\s+(?:score|rating|report)\b", re.I), "refers to a credit bureau score"),
]
_RATE_QUOTE = re.compile(r"(?:suggested\s+(?:merchant\s+)?rate|model(?:led)?(?:\s+rate)?\s+range)\b[^.\n;]{0,40}?\d+(?:\.\d+)?\s*%", re.I)
_RECOMMEND = re.compile(r"\b(?:recommend(?:ed|ing|s)?|pitch(?:ed|ing)?|offer(?:ed|ing)?|suggest(?:ed|ing|s)?|propos(?:e|ed|ing)|"
                        r"cross[- ]sell(?:ing)?)\b", re.I)
_TAIL_END = re.compile(r"[.;|]|\b(?:existing products?|products? held|currently holds?|already (?:holds?|has|have)|holds?)\b", re.I)
_AED = re.compile(r"AED\s*(\d[\d,]*(?:\.\d+)?)\s*(k|m|million|thousand)?\b", re.I)


def _holds(client: ClientFacts, product: str) -> bool:
    """Held-product names in the data are sometimes shorter than catalogue names ('smartTRADE' vs 'Trade Finance (smartTRADE)')."""
    p = product.lower()
    return any(h.lower() == p or h.lower() in p for h in client.held)


def _recommended_products(unit: str) -> list[str]:
    m = _RECOMMEND.search(unit)
    if not m:
        return []
    tail = unit[m.end():]
    end = _TAIL_END.search(tail)
    tail = tail[: end.start()] if end else tail
    return [p for p in catalogue.BY_NAME if re.search(rf"(?<!\w){re.escape(p)}(?!\w)", tail, re.I)]


_PCT = re.compile(r"(?<![A-Za-z0-9.])(\d+(?:\.(\d+))?)\s?%")
_DURATION = re.compile(r"(?<![A-Za-z0-9.])(\d+)\s*[- ]?(days?|months?)\b", re.I)
_COUNT = re.compile(r"(?<![A-Za-z0-9.,])(\d[\d,]*)\s+(?:of\s+(?:the\s+)?(\d[\d,]*)\s+)?(?:[A-Za-z-]+\s+){0,2}?(?:clients?|merchants?|customers?)\b", re.I)
_WINDOW_DAYS, _WINDOW_MONTHS = {30, 60}, {6, 12}      # the comparison windows the data is built on ("last 30 days", "6 months")
_MIN_AED = 100                                        # smaller amounts are not checked: they are usually unit prices in a sentence


def _near(value: float, pool: list[float], decimals: int) -> bool:
    """True when `value`, as written to `decimals` places, can be a rounding of some number in the pool."""
    tol = 0.5 * 10 ** -decimals + 1e-6
    return any(abs(value - n) <= tol for n in pool)


def check_figures(question: str, answer: str, ctx: GroundingContext) -> list[Violation]:
    """Block an AED amount, percentage, day or month count, or client count that is not in the data the model was given.

    Pool for a figure: the portfolio totals and knowledge text, the figures of every client the answer names, and any number the RM wrote
    in the question. In the portfolio chat a percentage is matched only against percentages and a day count against day counts. In a
    single-client chat the pool is the client's whole JSON, so percentages are also compared as fractions (0.43 and 43%).
    """
    text = answer.replace("**", "")
    named = ctx.clients_in(text)
    mine = [f for group in named for c in group for f in c.figures]      # (kind, value) of the clients the answer names
    pool = list(ctx.numbers) + numbers_in(question) + [v for _, v in mine]          # AED amounts, counts, months
    if ctx.scope == "portfolio":
        # A percentage must match a percentage and a day count a day count, so "7%" cannot pass on a "7" that means something else.
        pct_pool = ctx.pct_numbers + [v for k, v in mine if k == "pct"] + [float(m.group(1)) for m in _PCT.finditer(question)]
        day_pool = ctx.day_numbers + [v for k, v in mine if k == "days"] + [float(m.group(1)) for m in _DURATION.finditer(question)]
    else:   # one client: the JSON holds bare numbers and fractions, so any number can stand for a percentage or a day count
        pct_pool = pool + [n * 100 for n in pool if n != int(n) and abs(n) < 10]
        day_pool = pool
    out: list[Violation] = []

    def bad(shown: str, why: str):
        out.append(Violation("ungrounded_number", f"{shown} {why}"))

    for m in _AED.finditer(text):
        digits = m.group(1).replace(",", "")
        scale = _SCALE.get((m.group(2) or "").lower(), 1)
        v = float(digits) * scale
        # Rounding is allowed to the precision the answer states: "AED 27k" can stand for 27,153; "AED 53.5M" for 53,451,120; "AED 54.5M" cannot.
        tol = 0.5 * 10 ** -(len(digits.split(".")[1]) if "." in digits else 0) * scale + 1e-6
        if v >= _MIN_AED and not any(abs(v - n) <= tol for n in pool):
            bad(m.group(0).strip(), "is not in the data")
    for m in _PCT.finditer(text):
        if not _near(float(m.group(1)), pct_pool, len(m.group(2) or "")):
            bad(m.group(0), "is not in the data")
    for m in _DURATION.finditer(text):
        v, unit = int(m.group(1)), m.group(2).lower()
        if unit.startswith("month"):
            ok = v in _WINDOW_MONTHS or _near(v, pool, 0)
        else:
            ok = v in _WINDOW_DAYS or _near(v, day_pool, 0)
        if not ok:
            bad(m.group(0), "is not in the data")
    listed = len(named)
    for m in _COUNT.finditer(text):
        for g in (m.group(1), m.group(2)):
            if g and (v := int(g.replace(",", ""))) != listed and not _near(v, pool, 0):
                bad(f"{g} clients" if g == m.group(1) else f"of {g} clients", "is not in the data")
    return out


def check_answer(question: str, answer: str, ctx: GroundingContext) -> list[Violation]:
    out: list[Violation] = []
    conds, mode = question_conditions(question, ctx) if ctx.scope == "portfolio" else ([], "all")
    for unit in _units(answer):
        negated = bool(_NEG.search(unit))
        named = ctx.clients_in(unit)

        if ctx.scope == "client" and ctx._others_re:
            m = ctx._others_re.search(unit)
            if m:
                out.append(Violation("other_client", f"the answer mentions another client ({m.group(1)})"))

        if conds and not negated:
            for group in named:
                results = [any(pred(c) for c in group) for _, pred in conds]
                if not (any(results) if mode == "any" else all(results)):
                    failed = [label for (label, _), ok in zip(conds, results) if not ok]
                    out.append(Violation("condition_mismatch", f"{group[0].name} is not {' / '.join(failed)} in the data"))

        for pat, why in _FORBIDDEN:
            m = pat.search(unit)
            if m and not (why == "guarantees an outcome" and _NEG.search(unit[: m.start()][-12:])):
                out.append(Violation("forbidden_claim", f"{why}: \"{m.group(0)}\""))

        if not negated and _RATE_QUOTE.search(unit):
            for group in named or [[c] for c in ctx.clients if ctx.scope == "client"]:
                if all(c.rate_change is False for c in group):
                    out.append(Violation("rate_quote", f"quotes a suggested rate for {group[0].name}, where no rate change is recommended"))

        for prod in _recommended_products(unit):
            spec = catalogue.BY_NAME[prod]
            if spec.kind == "not_pitchable":
                out.append(Violation("product_policy", f"recommends {prod}, which is not a pitchable product"))
            holders = [g[0].name for g in (named or [[c] for c in ctx.clients if ctx.scope == "client"]) if any(_holds(c, prod) for c in g)]
            if holders:
                out.append(Violation("product_policy", f"recommends {prod}, which {holders[0]} already holds"))

    if ctx.reference_text:
        out.extend(check_figures(question, answer, ctx))
    return out
