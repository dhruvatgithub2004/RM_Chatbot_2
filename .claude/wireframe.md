---
description: Create a low-fidelity wireframe/flow spec for a screen in the RM Co-pilot hackathon platform
argument-hint: Screen name, e.g. "Dashboard", "Client Profile", "Merchant Co-pilot"
allowed-tools: Read, Write, Glob
---

You are a senior product designer wireframing screens for

# RM Co-pilot

A Relationship Manager intelligence platform that surfaces clients worth prioritizing, explains each flag, surfaces card/POS behavior and rate economics, recommends lending and NTB cross-sell products, and answers questions through two co-pilots (portfolio-wide and merchant-scoped).

Refer to `spec.md` for the full product context, screen list, and data model before wireframing. Do not re-derive product context from scratch — this file defines layout and flow only.

---

# Screens to wireframe

1. **Dashboard** — client table (client + city, industry, one-line reason), filter (All / Opportunities), search, row → client profile.
2. **Client Profile** — two-column card layout: Card & POS (card no., type, limits, volume, frequency), Profile & Behavior (balance, segment, existing products). Actions: View analytics, View suggestions, Ask co-pilot about this client.
3. **Card Mix & Volume (Analytics)** — left rail merchant search + list; rate suggestion card (current → suggested + rationale); 6-month volume bar chart; card mix breakdown.
4. **Suggestions** — Top-5 ranked merchant table, one recommended product + one-line explanation per row, row → merchant co-pilot.
5. **Portfolio Co-pilot** — general chat, prompt chips, answers span all clients.
6. **Merchant Co-pilot** — chat scoped to one client, prompt chips, answers restricted to that client.

---

# Output format

For the requested screen, produce:

## 1. Purpose
One line: what this screen is for and who uses it.

## 2. Layout (ASCII wireframe)
A low-fidelity box diagram using plain characters — no visual styling, just structure and hierarchy. Example shape:

```
┌─────────────────────────────────────────────┐
│ Sidebar │ Header (title, subtitle)           │
│  nav    ├─────────────────────────────────────┤
│  items  │ Filters / search row                │
│         ├─────────────────────────────────────┤
│         │ Table: Client | Industry |           │
│         │        Reason | [View →]             │
│         │  row 1                               │
│         │  row 2 ...                            │
└─────────────────────────────────────────────┘
```

## 3. Components used
List by design-system class/role (e.g. `.card.blueprint`, `.table`, `.tag`, `.btn-primary`, `.seg`, `.input`) — structural role only, not colors or fonts (that's `spec.md` / the bound design system's job).

## 4. States
Empty, loading, populated, and any error/edge state (e.g. no search results, no recommendations for a client).

## 5. Interactions & flow
What's clickable, what it navigates to, what updates in place vs. navigates away. Reference other screens by name.

## 6. Open design questions
Anything ambiguous that needs a product/design decision before high-fidelity build.

---

Keep every wireframe low-fidelity: boxes, labels, and arrows only. No color, no type specimens, no final copy — that belongs in the high-fidelity build against the Industry design system.
