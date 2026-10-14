# RM Co-pilot — the story

*A merchant relationship manager's day, before and after. All figures and clients below are from the synthetic demo data (as of 3 Aug 2026) and the live app.*

---

## 1. The business problem

A Relationship Manager (RM) at a bank looks after dozens of small and mid-sized merchants: salons, grocers, clinics, logistics firms, hotels. Each merchant takes card payments through the bank's POS terminals and holds accounts and products with the bank.

The RM is supposed to know three things about every merchant, every week:

1. **Who needs me now?** A merchant whose terminals have gone quiet or whose card volume is falling may be about to take their business elsewhere.
2. **What should I offer?** Many merchants are missing products the bank sells (payroll, trade finance, working-capital loans). Pitching the wrong product wastes a call and the client's trust.
3. **Is the price right?** The rate a merchant pays should reflect their card mix and risk. If it is too high, they leave. If it is too low, the bank gives away margin.

The answers sit in different places: daily POS data, the merchant profile, the products a client already holds, the bank's package and charge documents, and the loan product pages. No RM can read 150 merchants' data every Monday. In practice RMs fall back on memory, on whoever called last, and on the largest accounts. Quiet merchants drift away, and good opportunities go unpitched.

**The problem in one line:** the information an RM needs to act exists, but it is spread across too many sources to turn into a prioritised, specific, defensible action for every client.

## 2. What we built

RM Co-pilot is a web app for the RM that turns raw merchant data into a ranked list of who to call, what to say, and a chat assistant for follow-up questions.

| Screen | What the RM gets |
|---|---|
| **Dashboard** | Clients flagged for attention, ranked, each with a one-line reason ("POS terminals dormant for 14 days, volume down 43%, High risk segment") |
| **Profile and analytics** | One page per merchant: balance, package, products held, 6-month volume, card mix, rate card, risk, with filters by balance range, segment, card type and product |
| **Suggestions** | The top 10 merchants to pitch, each with a product, a reason that cites that client's own numbers, a next step, and a filter by product |
| **Co-pilot (portfolio)** | A chat across the whole book: "who is flagged?", "who has dormant terminals?", "who should I pitch first?" |
| **Co-pilot (merchant)** | A chat about one client, locked to that client's data |

## 3. The workflow

```
 Data in                 Checked and computed          AI layer                    RM
 ---------               ----------------------        ----------------------      ----------------
 POS daily data   --->   Validate rows,          --->  Suggestion engine    --->   Dashboard: who
 Merchant profile        quarantine bad ones           (LLM) picks one action      needs me?
 Products held           Compute facts: volume         per client, with reason,    Suggestions: what
 NTB candidates          trend, dormancy, limit        next step, priority         to pitch?
 Bank product and        use, card mix                 |                           Co-pilot chat:
 charges documents       Score and rank attention      Code checks the AI:         why? what next?
 Rate model output       (rules, deterministic)        product real, not held,     |
                                                       amount within limits        RM decides and
                                                       |                           acts. Nothing is
                                                       Co-pilots answer from       executed by the
                                                       the data and the            system.
                                                       product knowledge page
```

**Step by step**

1. **Load and check.** Merchant, POS, product and cross-sell files are validated. Bad rows are quarantined and reported, not silently used. The current load has 150 merchants and 36,000 daily POS rows with none quarantined.
2. **Compute the facts.** Volume change against the prior 30 days, dormant-terminal streaks, share of POS limit used, card mix, tenure. These are calculated by code so they can be tested and trusted.
3. **Rank attention.** A rule-based score flags merchants who need a call. Today 29 of 150 are flagged, 10 have dormant terminals.
4. **Decide what to pitch.** For each merchant, an LLM reads the bank's product knowledge page and that merchant's data and proposes one action: lend, cross-sell, protect the relationship, or do nothing. Code then rejects anything invented, already held, or outside published limits.
5. **Present.** The RM sees ranked lists with reasons, opens a profile, and asks the co-pilot follow-up questions.
6. **The RM decides.** The app recommends and explains. It never sends an offer, changes a rate or approves a limit.

## 4. What the GenAI produces

GenAI is used for judgement across many signals and for explaining in plain language. It does not compute the numbers it quotes.

### 4.1 A pitch decision, with its reasoning

For **Short Salon** (Salons & Spas), the suggestion engine produced:

| | |
|---|---|
| Recommended product | Cross-sell: Payroll / WPS Services |
| Why | "With an average monthly turnover of AED 1,038,312, Short Salon could benefit from Payroll / WPS Services to streamline employee payments." |
| Next action | Discuss Payroll / WPS Services to enhance operational efficiency |
| Priority | 90 of 100 (opportunity, signal and fit scored separately and added), ranked 4th in the portfolio |

The reason cites the client's own figures. The product was checked by code against the bank's catalogue and the client's existing products (it is not already held) before the RM saw it.

### 4.2 A conversation grounded in one client

An RM opens **Miller Technologies** (Proprietor package, High risk) from the dashboard and asks what is going on and what to do this week. The co-pilot answered from that client's data only:

> Miller Technologies is experiencing a significant decline in POS volume and has a dormant streak of 14 days, indicating potential risk to the relationship.
> - **Volume decline:** 42.7% decrease in POS volume over the last 30 days.
> - **Dormancy:** POS terminals have been dormant for 14 days.
> - **Risk segment:** High risk segment.
>
> **Next action:** Reach out to discuss their recent volume decline and offer support.

