# Blockers & Pending Inputs

Status after the data update (new columns in `merchant_profiles_v3.csv` and `pos_daily_acquiring_v3.csv`, plus `merchant_products_held.csv`, `ntb_cross_sell_candidates.csv` and `business_banking_packages_and_charges.md`).

**Result: all four hard blockers are resolved. Nothing is estimated or illustrative any more. What remains are decisions and sign-offs.** Tell me the item number and your answer and I'll apply it.

Status key: ✅ resolved · 🟡 built, needs your decision or sign-off · 🔴 not built

| # | Item | Status |
|---|------|--------|
| 1 | Card number and card type | ✅ |
| 2 | Current rate, suggested rate, rationale | ✅ (one data question, see 2a) |
| 3 | Existing products and NTB cross-sell | ✅ |
| 4 | Lending amounts and product names | ✅ (rules need sign-off, see 4a–4c) |
| 5 | Scoring thresholds and weights | 🟡 |
| 6 | LLM provider | ✅ |
| 7 | "Segment" definition | 🟡 (now backed by the packages document) |
| 8 | Data quirks | 🟡 (one quirk disappeared) |
| 9 | Portfolio scope (all 150 vs one RM) | 🟡 |
| 10 | Accept / pitch flow | 🔴 (not in the design) |
| 11 | Differences from the design | 🟡 |
| 12 | Package minimum-balance signal (new idea from the new document) | 🟡 optional |
| 13 | Suggestions screen showed the same product, amount and reason for the top merchants | ✅ replaced by LLM-decided suggestions (see 13); quality caveats in 14 |
| 14 | LLM quality limits with `gpt-4o-mini` | 🟡 your decision on the model |

---

## 1. Card number and card type ✅

**Done:** the profile's *Card no.* shows `card_number_masked` and *Card type* shows `card_product` (e.g. "Visa Signature Business Debit Card"). Both are used exactly as supplied.

**Still open (small):** the *Card mix analysis* panel is still by the per-day tier label in the POS file (`Mass` / `Premium` / `Super Premium` / `Debit` / `Business`), because the POS data has no scheme or product per transaction. The "txns" figure is the transaction count on days carrying each tier. Is that acceptable for the panel? If you want a mix by card scheme or product, I need a transaction-level column.

---

## 2. Rate suggestion ✅

**Done:** current rate, suggested rate and rationale come straight from the merchant file (`current_rate_pct`, `suggested_rate_pct`, `rate_change_recommended`, `rate_rationale`). I cross-checked the supplied rationales against the POS data: the chargeback ratio and premium-card share quoted in all 81 rationales match the POS data. Both co-pilots quote these fields as given.

### 2a. Decision needed: what to show as "Suggested" when no change is recommended 🟡
In all 69 rows with `rate_change_recommended = False`, `suggested_rate_pct` is filled and **differs** from the current rate (62 higher, 7 lower; e.g. current 2.36% vs suggested 2.55%), while the rationale says "No change recommended". Showing that number would contradict the text.

**What I did:** when a change is recommended, the card shows `current → suggested`. When it is not, the card shows `current → No change` with the supplied rationale. The raw `suggested_rate_pct` stays in the database and API but is not displayed.

**To resolve:** confirm this, or tell me what `suggested_rate_pct` means for those rows (for example a tier benchmark you want shown).

---

## 3. Existing products and NTB cross-sell ✅

**Done:**
- *Existing products* tags come from `merchant_products_held.csv` (385 rows, all 150 clients, 2–5 products each).
- NTB candidates come from `ntb_cross_sell_candidates.csv` (89 rows, 75 clients: Payroll / WPS Services 69, Trade Finance (smartTRADE) 20). The ingest checks whether a candidate is already held. **Correction (5 Oct 2026):** the original exact-name check reported none, but the held data calls a product `smartTRADE` where the candidate file says `Trade Finance (smartTRADE)`. With a name-tolerant match, 10 of the 89 candidates are already held, and the ingest now raises the warning `ntb_candidate_already_held`.
- The co-pilots use both. "What's the best cross-sell?" lists the supplied candidates with their rationale, and states the products held.

**Note:** the design's Profile screen has no NTB section, so NTB candidates appear only in Suggestions and in the co-pilots, as in the design.

---

## 4. Lending amounts and products ✅ (rules need sign-off)

