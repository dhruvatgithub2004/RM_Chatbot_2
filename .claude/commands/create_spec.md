---
description: Create a structured feature specification for the RM Co-pilot hackathon platform
argument-hint: Spec number + feature name, e.g. "01 Data Model", "05 Dashboard Ranking", "08 Merchant Co-pilot"
allowed-tools: Read, Write, Glob, Bash
---

You are a senior full-stack architect, AI engineer, and product designer building the

# RM Co-pilot

A Relationship Manager (RM) intelligence platform that identifies clients worth prioritizing, explains why each client needs attention, surfaces card/POS behavior and rate economics, recommends lending and new-to-bank (NTB) cross-sell products, and answers RM questions through two distinct conversational co-pilots — one portfolio-wide, one scoped to a single merchant.

The application uses

- Next.js
- React
- TypeScript
- HTML
- CSS / Tailwind CSS
- FastAPI
- Python
- PostgreSQL / SQLite
- LLM API
- Pandas
- SQLAlchemy
- Recharts

There is NO Streamlit UI.
There is NO Git/GitHub workflow required for spec generation.
The project is developed locally and does not require Git branches or GitHub operations for this step.

---

# Step 1 — Check Project State

Before creating the specification, inspect the current project structure. Check:

- frontend
- backend
- data
- docs
- scripts
- `.claude`
- existing components
- existing APIs
- existing services
- existing database models
- existing prioritization logic
- existing co-pilot/chat implementation
- existing styling system (the bound **Industry** design system — blueprint wireframe cards, Barlow/Barlow Condensed, steel-blue accent)
- existing environment configuration

Do NOT modify existing implementation files at this stage. The purpose of this step is to understand the current architecture and avoid duplication.

---

# Step 2 — Parse Arguments

From `$ARGUMENTS`, extract:

## 1. spec_number
Zero-padded. Examples: `1` → `01`, `2` → `02`, `10` → `10`.

## 2. feature_name
Examples:
- Project Architecture
- Client Data Model
- Opportunity & Risk Scoring
- Dashboard Ranking View
- Client Profile View
- Card Mix & Volume Analytics
- Rate Suggestion Engine
- Lending & NTB Recommendation Engine
- Portfolio Co-pilot
- Merchant Co-pilot
- Suggestions Top-5 Feed
- Human-in-the-Loop Accept Flow
- RM Platform UI
- Guardrails & Grounding
- Evaluation & Demo Test Cases
- Demo Scenario & Hackathon Flow
- Deployment & Configuration

## 3. feature_slug
Lowercase kebab-case, max 40 characters.
Examples: `Portfolio Co-pilot` → `portfolio-copilot`, `Rate Suggestion Engine` → `rate-suggestion-engine`.

---

# Step 3 — Validate Spec Number

The specification must follow the project's approved sequence:

01 — Client Data Model
02 — Dashboard Prioritization View
03 — Client Profile View
04 — Card Mix & Volume Analytics
05 — Rate Suggestion Engine
06 — Lending & NTB Recommendation Engine
07 — Suggestions Top-5 Feed
08 — Portfolio Co-pilot (general, all clients)
09 — Merchant Co-pilot (scoped to one client)
10 — Human-in-the-Loop Accept Flow
11 — RM Platform UI / Navigation
12 — Guardrails & Grounding
13 — Evaluation & Demo Test Cases
14 — Demo Scenario & Hackathon Flow
15 — Deployment & Configuration

Project Architecture is a foundational document and should only be created if it does not already exist. If the requested feature does not match the project's architecture, ask the user to clarify.

---

# Step 4 — Read Existing Specifications

Before creating the new specification, inspect `.claudespecs`. Read relevant previous specs. The new specification MUST:

- build on previous specifications
- avoid duplicating existing functionality
- use existing terminology (client/merchant, reason, rate, lending, NTB, co-pilot mode)
- reuse existing components and services
- preserve existing architectural decisions
- identify dependencies on previous specs

If an existing specification already defines the requested feature, do not create a duplicate.

---

# Step 5 — Product Context

Use the following as the source of truth.

## Product
RM Co-pilot

## Target User
Bank Relationship Manager and back-office ops staff managing a portfolio of merchant/business clients (card acquiring, lending, accounts).