These figures match the data: 14 dormant days, volume down 42.7%, High risk. The rule-based engine also lists "POS terminal reactivation" as the action for this client.

### 4.3 Portfolio questions in plain language

Across the book, an RM can ask "who is flagged?", "who should I pitch first?" or "what does a package cost?" and get a short, bulleted answer built from the same data that drives the dashboard and the Suggestions screen.

### 4.4 Rate suggestions

Each merchant's suggested rate and rationale come from an offline ML model: a calculated Visa interchange cost for their card mix plus a predicted spread. The app shows the current rate, the suggested rate and the reasoning.

### 4.5 What surrounds the GenAI

| Control | Effect |
|---|---|
| Answers limited to supplied data and the product page | Fewer invented figures |
| AI picks validated by code | No made-up products, no held products, amounts within limits |
| NVIDIA NeMo Guardrails on both chats | Questions asking the co-pilot to approve or change something are refused; attack prompts are screened; an answer that contradicts the data (for example listing clients who do not hold a product) is replaced by the correct data-only answer |
| Merchant chat holds one client only | Cannot leak another client's data |
| "AI-generated, verify before acting" labels | RM knows what is machine-written |
| Audit log of questions, answers and decisions | Every output can be traced |
| Rate limit and fallbacks | Stays up if the AI service fails |

Details are in `RESPONSIBLE_AI.md`. Where AI is and is not used is in `Role of AI.md`.

## 5. Value proposition

**For the RM**
- **Start the week knowing whom to call.** A ranked list with a reason, in place of reading 150 rows of data.
- **Walk into the conversation prepared.** The product, the reason with the client's own numbers, and the next step are ready.
- **Ask instead of dig.** The co-pilot answers follow-up questions in seconds and shows its facts.
- **No client left unseen.** Every merchant is scored every time, not only the largest.

**For the bank**
- **Retention.** Dormant terminals and falling volume are caught while the client can still be won back.
- **Growth.** Lending and cross-sell pitches are matched to what each client actually holds and needs, which targets the right product and avoids pitching what the client already has.
- **Pricing discipline.** Each merchant's rate is compared to a modelled rate built from their card mix, so over- and under-priced accounts are visible.
- **Consistency.** Every RM works from the same facts, the same product knowledge and the same rules.

**For risk and governance**
- **Grounded, checked and traceable.** Facts come from code, AI picks are validated, and every answer is logged.
- **Human in control.** The system recommends. People decide and act.

### How we would measure it (to validate, not yet claimed)

The prototype runs on synthetic data and has not been tested with RMs, so these are the measures a pilot should track, not results.

| Question | Measure |
|---|---|
| Does it save RM time? | Minutes to prepare a client review, with and without the app |
| Does it find the right clients? | Share of flagged clients who later reduced volume or left, compared with unflagged ones |
| Do the pitches land? | Conversion rate of suggested pitches versus RMs' own pitches |
| Do RMs trust it? | Share of suggestions accepted, and share of answers RMs correct |
| Is it safe? | Rate of wrong or ungrounded answers found in audit-log reviews |

## 6. A three-minute demo

1. **Dashboard.** "29 of 150 merchants are flagged this week." Open the top one, **Miller Technologies**: dormant 14 days, volume down 43%, High risk.
2. **Profile.** Show the 6-month volume bars, card mix, products held and the rate card. Use the filters: balance range, segment, card type, existing product.
3. **Merchant co-pilot.** Ask what is going on and what to do this week. Point out the "AI-generated" label and that the figures match the profile.
4. **Suggestions.** Show the top 10. Open **Short Salon**: the product, the reason with its own numbers, the next step. Filter by product.
5. **Scope and safety.** In a merchant chat, ask about another client. It refuses before any AI call.
6. **Close.** "The numbers come from code, the judgement from AI, the decision from the RM."

## 7. Honest limits

- **Synthetic data.** All clients, balances, rates and scores are demonstration data. Nothing has been tested on real customers.
- **Rates are illustrative.** Interchange is calculated from a real table, but the spread model is trained on a synthetic cohort.
- **Model quality varies.** The chat model (`gpt-4o-mini` by default) can slip. In testing it listed a High-risk client with an idle balance as having dormant terminals, when its terminals were active. This is why answers are labelled "verify before acting" and why the facts shown elsewhere in the app come from code. A stronger model can be set in one line of configuration.
- **Suggestion mix.** An earlier version chose "retention" for 102 of 150 clients and clustered its priority scores. We fixed both (32 retention, all with dormant terminals or falling volume; priority built from three scored parts), and the Dashboard now shows each client's AI decision. The engine now pitches 77% of clients, so it is less selective, and nobody has yet checked its decisions against an experienced RM's. That is a pilot task.
- **No outcome data yet.** We can show what the tool recommends, not yet whether recommendations win business. Section 5 sets out how a pilot would find out.

## 8. Where to read more

| File | What it covers |
|---|---|
| `Role of AI.md` | Exactly where AI is and is not used, and who decides what |
| `RESPONSIBLE_AI.md` | Controls, tests, known gaps and roadmap |
| `README.md` | How to run the app |
| `BLOCKERS_AND_PENDING_INPUTS.md` | Open decisions and data questions |
