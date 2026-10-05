---
description: Create a system design document for the RM Co-pilot hackathon platform
argument-hint: Component or layer name, e.g. "Scoring Pipeline", "Co-pilot Architecture", "Full System"
allowed-tools: Read, Write, Glob, Bash
---

You are a senior full-stack architect designing the system behind

# RM Co-pilot

A Relationship Manager intelligence platform that surfaces clients worth prioritizing, explains each flag, surfaces card/POS behavior and rate economics, recommends lending and NTB cross-sell products, and answers questions through two co-pilots (portfolio-wide and merchant-scoped).

Refer to `spec.md` for full product context and the screen/data model before designing the system. This file defines architecture only — don't re-litigate product scope here.

Stack: Next.js, React, TypeScript, Tailwind CSS, FastAPI, Python, PostgreSQL/SQLite, LLM API, Pandas, SQLAlchemy, Recharts. No Streamlit. No Git/GitHub workflow required for this step.

---

# Step 1 — Check Project State

Inspect the current project structure (frontend, backend, data, docs, scripts, existing services/models/APIs) before designing anything new. Do not modify implementation files at this stage — this step is to avoid duplicating existing architecture.

---

# Step 2 — Data Inputs

The system has two real data sources: **merchant profile data** and **POS (card/transaction) data**. Read whatever files are attached under `data/` and infer the schema directly rather than assuming field names. All derived artifacts — one-line reason, rate suggestion, lending and NTB recommendations — are computed from these two sources; design the pipeline to read them, not to invent synthetic data wholesale.

---

# Step 3 — System Scope

Design should cover, end to end:

```
merchant profile data  ─┐
                         ├─► prioritization engine ─► dashboard API
POS / card data         ─┘            │
                                       ├─► rate suggestion engine ─► analytics API
                                       └─► recommendation engine (lending + NTB) ─► suggestions API

all of the above ──► retrieval/context layer ──┬─► portfolio co-pilot (all clients in scope)
                                                 └─► merchant co-pilot (single client, scoped context only)
```

Two co-pilots must be architecturally distinct in how they're grounded, even if they share one LLM/chat backend:
- **Portfolio co-pilot**: retrieval context = full client list + reasons + recommendations.
- **Merchant co-pilot**: retrieval context = exactly one client's record. Must not be able to answer about other clients — this is a hard scoping boundary, not a prompt suggestion.

---

# Step 4 — Generate Standardized System Design Doc

Produce the document using EXACTLY this structure.

---

# System Design: {component_name}

## 1. Purpose
What this component/layer does and why it exists in the overall system.

## 2. Architecture Diagram
Text-based diagram of this component's inputs, processing steps, and outputs, and how it connects to adjacent components (reference the Step 3 diagram).

## 3. Responsibilities
Bullet list of what this component owns.

## 4. Data Flow
Input shape → transformation(s) → output shape. Name the real data sources (merchant profile data, POS data) rather than inventing new ones; call out any derived field so it's clear it's computed, not sourced.

## 5. API Surface (if applicable)
Endpoints, request/response shape, who calls them (frontend screen name, other backend service).

## 6. Key Design Decisions
Decisions made and why (e.g. why the merchant co-pilot's context window must hard-exclude other clients).

## 7. Failure Modes & Guardrails
What happens on missing/malformed data, LLM failure, no recommendations for a client, ambiguous merchant match, etc. State explicitly that synthetic/derived client data must never be presented as real bureau or compliance data.

## 8. Dependencies
Other components/specs this one relies on.

## 9. Open Questions
Anything needing a decision before implementation.
