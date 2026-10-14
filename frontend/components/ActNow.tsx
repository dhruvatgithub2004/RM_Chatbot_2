"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ActNowData, ActNowItem } from "@/lib/types";
import Blueprint, { ErrorCard, Loading } from "./Blueprint";

// Figures in a reason line (percentages, day counts, AED amounts) in bold, so the eye lands on the numbers.
const FIGURE = /(\d[\d,.]*\s?%|\d[\d,.]*\s(?:days?|months?)|AED\s?\d[\d,.]*[kM]?)/g;

export function Figures({ text }: { text: string }) {
  return <>{text.split(FIGURE).map((part, i) => (i % 2 ? <strong key={i} style={{ color: "var(--color-accent-700)", fontWeight: 700 }}>{part}</strong> : part))}</>;
}

function Card({ item, onView }: { item: ActNowItem; onView: (id: string) => void }) {
  const a = item.action;
  return (
    <Blueprint className="opp-card" onClick={() => onView(item.merchant_id)} style={{ gap: "var(--space-3)", padding: "var(--space-4)" }}>
      <div style={{ display: "flex", gap: "var(--space-3)", alignItems: "baseline" }}>
        <span style={{ fontFamily: "var(--font-heading)", fontSize: 28, lineHeight: 1, color: "var(--color-accent)" }}>{item.rank}</span>
        <div style={{ minWidth: 0 }}>
          <div className="card-title">{item.name}</div>
          <div className="text-muted" style={{ fontSize: 11 }}>{item.industry} · {item.city}</div>
        </div>
      </div>

      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
        <span className="tag tag-accent">{item.value_tier} value</span>
      </div>


      <div>
        <div className="card-kicker" style={{ marginBottom: 2 }}>Why it is flagged</div>
        <ul style={{ margin: 0, paddingLeft: 16, display: "flex", flexDirection: "column", gap: 3, fontSize: 13, lineHeight: 1.4 }}>
          {item.reasons.map((r) => <li key={r}><Figures text={r} /></li>)}
        </ul>
      </div>

      <div style={{ flex: 1 }}>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <span className="card-kicker">What to do</span>
          <span className="tag tag-outline" style={{ fontSize: 10 }} title={a.source === "llm" ? `Decided by the AI suggestion engine · ${a.model ?? ""}` : "Rule-based wording; the AI engine has not decided this one"}>
            {a.source === "llm" ? "AI" : "Rules"}
          </span>
        </div>
        {a.next_action && <div style={{ fontSize: 13, fontWeight: 600, marginTop: 2 }}>{a.next_action}</div>}
        {a.source === "llm" && <div className="text-muted" style={{ fontSize: 11, marginTop: 2 }}>{a.why}</div>}      {/* the rule-based wording repeats the facts above */}
      </div>

      <div>
        <button className="btn btn-ghost" onClick={(e) => { e.stopPropagation(); onView(item.merchant_id); }}>View profile →</button>
      </div>
    </Blueprint>
  );
}

/** The merchants the RM should act on now. Step 1: the five highest-value churn risks. Rules choose and rank them from the data. */
export default function ActNow({ onView }: { onView: (id: string) => void }) {
  const [data, setData] = useState<ActNowData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let live = true;
    api.actNow().then((d) => live && (setData(d), setError(null))).catch((e) => live && setError(String(e.message)));
    return () => { live = false; };
  }, [tick]);

  return (
    <section aria-labelledby="act-now-title" style={{ marginBottom: "var(--space-8)" }}>
      <div className="card-kicker">Act now</div>
      <h2 id="act-now-title" style={{ margin: "2px 0 4px", fontSize: 26 }}>High-value churn risks</h2>
      {error ? (
        <ErrorCard message={`The act-now list could not be loaded: ${error}`} onRetry={() => setTick((t) => t + 1)} />
      ) : !data ? (
        <Loading />
      ) : (
        <>
          <p className="text-muted" style={{ fontSize: 12, margin: "0 0 var(--space-4)", maxWidth: 900 }}>
            Top {data.items.length} of {data.high_value_at_risk} high-value merchants at risk ({data.at_risk} at risk in total), ranked by estimated monthly revenue
            lost against their own baseline. Rules pick and rank them from the data.
          </p>
          {data.items.length === 0 ? (
            <p className="text-muted">No high-value merchant is at risk right now.</p>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "var(--space-4)", alignItems: "stretch" }}>
              {data.items.map((i) => <Card key={i.merchant_id} item={i} onView={onView} />)}
            </div>
          )}
          <details style={{ marginTop: "var(--space-3)" }}>
            <summary className="text-muted" style={{ fontSize: 11, cursor: "pointer" }}>How a merchant gets on this list</summary>
            <p className="text-muted" style={{ fontSize: 11, margin: "4px 0 0", maxWidth: 900 }}>{data.definition}</p>
          </details>
        </>
      )}
    </section>
  );
}
