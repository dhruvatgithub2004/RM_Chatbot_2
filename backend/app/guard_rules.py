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
        soft rule (audited, not blocked):
          ungrounded_number   an AED figure in the answer that appears nowhere in the data or knowledge page (it may be derived)

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
        return [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*\.?\d*", self.reference_text) if x.strip(",.")]

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
_RATE_QUOTE = re.compile(r"suggested\s+(?:merchant\s+)?rate\b[^.\n;]{0,40}?\d+(?:\.\d+)?\s*%", re.I)
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
        for m in _AED.finditer(answer.replace("**", "")):
            value = float(m.group(1).replace(",", ""))
            suffix = (m.group(2) or "").lower()
            value *= {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6}.get(suffix, 1)
            tol = 0.06 if suffix else 0.006
            if value >= 1000 and not any(abs(value - n) <= tol * max(abs(n), 1) for n in ctx.numbers):
                out.append(Violation("ungrounded_number", f"{m.group(0)} does not appear in the data (it may be derived)", hard=False))
    return out