## Core Problem
RMs manually review client-by-client to figure out who needs attention, what's changed in their POS/card behavior, and what to pitch next. This doesn't scale across a large portfolio and misses signals (declining volume, limit pressure, idle balances, onboarding gaps).

## Core Value Proposition
The system surfaces the clients worth prioritizing, explains each flag in one line, and lets the RM go from "who needs attention" to "what to say to them" through a scoped conversational co-pilot — without manually digging through account history.

## Core Workflow
```
MONITOR PORTFOLIO
      ↓
PRIORITIZE & FLAG (one-line reason)
      ↓
OPEN CLIENT PROFILE
      ↓
REVIEW CARD/POS BEHAVIOR & RATE ECONOMICS
      ↓
SEE RECOMMENDED PRODUCT (lending or NTB cross-sell)
      ↓
ASK MERCHANT CO-PILOT (scoped Q&A)
      ↓
ACCEPT / PITCH
```

Two co-pilot entry points sit alongside this flow:
- **Portfolio co-pilot** (nav): answers questions across all clients — flagged clients, high-risk clients, lending opportunities, cross-sell candidates, portfolio summary.
- **Merchant co-pilot** (from a Suggestions row or a client profile): locked to one client's data only.

---

# Step 6 — Data Sources

The project has two real data sources available: **merchant profile data** and **POS (card/transaction) data**. Read whatever files exist under `data/` (or wherever they're attached) and infer the schema directly — do not guess or invent fields ahead of inspecting the actual data. Rate suggestions and lending/NTB recommendations are derived from these two sources.

---

# Step 7 — Data Integrity Rules

The specification must explicitly distinguish:

## Synthetic (safe to present as illustrative)
- client profiles, POS/card activity, rate suggestions, lending/NTB recommendations

## Real / must not be invented
- any actual bank product names, fee schedules, or rate cards referenced for realism — must come from real public sources, never fabricated as if official

The system must never represent synthetic client/behavior data as real customer data or a real credit bureau record.

---

# Step 8 — Visual/Design Constraint

All UI specs must conform to the bound **Industry** design system: light steel ground, Barlow Condensed headings over Barlow body, single steel-blue accent with tonal ramps, square-cornered hairline "blueprint" cards with corner registration marks, solid-fill primary button as the one filled object, Lucide icons at 1.5 stroke. Do not specify rounded cards, drop shadows beyond the system's elevation tokens, or a second accent color.

---

# Step 9 — Generate Standardized Spec

Create the specification using EXACTLY the following structure.

---

# Feature Spec: {feature_name}

## 1. Purpose
What this feature does, why it exists, what business problem it solves, how it contributes to RM Co-pilot.

## 2. User Goal
What the RM should be able to accomplish. Concrete outcome, e.g. "The RM should be able to tell at a glance which clients need attention this week and why."

## 3. Business Context
Relevant RM workflow, client use case, relationship to proactive portfolio intelligence, relationship to the overall hackathon pitch. Do not introduce unrelated banking functionality.

## 4. Scope
### In Scope
Everything that must be implemented.
### Out of Scope
Functionality intentionally excluded. Do not expand the hackathon scope unnecessarily.

## 5. Functional Requirements
### FR-001 — {Requirement}
Behavior, input, processing, output, validation, failure behavior. Continue numbering sequentially.

## 6. User Flow
End-to-end interaction as a text diagram, e.g.:
```text
RM opens dashboard
      ↓
Sees top-ranked flagged client
      ↓
Opens client profile
      ↓
Reviews card/POS analytics
      ↓
Opens Suggestions
      ↓
Opens merchant co-pilot for that client
      ↓
Asks a scoped question
      ↓
Accepts a recommendation
```

## 7. Data Requirements
Fields read/written by this feature, referencing the data sources in Step 6.

## 8. UI Requirements
Screen(s) touched, components from the Industry design system to use (`.card.blueprint` + corner marks, `.table`, `.tag`, `.btn-primary/secondary/ghost`, `.input`, `.seg`), states (empty, loading, error).

## 9. Dependencies
Prior specs this one builds on or requires.

## 10. Open Questions
Anything ambiguous that needs a product decision before build.
