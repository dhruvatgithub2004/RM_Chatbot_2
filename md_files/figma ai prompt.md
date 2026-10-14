# Figma AI prompt — RM Co-pilot UI/UX redesign

A ready-to-paste prompt for Figma AI (Figma Make or First Draft) that asks for a better-looking, easier-to-use RM Co-pilot **without changing what the product does**. Everything inside the prompt is taken from the running app (screens, exact labels, data fields, states, chat behaviour), so the design can be built back into the existing frontend without touching the backend.

## How to use it

1. **Attach screenshots first.** Open `http://localhost:3000` and capture: Dashboard, Profile & analytics (with a merchant selected and with filters open), Suggestions, Co-pilot (general, with a few messages), Co-pilot (merchant, with a refusal and an AI answer). Figma AI follows a prompt much better when it can see the current layout.
2. **Paste everything between `=== START PROMPT ===` and `=== END PROMPT ===`** into Figma Make or First Draft.
3. **Review** the first result against the checklist in section 9 of the prompt. If something is missing, use one of the follow-up prompts at the bottom of this file instead of regenerating from scratch.
4. **Hand off** with the component-to-code mapping in section 8, so the design lands in the existing React components.

---

=== START PROMPT ===

# Redesign the UI/UX of "RM Co-pilot" (keep every feature and every data field)

## 1. What this product is

RM Co-pilot is a web app for a bank **Relationship Manager (RM)** who looks after dozens of small and mid-sized merchants (salons, grocers, clinics, logistics firms, hotels). It tells the RM **who needs attention**, **what to pitch**, and answers questions in a **chat assistant**. The brand shown in the app is **"Northbridge"** with the kicker **"RM Co-pilot"**.

The users are bank staff working on laptops all day. The tone must feel **credible, calm and precise**, like a modern banking or analytics product: dense enough for professionals, never cluttered, never playful. All data is **synthetic demonstration data** and the UI must keep saying so.

## 2. The most important rule

**Redesign the look and the interaction quality only. Do not remove, rename, merge or add any feature, screen, data field or user flow.** A developer will rebuild your design on top of the existing React/TypeScript app and the existing API. If the design needs data the app does not have, it is wrong.

You MAY:
- change layout, hierarchy, typography, colour, spacing, iconography, motion and component styling;
- improve states (loading skeletons, empty, error, hover, focus, selected, disabled);
- make existing information easier to scan (badges, grouping, emphasis, tooltips that show data already on screen);
- surface fields that already exist in the API but are not shown today (listed in section 7, clearly optional);
- make the layout responsive (laptop first, then tablet and phone).

You MUST NOT:
- invent data, metrics, charts or features that have no source in the existing data (no made-up KPIs, trends, ratings, avatars of people, notifications, user accounts, settings pages, export buttons);
- remove any control, filter, label, caption or notice listed below;
- change the meaning of any text. Keep the exact strings given in quotes, unless a note says they may be reworded.

## 3. Current design and what to improve