**Done:** the lending offer is the supplied `suggested_working_capital_limit_aed`, and the product name ("Working capital facility") is one the bank's own page lists (the packages document). I removed my earlier generic "Treasury / fixed deposit placement" and signal-based "Working capital" rules, because those names weren't in the supplied data.

**How the Suggestions top 5 is built:** clients are ranked by supplied `opportunity_tier` (Prime first), then by suggested limit, then by synthetic score, then by ID. Each row is *Lending — Working capital facility · AED amount* when eligible, otherwise the first supplied NTB candidate. The "Why" text is built only from supplied fields (opportunity label, turnover, risk segment, synthetic score, limit).

**Result today:** 75 clients have a lending pitch, 11 have a cross-sell pitch, 64 have neither.

### 4a. Decision: minimum facility size 🟡
The bank's page says working capital facilities start at AED 250,000. **64 clients have a supplied limit below that** (as low as AED 10,000), so I make **no lending pitch** to them (the ingest raises a warning). Confirm that rule, or tell me those small limits are meant to be pitched anyway.

### 4b. Decision: who is excluded from a lending pitch 🟡
My rule: no lending pitch while terminals are dormant or in the High risk segment (11 clients with an eligible limit are excluded this way). The co-pilot explains the reason when asked. Confirm or change.

### 4c. The top 5 all look the same 🔴
This is now tracked in full as **item 13** below (problem, cause, and what is needed).

---

## 5. Scoring thresholds and weights 🟡

The dashboard ranking, the "Opportunities" cut-off and the one-line reasons come from rules in `backend/app/scoring.py`. These are **policy parameters, not data**. I calibrated them against the real distributions, but they need your approval.

| Parameter | Value | Calibration note (real data) |
|---|---|---|
| Flag threshold | score ≥ 30 | Flags **27** of 150 clients (it was 15 before; see the rate-review row) |
| Terminals dormant | 40 pts + up to 10 by streak length | 10 clients dormant today (6–24 days) |
| Volume decline vs prior 30 days | ≤ −10%, points = size of drop (max 40) | 10 clients below −15% |
| Sustained 6-month decline | ≤ −15%, 10 pts | 6-month change ranges −64% to +33% |
| Limit pressure | ≥ 70% of monthly POS limit, 15–25 pts | Max observed 77% (19 clients) |
| Idle balance | balance ≥ 50% of avg monthly turnover, 10–20 pts | Max observed 60% (26 clients) |
| Growth | ≥ +10% vs prior 30 days, 10 pts | About the 95th percentile |
| **Rate review (new)** | rate change recommended in the data, 10 pts | 81 clients |
| Risk segment | High +15, Medium +5 | Used as given |

**Known consequences:**
- The top 10 dashboard rows are still all dormant-terminal clients, because dormancy scores highest.
- The peak-day share of the *daily* limit never exceeds 62%, so I use the monthly limit for the limit-pressure signal.
- Chargebacks (now in the POS data) are tiny: over the last 30 days only 7 clients had any, and the highest ratio was 0.42%. I did **not** add a chargeback signal; the figures are available to the co-pilot.

---

## 6. LLM provider ✅

OpenAI `gpt-4o-mini` is connected (`backend/.env`). Verified live after the data update:
- Rate answers quote the supplied rates and rationale.
- Cross-sell answers list only supplied NTB candidates.
- A "who should I offer lending to first" question now returns the same top 5 as the Suggestions screen, in the same order. I added a precomputed pitch list to the context because the model otherwise followed the wrong row order.
- A question about another client's data from the merchant chat is refused before any model call.

The key was pasted into a chat, so consider rotating it before any shared demo.

---

## 7. What "segment" means 🟡

The *Segment* row shows the merchant file's `package` (Prime, Preferred, Connect, Prestige, Proprietor, Platinum, Emirati Business). The new packages document confirms these are the bank's real package tiers, so I think this is right. Confirm, or tell me how segment should be derived instead.

---

## 8. Data quirks 🟡

| Quirk | Status |
|---|---|
| POS data before the relationship start date | ✅ **Gone.** The updated start dates all fall before the POS window. |
| Duplicate business names: "Johnson Technologies" (MER2077, MER2091), "Hardy Style Co" (MER2108, MER2131) | Still there. The UI shows the name only. Should it show the ID too? |
| Daily limit × 30 is 1.9–3.1 × the monthly limit | Confirm the two limits are meant to be independent. |
| `risk_segment` does not track `synthetic_credit_score` | Confirm `risk_segment` is authoritative. |

