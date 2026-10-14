You are helping a hackathon team prepare the BUSINESS IMPACT case and the STORYTELLING for a working prototype. Use Google Search for every external fact and cite the source (title, publisher, year, URL). Everything in the "What we built" section below was taken from the project's actual code and loaded data, so treat it as ground truth and do not add features that are not listed.

## Hackathon context (fill in before sending)

- Hackathon name and theme: [FILL IN]
- Judging criteria and weights: [FILL IN]
- Pitch length and format (e.g. 5 min pitch + 3 min demo + Q&A): [FILL IN]
- Audience (bank executives, technologists, mixed): [FILL IN]
- Should the bank be named? The demo UI uses a fictional bank brand, "Northbridge". The product and fee knowledge comes from public Emirates NBD business banking pages. [FILL IN: name the bank / keep it generic as "a UAE bank"]

## What we built

**Product:** RM Co-pilot, a web app for a bank Relationship Manager (RM) who looks after a portfolio of SME merchant clients (businesses that accept card payments on the bank's POS terminals) in the UAE.

**The problem it targets:** an RM has many merchant clients and several disconnected data sources (profile, daily POS acquiring, products held, pricing, lending sizing). They cannot see each week which clients are slipping away, which are outgrowing their limits, and which are ready for a lending or cross-sell conversation, so they work reactively.

**The four screens**

1. Dashboard. Two tabs: Opportunities (the default) and All. Opportunities shows the clients that have a suggested action, strongest first by the suggestion engine's priority, with the top 9 as clickable boxes that open the client profile and the rest in a table; clients with no suggested action are left out. All lists every client ranked by an attention score. Each row has a one-line reason (for example "POS terminals dormant for 12 days, volume down 38% vs prior 30 days") and a suggested action tagged as Lending, Cross-sell, Retain or No action. Each action is labelled "AI" or "Rules" so the RM can see where it came from. The header reads "N clients flagged for attention this week".
2. Profile and analytics. One page per merchant: card and POS limits, last-30-day volume and transaction count, balance, risk segment, package, products held, a 6-month volume chart, the card mix (Mass, Premium, Super Premium, Debit, Business), and a rate suggestion (current rate, suggested rate, written rationale). Searchable and filterable by balance range, segment, card type and product held.
3. Suggestions. The top 10 merchants to pitch, each with a recommended product, an amount where relevant, and a "why" that cites that client's own numbers. Filterable by product.
4. Co-pilot chat, in two modes. The portfolio co-pilot answers questions across all clients ("Which clients are flagged?", "Lending opportunities?"). The merchant co-pilot is locked to one client and refuses to discuss any other client.

On the Dashboard and Suggestions screens, every suggestion also has "Why this?", which shows the client's own data behind it, the validations re-run on current data, and a check that the figures in the AI's written explanation match the data, and "Useful? Yes / No", which saves the RM's rating so usefulness can be summarised for AI-decided versus rule-based suggestions and by product. There are no ratings yet because the feature is new.

**How the intelligence works**

- Data pipeline: CSV files are validated, bad rows are quarantined, and a data-quality report is written. Per-client facts are then computed from daily POS data: 30-day volume against the prior 30 days, 6-month trend, dormancy streak, share of monthly and daily POS limit used, balance against turnover, card mix, chargeback ratio.
- Attention score (deterministic rules, fully explainable): points for dormant terminals, falling volume, limit pressure, idle balance, growth, a pending rate review and risk segment. A client scoring 30 or more is flagged. Every signal is shown with its points and a plain-language sentence.
- Pitch decision engine (LLM): for each client the model receives that client's data plus a product knowledge page, and returns one decision: kind, product, amount, a reason citing at least two of the client's own numbers, a next step, and a priority made of three parts (opportunity 0-40, signal 0-30, fit 0-30). Code then checks the facts: the product must exist in the catalogue and be pitchable, the client must not already hold it, the amount must sit within published product limits and within the client's supplied working-capital limit, and a "retention" decision needs a real behavioural signal (dormancy or falling volume). A rejected answer is retried with the rejection reason, and after three rejections the client falls back to the rule-based pitch.
- Product catalogue: 10 pitchable products (Working capital facility, Small Business Loan, Merchant Loan (POS), Commercial Vehicle Loan, Construction Equipment Loan, Fleet Financing, Term Loan, Payroll / WPS Services, Trade Finance (smartTRADE), businessONLINE) and 4 marked not pitchable because the data needed to qualify a client is not held (for example property-secured loans).
- Rate suggestion model (shown to the RM as a range of the model's estimate plus or minus 0.10 points, because the model is trained on synthetic data): suggested merchant rate = blended interchange cost + predicted spread. The interchange part is a deterministic calculation from the published Visa UAE interchange table, weighted by the merchant's card mix. The spread is a Ridge regression on 7 merchant features, linear on purpose so each rate breaks down exactly into a per-feature "waterfall". The model was trained on a synthetic cohort, so its rates are illustrative and it has a documented path to retrain on real negotiated rates.

**Responsible AI and controls (all implemented)**

- Human in the loop by design: the co-pilot recommends and explains. If asked to approve, send, change or book anything it refuses and says the decision stays with the RM.
- NVIDIA NeMo Guardrails on input and output. Input rails block action requests, prompt injection, requests to reveal the system prompt, and abuse. Output rails block answers that mention another client inside a single-client chat, list a client who does not match the question's filter, claim an action was taken, guarantee an outcome, quote a suggested rate where no change is recommended, or recommend a product that is not pitchable or already held. AED figures that do not appear in the source data are logged for review.
- Safe fallback: when an AI answer fails a hard check or the model is unavailable, the RM gets a deterministic data-only answer built from computed facts, labelled as such. The chat never fails and never shows an answer that failed a check.
- The hard guarantees are plain code rules, so they hold even if the guardrail library or the model is down.
- Audit trail: every chat (question, reply, mode, model, guardrail verdict, cache hit, latency, request ID) and every suggestion decision is written to an append-only log.
- Transparency in the UI: "AI-generated, may contain errors, verify before acting", "Data-only answer", "AI" and "Rules" tags, and a permanent "Synthetic data" badge.
- Data residency: the default model is a local open-weight model (Qwen3 8B through Ollama) running on the bank's own machine, so no client data leaves the environment. A hosted model can be switched in by configuration.
- Efficiency: exact and semantic response caching (ChromaDB) and a rate limit per user.
- Quality: 137 automated test cases covering the backend, the decision engine, the guardrails and responsible-AI behaviour, plus evaluation scripts comparing AI decisions with rule-based ones.

**Tech stack:** Next.js 15 and React 19 frontend, FastAPI and SQLAlchemy backend on SQLite, pandas, scikit-learn, NVIDIA NeMo Guardrails, ChromaDB, Ollama (Qwen3 8B) with an optional Anthropic Claude path.

**Not built (do not claim these):** user login or role-based access, CRM or core-banking integration, sending emails or offers to clients, real customer data, tracking of whether a pitch was accepted, and mobile apps.

## The demo data (synthetic, useful for scale and illustration only)

All data is synthetic demonstration data. It is not real customer, credit bureau or bank performance data.

- 150 merchant clients across 16 industries (construction, grocery, wholesale trading, salons, fitness, logistics, IT services, education, fashion retail, restaurants, electronics, hotels, real estate, auto repair, clinics, jewellery) in Dubai (65), Sharjah (40), Ras Al Khaimah (18), Ajman (16) and Abu Dhabi (11)
- 25 RMs and 8 branches in the data; 7 business banking packages
- 36,000 daily POS rows covering 7 Dec 2025 to 3 Aug 2026: AED 453 million of card volume and 1.82 million transactions
- Last 30 days: AED 53.5 million of POS volume, against AED 55.7 million in the prior 30 days
- Combined account balances AED 21.2 million; combined average monthly turnover AED 58.3 million
- Risk segments: 91 Low, 48 Medium, 11 High
- 29 of 150 clients flagged for attention: 10 with dormant terminals, 19 nearing their POS limit, 4 with falling volume needing a retention call
- 75 clients qualify for a working-capital lending pitch under the rules, with AED 135.7 million of suggested limits in total
- 89 new-to-bank cross-sell candidates (mainly Payroll / WPS and Trade Finance)
- 110 clients have a recommended rate change, averaging 0.30 percentage points below the current rate

## What I need from you

Use Google Search throughout. Label every number as one of: (a) from our prototype, (b) external and cited, or (c) our assumption. Never present the synthetic figures as real bank results. Where you cannot find a reliable source, say so and give a clearly labelled assumption with a range in place of an invented figure.

**1. Market and problem evidence (search and cite)**

- The size and importance of SMEs in the UAE economy, and the SME credit gap in the UAE and wider MENA region
- UAE Central Bank or government targets and initiatives on SME lending
- Growth of card and POS acceptance and merchant acquiring in the UAE
- How RMs spend their time (selling versus administration and data gathering), typical RM portfolio sizes in SME banking, and cross-sell ratios or products per SME customer
- SME and merchant churn or attrition, and what a dormant or lost merchant costs a bank
- Published results from banks using AI co-pilots or next-best-action tools for relationship managers (productivity, conversion, revenue uplift), from sources such as McKinsey, BCG, Accenture, Deloitte or named banks
- Regulation relevant to AI in UAE banking (Central Bank of the UAE guidance on AI and model risk, data protection and data residency rules), and how our controls map to it

**2. Business impact model**

- Build a simple, transparent model with formulas visible, in three scenarios: conservative, base and stretch
- Cover these value levers: RM time saved on portfolio review and call preparation, lending revenue from converted working-capital pitches, fee income from cross-sell (payroll, trade finance, cash management), retained acquiring revenue from catching dormant and declining merchants early, pricing discipline from the rate model, and risk and compliance cost avoided through guardrails and audit
- Show the result first for our 150-client synthetic portfolio as a worked example, then scaled per RM and for a bank with a realistic number of SME RMs
- List every assumption (conversion rate, net interest margin, fee per product, hours saved per week, RM cost) with its source or its reasoning, and show which two or three assumptions the result is most sensitive to
- Add cost and feasibility: what it takes to run on a local model, and a realistic path from prototype to pilot to rollout
- Give 4 to 6 KPIs a pilot would track, with how each is measured

**3. Storytelling**

- A one-sentence pitch and three alternative taglines
- A narrative arc built around a named, fictional RM: their Monday morning before the tool, the moment the tool changes it, and the outcome for the RM, the merchant and the bank. Use one concrete merchant story for each of the three situations the product handles: a merchant going dormant, a merchant outgrowing its POS limit, and a healthy merchant ready for working capital
- A demo script, timed to our pitch length, that follows the four screens in order and ends on a guardrail moment (the RM asks the co-pilot to approve a loan and it declines and hands the decision back)
- A slide-by-slide outline (title, the one message per slide, the visual, speaker notes) sized to our pitch length
- What makes this different from a generic chatbot over bank data, in three points a non-technical judge will remember
- The 10 hardest questions judges are likely to ask, with strong, honest answers. Include: "your data is synthetic, so how do you know it works?", "what stops it hallucinating?", "why a local model?", "how is this different from the bank's CRM next-best-action?", and "what would it take to put this in production?"

**4. Competitive and comparable landscape (search and cite)**

- Existing RM co-pilot or next-best-action products from banks and vendors, globally and in the Gulf
- A short comparison table showing where our prototype is similar and where it differs

## Rules for your answer

- Tailor emphasis to the judging criteria above
- Keep external facts recent (prefer the last three years) and from primary or reputable sources; flag anything older
- Be honest about the prototype's limits; a credible claim beats a large one
- Write in plain business English that a bank executive can follow, and keep technical terms to the responsible AI section
- Use AED for money, with USD in brackets where it helps
- Finish with a one-page summary I can paste into a slide: problem, solution, proof, impact, ask