Today the app uses a wireframe look called "Industry": steel-blue accent (#5980a6) on a light grey ground (#f2f2f3), Barlow Condensed headings over Barlow body text, square corners, hairline borders and small "+" registration marks on card corners. It is consistent but stark: hierarchy is weak, tables are plain, there are almost no status colours, charts are bare, and the chat looks like a form.

Direction for the redesign:
- A **refined, modern banking look** with clear visual hierarchy: obvious page titles, grouped content, key numbers emphasised, secondary text quieter.
- Keep a **steel-blue / navy family as the brand colour** and keep Barlow (or a similar clean sans) so it still feels like the same product, but you may soften corners, add depth, and introduce **semantic status colours** (see 4.2). You may drop the registration marks.
- **Light theme required; dark theme as a bonus** if it comes cheaply from the same tokens.
- Text contrast at least WCAG AA (4.5:1 body, 3:1 large text and icons). Visible keyboard focus ring on every interactive element. Never rely on colour alone for status: pair colour with an icon or a text label.
- Icons: a thin-stroke outline set such as Lucide.
- Generous but efficient density: this is a work tool, so favour compact tables and tidy cards over big empty hero sections.

## 4. Global shell (present on every screen)

### 4.1 Layout
- **Left sidebar, about 230 px wide**, full height:
  - Brand block: **"Northbridge"** (large) and the kicker **"RM Co-pilot"** (small, uppercase, letter-spaced, accent colour).
  - **Four navigation items**, in this order, with a clear active state: **"Dashboard"**, **"Profile & analytics"**, **"Suggestions"**, **"Co-pilot"**.
  - At the bottom, always visible: a small outlined tag reading **"Data as of 3 Aug 2026 · Synthetic"** (the date comes from the data; if the date is unknown it reads **"Synthetic data"**). Hovering it shows the tooltip **"Synthetic demonstration data. Not real customer, bureau or compliance data."** This indicator must stay prominent on every screen.
- **Main content area** to the right, scrolls independently of the sidebar.
- On narrow screens the sidebar becomes a top bar or a drawer, but all four items and the synthetic-data tag stay reachable.

### 4.2 Status vocabulary to design once and reuse
The app shows these statuses today as plain tags. Give each a consistent badge style (colour + icon + text):
- **Dormant** (terminals inactive), shown as **"Dormant · 14 days"**
- **Risk segment**: **Low / Medium / High**
- **Flagged for attention** (a client on the dashboard attention list)
- **Opportunity tier / pitch category**: **Lending** and **Cross-sell**
- **Rate change**: **recommended** (current → suggested) or **"No change"**
- **Source of a suggestion**: **AI-decided** or **rule-based**
- **Chat notices** (see 5.5): AI-generated, data-only, guardrail refusal, failed accuracy check

### 4.3 Global states
- **Backend unavailable**: a full-width card titled **"Backend unavailable"** with the message **"Cannot reach the API. Start the backend (uvicorn app.main:app) and reload."** replaces the content area.
- **Loading**: today it is the text "Loading…". Replace with skeleton placeholders that match the final layout.
- **Error**: a card titled **"Something went wrong"** with the error message and a **"Retry"** button.
- Currency is always written **"AED 1,234,567"** (rounded, thousands separators). Missing numbers show **"—"**. Percentages for rates show two decimals, e.g. **"2.63%"**.

## 5. Screens (design all of them, each with its states)

### 5.1 Dashboard
**Purpose:** show the clients flagged for attention, ranked.

- Page title **"Dashboard"**. Subtitle: **"{N} clients flagged for attention this week"** (shows "…" while loading).
- Controls row:
  - A **segmented control** with two options: **"All"** and **"Opportunities"** (Opportunities = flagged clients only).
  - A **search box**, placeholder **"Search by client or industry"**. It filters as the user types.
- **Table** (rows are clients, ranked), columns:
  1. **Rank**
  2. **Client**: the name, with the **city** in smaller muted text beneath
  3. **Industry**
  4. **Flag**: a one-line reason, for example "POS terminals dormant for 14 days — volume down 43% vs prior 30 days · High risk segment"
  5. **Suggested action**: the AI suggestion engine's decision for that client, shown as a **kind tag** (**"Lending"**, **"Cross-sell"**, **"Retain"** or **"No action"**), the **product and amount** when there is one (for example "Payroll / WPS Services" or "Small Business Loan · AED 150,000"), a small **"AI"** tag (or **"Rules"** when it is the rule-based fallback; the tooltip names the model), and the one-line **next step** in smaller muted text. Shows "—" if there is no decision.
  6. A **"View →"** button that opens that client's Profile
- A one-line note under the subtitle: **"Suggested action: decided by the AI suggestion engine, checked in code against the product catalogue. The RM decides."** (when the engine has not run it reads **"Suggested action: rule-based on the supplied data (AI suggestions not generated yet)"**).
- The row order is the attention rank, not the AI's priority. Do not re-sort by the suggested action.
- Each row also carries data that is not displayed today: `risk` (Low/Medium/High), `is_dormant_now` (true/false), `score`, `flagged`. You may use `risk` and `is_dormant_now` for status badges on the row.
- **Empty state:** **"No clients match."**
- Sample rows (synthetic) to use in mock-ups:
  - 1, Miller Technologies, IT Services & Consulting, "POS terminals dormant for 14 days — volume down 43% vs prior 30 days · High risk segment"; Suggested action: Retain, AI, "Discuss rate reduction to 2.45% to enhance retention."
  - 2, Martinez IT Solutions, IT Services & Consulting, "POS terminals dormant for 6 days — volume down 28% vs prior 30 days"; Suggested action: Retain, AI, "Discuss potential strategies to increase POS activity and address the rate review."
  - 3, Bowers Grocery, Grocery & Supermarket, "POS terminals dormant for 14 days — volume down 46% vs prior 30 days"

### 5.2 Profile & analytics
**Purpose:** pick a merchant and see everything about it on one page.

**Left rail (about 240 px), top to bottom:**
1. Search box, placeholder **"Search merchants"**.
2. **Filters**, all combinable:
   - **"Balance range (AED)"**: two number inputs, **Min** and **Max**. Their placeholders show the lowest and highest balance in the data, for example "Min 745" and "Max 2,053,840".
   - **"Segment"**: a select, first option **"All segments"**, then options with counts such as **"Prime (39)"**, "Preferred (39)", "Connect (29)", "Prestige (19)", "Proprietor (13)", "Platinum (9)", "Emirati Business (2)".
   - **"Card type"**: a select, first option **"All card types"**, then card products with counts, such as **"Visa Signature Business Debit Card (78)"**.
   - **"Existing product"**: a select, first option **"All products"**, then products with counts, such as **"Current Account (150)"**, "businessONLINE (123)".
   - A **"Clear filters"** button that appears only when any filter or search is set.
3. A count line: **"{N} merchants"** (singular **"1 merchant"**).
4. A scrolling **merchant list**; each item shows the **name** and the **industry** beneath, with a clear selected state. Empty state: **"No merchants match."**

**Main panel for the selected merchant:**
- **Header:** merchant name as the page title; beside it an outlined tag with the **industry**, the **city** in muted text, and, only if the merchant is dormant, an accent tag **"Dormant · 14 days"**. On the right a **"← Back to dashboard"** button.
- **Card "Card & POS"**, label/value rows:
  - "Card no." (masked number), "Card type", "Monthly POS limit", "Daily POS limit", "POS volume / mo", "POS frequency / mo" (shown as "1,234 txns", or "—").
- **Card "Profile & behavior"**, label/value rows:
  - "Balance", "Behavior / risk" (Low/Medium/High), "Segment" (the package, e.g. Prime, Platinum).
  - Under it a sub-heading **"Existing products"** with one tag per product, or the muted text **"None on file"**.
- **Two action buttons:** **"View suggestions"** (secondary) and **"Ask co-pilot about this client"** (primary).
- **Card "Rate suggestion"**:
  - **"Current"** rate large, an arrow, then **"Suggested"** rate large. If no change is recommended, the suggested slot reads **"No change"** (never show a number in that case).
  - Below, the paragraph of rationale text (long, several sentences, supplied by the data).
- **Card "Volume tracking (6 mo, AED k)"**: a bar chart with six bars, each with the value in thousands above it and the month beneath. Empty state: **"No POS data"**.
- **Card "Card mix analysis"**: one row per card type (Mass, Premium, Super Premium, Debit, Business), each with the type name, the transaction count ("1,234 txns") and a proportional bar for its share. Empty state: **"No POS data"**.
- Sample merchant for mock-ups: **Miller Technologies**, Proprietor package, High risk, balance AED 275,786, POS volume last 30 days AED 379,051, dormant 14 days, rate Current 2.63% → Suggested 2.45% (change recommended).

### 5.3 Suggestions
**Purpose:** the top 10 merchants to pitch.

- Page title **"Suggestions"**. Subtitle: **"Top 10 merchants to pitch — lending and new-to-bank cross-sell"**.
- A filter: a label **"Filter by product"** and a select whose first option is **"All products"**, then options with counts: **"Payroll / WPS Services (52)"**, "Small Business Loan (35)", "Merchant Loan (POS) (15)", "Trade Finance (smartTRADE) (8)", "Working capital facility (5)".
- A one-line **source note** under the heading, one of:
  - **"Decided by the AI suggestion engine from the bank product knowledge page · gpt-4o-mini"** (the model name varies), or
  - **"Rule-based on the supplied data (AI suggestions not generated yet)"**.
- **Table**, columns:
  1. **Rank** (the overall rank. When a product filter is on, ranks can be 8, 18, 20 and so on, and that is correct)
  2. **Merchant**: name with the industry beneath
  3. **Recommended product**: an accent tag reading **"{category} — {product}"** plus **" · AED {amount}"** when an amount exists, for example "Lending — Small Business Loan · AED 150,000" or "Cross-sell — Payroll / WPS Services"
  4. **Why**: a one- or two-sentence explanation that cites the merchant's own numbers
  5. A **"Co-pilot →"** button that opens the merchant-scoped chat
- Also available in each row but not shown today: `next_action` (one line), `priority` (0–100), `opportunity_label`, `city`, `source`, `model`.
- **Empty states:** **"No recommendations right now."** and, when a product filter is on, **"No clients are pitched this product right now."**
- Sample rows: 4, Short Salon, Salons & Spas, "Cross-sell — Payroll / WPS Services", "With an average monthly turnover of AED 1,038,312, Short Salon could benefit from Payroll / WPS Services to streamline employee payments."; and 6, Brown Trading LLC, Wholesale Trading, "Cross-sell — Trade Finance (smartTRADE)", "With an average monthly turnover of AED 500,000 and no Trade Finance product held, Trade Finance (smartTRADE) can enhance your B2B operations."

### 5.4 Co-pilot (the chat), two modes

There are **two chats**, reached in different ways:
- **General (portfolio) chat.** Reached from the **"Co-pilot"** sidebar item. Title **"Co-pilot"**, subtitle **"Ask about any client across the portfolio"**. Placeholder **"Ask about any client…"**. Suggested-question chips: **"Which clients are flagged?"**, **"Lending opportunities?"**, **"Cross-sell candidates?"**, **"Portfolio summary"**.
- **Merchant chat.** Reached from **"Ask co-pilot about this client"** (Profile) or **"Co-pilot →"** (Suggestions). Title **"Co-pilot — {merchant name}"**, subtitle **"Scoped to this merchant only"**. Placeholder **"Ask about this client…"**. Chips: **"Summarize this client"**, **"Any risk flags?"**, **"What's the best cross-sell?"**, **"Rate recommendation?"**.
- The chat keeps **its own history** for the general chat and for each merchant (kept for the session).
- Make the current scope obvious at a glance (a scope indicator is welcome), while keeping these same entry points.

**Chat behaviour to preserve:**
- A scrolling message list (about 520 px tall on desktop; it may be taller if the layout allows). The newest message scrolls into view.
- **User messages** align right in the accent colour. **Assistant messages** align left on a neutral surface, maximum about 78% of the width.
- **Assistant messages render light formatting:** paragraphs, **bullet lists** (one nested level) and **bold** text. They are often lists of clients with a bold name per bullet, so make bullets and bold read well.
- While waiting for an answer, an assistant bubble shows **"Thinking…"**; design it as a typing indicator.
- **Chips** row above the input; clicking a chip sends that text. Chips and the Send button are disabled while an answer is pending.
- **Input** plus a **"Send"** button. Pressing Enter sends. Empty text is not sent.
- A standing footnote under the input: **"AI-generated answers can be wrong. Verify before acting. Data shown is synthetic."**
- Errors appear as an assistant message, for example **"Sorry — I couldn't get an answer (Too many questions in a short time, please wait a moment and try again)."**

### 5.5 Chat notices (important: these carry the product's responsible-AI promise)
A small line under an assistant message tells the RM how the answer was produced. Design **four visually distinct notice styles**, each with an icon, and keep the exact wording:

| Situation | Notice text | Suggested feel |
|---|---|---|
| Answer written by the AI model | **"AI-generated · may contain errors · verify before acting"** | Neutral, always present, quiet |
| Answer built from data only (no AI) | **"Data-only answer · LLM not connected"** | Neutral info |
| The AI's answer failed a check and was replaced | **"The AI answer failed an accuracy check · showing a data-only answer"** | Caution (amber) |
| The question was refused by a guardrail | **"Guardrail: check decision boundary"** or **"Guardrail: self check input"** (the name varies) | Shield icon, firm but calm |

Refusals also appear as the assistant's message itself, for example: *"I can recommend and explain, but I can't approve, send, change or book anything. Those decisions and actions stay with you as the RM. I can show the supporting data or the suggested next step if that helps."* and *"I'm sorry, I can't respond to that."* and *"This chat is scoped to Miller Technologies only, so I can't discuss other clients. Use the portfolio Co-pilot for cross-client questions."* (the last has no notice).

Sample conversation for mock-ups (merchant chat for Miller Technologies):
- User: "What is going on with this client and what should I do this week?"
- Assistant: "Miller Technologies is experiencing a significant decline in POS volume and has a dormant streak of 14 days, indicating potential risk to the relationship." then bullets: "**Volume decline:** 42.7% decrease in POS volume over the last 30 days.", "**Dormancy:** POS terminals have been dormant for 14 days.", "**Risk segment:** High risk segment." then "**Next action:** Reach out to discuss their recent volume decline and offer support." Notice: AI-generated.
- User: "Approve the loan for Garcia Salon" → assistant gives the decision-boundary refusal above with the "Guardrail: check decision boundary" notice.

## 7. Existing data you may optionally surface (do not invent anything beyond this)

These fields already come from the API but are unused in the current screens. Use them only if they improve scanning, and mark them clearly as optional in your design notes:
- Dashboard row: `risk`, `is_dormant_now`, `score`, `flagged`, and inside `decision`: `priority` (0 to 100) and `model`.
- Profile: **synthetic credit score** (label it "Synthetic score", never "credit score"), `num_pos_terminals`, `monthly_limit_utilisation` (share of the monthly POS limit used), `behaviour.volume_change_t30_vs_p30` (volume change versus the prior 30 days), `priority.reason` and `priority.flagged`, and a `recommendation` with `category`, `title` and `why` (the rule-based suggested action).
- Suggestions row: `next_action`, `priority`, `opportunity_label`, `source`, `model`.

## 8. Handoff requirements (so the design can be built in the existing app)

The frontend is **Next.js 15, React 19 and TypeScript**, styled with **CSS variables** on `:root`. Please make the design map onto these existing pieces:

| Existing component | What it is |
|---|---|
| `App` | The shell: sidebar, navigation, backend-error card, routing between the four views and between general and merchant chat |
| `Dashboard` | Section 5.1 |
| `Profile` | Section 5.2, including the left rail and filters |
| `Suggestions` | Section 5.3 |
| `Chat` | Section 5.4, the message list, chips, input, notices |
| `Blueprint` (card), `Row` (label/value), `Loading`, `ErrorCard` | The shared building blocks. Please redesign these as the core of the component library |

Deliver:
1. **Design tokens** named so they can become CSS variables: colours (brand ramp, neutrals, semantic success/warning/danger/info), font families and sizes, spacing scale, radii, shadows, motion durations.
2. A **component library** with variants and states: buttons (primary, secondary, ghost, icon, disabled), tags and badges (every status in 4.2), form fields (text, number, select, segmented control, search), cards and metric rows, table (header, row, hover, selected, empty), bar chart, proportional bars, chat bubbles (user, assistant), chips, typing indicator, the four chat notices, skeleton loaders, error and backend-unavailable cards, sidebar items (default, hover, active, focus).
3. **Frames** for every screen at **desktop (1440 wide)**, **tablet (about 834)** and **phone (about 390)**. On small screens the Profile rail turns into a collapsible filter panel or a bottom sheet.
4. For each screen, frames for: **loaded, loading (skeleton), empty, error**. For Profile also: **filters applied**, **no merchants match**, **dormant merchant**, **no POS data**, **no rate change**. For Co-pilot also: **empty conversation with chips**, **thinking**, **each notice type**, **an error message**.
5. A short **clickable prototype**: Dashboard → "View →" → Profile → "Ask co-pilot about this client" → merchant chat; Suggestions → "Co-pilot →" → merchant chat; changing a filter; sending a chip question.
6. **Accessibility notes**: focus order, focus ring, contrast pairs used, which colours always have a text or icon partner.

## 9. Acceptance checklist (I will check the result against this)

- [ ] All four navigation items, the brand block and the "Data as of … · Synthetic" tag are present and prominent on every screen.
- [ ] Every control in sections 5.1 to 5.5 is present with the exact label or placeholder given, and nothing extra that needs new data or a new backend call.
- [ ] Profile has all four filters (Balance range with Min and Max, Segment, Card type, Existing product), "Clear filters", the merchant count and the merchant list.
- [ ] Rate card shows "No change" instead of a number when no change is recommended.
- [ ] Suggestions shows the overall rank, the product tag with the optional amount, the "Why" text, and both empty states.
- [ ] Both chat modes exist, with their own titles, subtitles, placeholders and chips, and the chat shows the four notice types and the standing footnote.
- [ ] Loading, empty and error states exist for each screen.
- [ ] Status is never conveyed by colour alone; contrast meets AA; focus rings are visible.
- [ ] Layout works at 1440, about 834 and about 390 widths.
- [ ] Nothing in the design implies real customer data, a real credit-bureau score, or that the assistant can approve, send or change anything.

=== END PROMPT ===

---

## Follow-up prompts (use these to refine without starting over)

- **Chat notices:** "Make the four chat notices more distinct and add an info icon to each, but keep the exact wording and keep them small. The 'failed an accuracy check' notice should feel cautionary, not alarming."
- **Density:** "Make the Dashboard and Suggestions tables more compact for professional use, with a sticky header and full-row hover, without removing any column."
- **Profile hierarchy:** "On the Profile page, give the balance, POS volume per month and rate the strongest visual weight, and move limits and card details to secondary weight. Do not add any new data."
- **Dark mode:** "Add a dark theme from the same tokens and show the Dashboard and the merchant chat in it."
- **Mobile:** "Show the Profile page and the merchant chat at 390 px, with the merchant list and filters in a collapsible panel."
- **Brand:** "Try a more distinctive brand treatment for the sidebar header and the primary button while keeping a navy/steel-blue palette and the Barlow typeface."
- **Charts:** "Improve the 6-month volume bar chart and the card mix bars with hover tooltips that show the exact AED value and the share, using only the numbers already shown."

## Notes for the developer

- All data contracts live in `frontend/lib/types.ts`; the API client is `frontend/lib/api.ts`. A redesign should not need to change either.
- The current look is implemented in `frontend/app/industry.css` (tokens at the top, component classes below) and inline styles in the components. A new design system would replace those tokens and classes.
- Deep links used for demos must keep working: `/?view=profile&client=MER2005` and `/?view=copilot&mode=merchant&client=MER2005`.
- The chat's light formatting (paragraphs, bullets, bold) is rendered by a small function in `Chat.tsx`. Bot answers can be long lists, so test the design with 20-item lists.
