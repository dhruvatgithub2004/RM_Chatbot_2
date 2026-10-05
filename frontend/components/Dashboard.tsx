"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fmtAed } from "@/lib/format";
import type { ClientDecision, Dashboard as DashboardData, DecisionKind } from "@/lib/types";
import Blueprint, { ErrorCard, Loading } from "./Blueprint";

const DECISION_LABEL: Record<DecisionKind, string> = { lending: "Lending", cross_sell: "Cross-sell", retention: "Retain", none: "No action" };

/** What the suggestion engine decided for this client: a kind tag, the product and amount, and the next step. */
function Decision({ d }: { d: ClientDecision | null }) {
  if (!d) return <span className="text-muted">—</span>;
  const product = d.product ? `${d.product}${d.amount_aed ? ` · ${fmtAed(d.amount_aed)}` : ""}` : null;
  return (
    <div>
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
        <span className={d.kind === "none" ? "tag tag-neutral" : "tag tag-accent"}>{DECISION_LABEL[d.kind]}</span>
        {product && <span style={{ fontSize: 12 }}>{product}</span>}
        <span className="tag tag-outline" style={{ fontSize: 10 }} title={d.source === "llm" ? `Decided by the AI suggestion engine · ${d.model ?? ""}` : "Rule-based fallback"}>
          {d.source === "llm" ? "AI" : "Rules"}
        </span>
      </div>
      {d.next_action && <div className="text-muted" style={{ fontSize: 11, marginTop: 2 }}>{d.next_action}</div>}
    </div>
  );
}

export default function Dashboard({ onView }: { onView: (id: string) => void }) {
  const [filter, setFilter] = useState<"all" | "opp">("all");
  const [search, setSearch] = useState("");
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let live = true;
    const t = setTimeout(() => {
      api.dashboard(filter, search).then((d) => live && (setData(d), setError(null))).catch((e) => live && setError(String(e.message)));
    }, search ? 200 : 0);
    return () => { live = false; clearTimeout(t); };
  }, [filter, search, tick]);

  const options: { key: "all" | "opp"; label: string }[] = [
    { key: "all", label: "All" },
    { key: "opp", label: "Opportunities" },
  ];

  return (
    <div>
      <h1 style={{ marginBottom: 4 }}>Dashboard</h1>
      <p className="text-muted" style={{ marginBottom: "var(--space-6)" }}>
        {data ? data.flagged_count : "…"} clients flagged for attention this week
      </p>
      <p className="text-muted" style={{ fontSize: 11, marginTop: "calc(var(--space-4) * -1)", marginBottom: "var(--space-4)" }}>
        {data?.decisions_source === "llm"
          ? "Suggested action: decided by the AI suggestion engine, checked in code against the product catalogue. The RM decides."
          : "Suggested action: rule-based on the supplied data (AI suggestions not generated yet)"}
      </p>

      <div style={{ display: "flex", gap: "var(--space-4)", alignItems: "center", marginBottom: "var(--space-4)", flexWrap: "wrap" }}>
        <div className="seg">
          {options.map((o) => (
            <label className="seg-opt" key={o.key}>
              <input type="radio" name="filter" checked={filter === o.key} onChange={() => setFilter(o.key)} />
              {o.label}
            </label>
          ))}
        </div>
        <input className="input" style={{ maxWidth: 260 }} placeholder="Search by client or industry" value={search}
               onChange={(e) => setSearch(e.target.value)} />
      </div>

      {error ? (
        <ErrorCard message={error} onRetry={() => setTick((t) => t + 1)} />
      ) : !data ? (
        <Loading />
      ) : (
        <Blueprint style={{ padding: 0 }}>
          <table className="table">
            <thead>
              <tr><th>Rank</th><th>Client</th><th>Industry</th><th>Flag</th><th>Suggested action</th><th></th></tr>
            </thead>
            <tbody>
              {data.clients.map((c) => (
                <tr key={c.merchant_id}>
                  <td style={{ fontFamily: "var(--font-heading)" }}>{c.rank}</td>
                  <td>{c.name}<div className="text-muted" style={{ fontSize: 11 }}>{c.city}</div></td>
                  <td>{c.industry}</td>
                  <td className="text-muted" style={{ fontSize: 12, maxWidth: 260 }}>{c.reason}</td>
                  <td style={{ maxWidth: 300 }}><Decision d={c.decision} /></td>
                  <td><button className="btn btn-ghost" onClick={() => onView(c.merchant_id)}>View →</button></td>
                </tr>
              ))}
              {data.clients.length === 0 && (
                <tr><td colSpan={6} className="text-muted" style={{ textAlign: "center", padding: "var(--space-6)" }}>No clients match.</td></tr>
              )}
            </tbody>
          </table>
        </Blueprint>
      )}
    </div>
  );
}