---

## 9. Portfolio scope 🟡

25 RMs, 8 branches, every RM spans several branches. The prototype shows all 150 clients with no RM selector, as the design does. Say if you want an RM filter.

---

## 10. Accept / pitch flow 🔴

The design keeps `accepted` state but no rendered screen uses it, so I did not build an accept button or persistence. It would need a table to record accepted suggestions. Say if you want it.

---

## 11. Differences from the design 🟡

| Difference | Reason |
|---|---|
| Sidebar footer tag "Data as of 3 Aug 2026 · Synthetic" | Data is synthetic and ends 3 Aug 2026 |
| Rate card shows "No change" in the Suggested slot when no change is recommended | See 2a |
| Dormant tag ("Dormant · N days") next to the industry on the profile | A real, key signal |
| Subtitle keeps "this week" while the data is as of 3 Aug 2026 | Wording kept from the design |
| Volume chart uses plain bars (as in the design), not Recharts; no Tailwind | Matches the design exactly |
| Chat shows "Thinking…" and, when the LLM is off, a "Data-only answer" caption | Loading state and honesty |
| Brand name "Northbridge" | Taken from the design file. Confirm it's the name you want. |
| 6-month chart shows Feb–Jul 2026 | The six most recent complete months |
| Deep links (`/?view=profile&client=MER2005`) | New: lets you open a screen directly for demos |

---

## 12. New idea: package minimum-balance signal 🟡 optional

The packages document gives each package a minimum monthly average balance and a fall-below fee (for example Prime: AED 50,000 / AED 157.50 a month; Platinum: AED 3.5M / AED 1,575 a month). Comparing the account balance to the package minimum, **109 of 150 clients are below their package minimum today**. That is a real attention signal ("balance below package minimum, fall-below fee applies") and a basis for a package-review conversation.

I have **not** added it, since it wasn't requested and it would change the ranking (109 clients is a lot). Say if you want it, and whether it should score as an attention signal or appear only in the co-pilot.

---

## 13. Suggestions: the top merchants all get the same product, amount and reason 🔴

### The problem
On the Suggestions screen, all five rows show the identical recommendation: *Lending — Working capital facility · AED 12,250,000*, with a "Why" that reads the same apart from the synthetic score and risk segment. Only the merchant name and industry differ. An RM looking at the screen cannot tell why one merchant is ranked above another, or why each one is being offered the same thing.

### The reason (verified against the loaded data)

**A. The data has no variation among the top-ranked clients.**
- Ranking is by supplied `opportunity_tier` (Prime first), then by suggested limit. There are only **9 Prime-tier clients**, and they are all on the **Platinum** package with `avg_monthly_turnover_aed` of **exactly AED 3,500,000**. That value looks like a cap, not a measured figure.
- `suggested_working_capital_limit_aed` is a fixed multiple of turnover by tier. The Prime tier is **exactly 3×** turnover, so all nine get **AED 12,250,000**.
- Across all 150 clients there are only **38 distinct limits**, and four values cover 84 clients (AED 460,000 for 36; 100,000 for 21; 1,400,000 for 18; 12,250,000 for 9).
- The top 5 are therefore tied on every ranking field the data provides. The only thing separating them is my tie-break on synthetic score, which is not a business reason.

**B. My pitch logic has one product and one reason template.**
- The only lending product with a supplied amount is working capital, so every lending pitch uses it.
- The "Why" is built only from tier, label, turnover, risk segment, synthetic score and limit. Clients with the same values get the same sentence.
- Nothing merchant-specific (growth, limit utilisation, idle balance, industry, the NTB candidate) enters the lending reason or the choice of product.

### What is missing to fix it properly
1. **Real turnover and limit data.** Either turnover that is not capped at AED 3.5M for the Platinum clients, or a limit produced by a model that uses more than turnover (volatility, growth, credit quality, chargebacks). Today the limit is a lookup on tier.
2. **More lending products, with sizing and eligibility rules.** The bank's page lists term loans, overdrafts, equipment loans, trade finance (LC/LG) and supply chain finance, but there are no amounts or eligibility rules for them in the data. Needed: which product suits which merchant, for example a mapping by industry (trade finance for wholesale, equipment loans for clinics), and how each should be sized.
3. **Merchant-specific pitch reasons.** A decision on which signals should drive the reason and the product choice.

### Options (tell me which you want)
| Option | Needs new data? | Effect |
|---|---|---|
| **A.** After tier and limit, rank on merchant-specific signals (volume growth, limit utilisation) instead of synthetic score | No | Top 5 become distinguishable and defensible |
| **B.** Make the "Why" specific to each client: its own growth, limit utilisation and gap to the next tier | No | Reasons differ per merchant; product and amount stay the same |
| **C.** Add more lending products matched by industry or signal | Yes: a product-by-industry mapping and sizing rules | Different products and amounts per merchant |
| **D.** Supply real (uncapped) turnover or a richer limit model | Yes | Amounts differ per merchant |

My recommendation is **A + B now** (no new data) and **C** when you can provide the mapping.

### Resolution of item 13 (built)
Suggestions are now **decided by the LLM**, not by my rules.
- **One knowledge page:** `structured_data/rm_product_knowledge.md` consolidates the data dictionary, an "Allowed products" table (from `backend/app/catalogue.py`), the packages and charges document, and the public business-loans reference. Rebuild with `python -m app.knowledge`.
- **One decision per client:** for each of the 150 clients the LLM gets that page plus the client's data and returns: kind (lending / cross-sell / retention / none), product, amount, a "why" citing the client's own numbers, a next action, and a 0–100 priority. These are stored in `client_suggestion`. The Suggestions screen ranks by the LLM's priority. Regenerate with `python -m app.suggest_llm` (about 3½ minutes for 150 clients; it also runs at the end of `python -m app.ingest` when an LLM is configured).
- **Only facts are enforced in code:** the product must exist in the catalogue and be pitchable; it must not already be held; amounts must respect the published minimum and maximum and the client's supplied limit; unsized products carry no amount. A rejected answer is retried once with the reason, then falls back to the rule-based pitch, marked `source: rules`. Who gets what is the model's decision.
- **Co-pilots** also read the knowledge page, so they can answer product questions (caps, tenures, package fees) and explain a pitch.
- **Result today:** 146 of 150 decisions from the LLM; 4 fell back (the model proposed a Small Business Loan to clients whose limits, AED 10,000–40,000, are below its AED 50,000 minimum). Mix: 41 cross-sell, 23 lending, 81 retention, 5 none. Products used: Payroll / WPS 28, Small Business Loan 17, Trade Finance 13, Merchant Loan (POS) 6.
- The earlier tie (five identical Prime clients) is gone. The top 5 now differ in product, amount and reason.

**Assumption to confirm:** Merchant Loan (POS) and Small Business Loan amounts are sized from the supplied `suggested_working_capital_limit_aed`, capped by each product's published maximum, because it is the only supplied amount. Confirm that this is acceptable.

---

## 14. LLM quality limits with `gpt-4o-mini` 🟡

> **Update 5 Oct 2026:** points 1 and 2 below describe the engine before it was changed. Retention is now gated in code and priority is built from three scored parts (retention 102 to 32; priority scores at exactly 55 or 65 from 77% to 12%). See `Role of AI.md`, sections 10 and 11. Points 3 and 4 still apply.

Observed while building item 13:
1. **Too many "retention" decisions:** 81 of 150 clients (more than half), including clients whose only signal is a recommended rate change. A stronger model was more discerning in a 15-client comparison (`gpt-4o`: 5 retention, 2 none; `gpt-4o-mini`: 8 retention, 0 none).
2. **Priority scores cluster** around 55 and 65 (63 clients scored 55), so the ranking leans on my tie-break (opportunity tier, then limit).
3. **Arithmetic and lookup slips in chat:** asked about a client with a AED 30,236 balance on a package with a AED 50,000 minimum, the co-pilot said the balance was "above the minimum". Questions like "which clients suit a Construction Equipment Loan" can also get a lazy "no data" answer.
4. **Rate limits:** the first full run hit OpenAI 429 errors for 56 clients; I added backoff and lower concurrency (4 workers), and it now completes.

**Options:**
- **A.** Set `SUGGESTION_MODEL=gpt-4o` (or another stronger model) in `backend/.env` for the batch only, and rerun `python -m app.suggest_llm`. The chat can stay on `gpt-4o-mini`. The batch is about 150 calls.
- **B.** Also move the chat to a stronger model (`LLM_MODEL`), which should fix the lookup slips.
- **C.** Keep `gpt-4o-mini` as is.
Tell me which, and I'll rerun the batch if you pick A or B.

