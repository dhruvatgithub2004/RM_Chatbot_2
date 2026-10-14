"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { TopPerformerItem, TopPerformersData } from "@/lib/types";
import { Figures } from "./ActNow";
import Blueprint, { ErrorCard, Loading } from "./Blueprint";

function Card({ item, onView }: { item: TopPerformerItem; onView: (id: string) => void }) {
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

      <div>
        <span className="tag tag-accent">Top performer</span>
      </div>

      <div>
        <div className="card-kicker" style={{ marginBottom: 2 }}>Why it is a top performer</div>
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
        {a.source === "llm" && <div className="text-muted" style={{ fontSize: 11, marginTop: 2 }}>{a.why}</div>}
      </div>

      <div>
        <button className="btn btn-ghost" onClick={(e) => { e.stopPropagation(); onView(item.merchant_id); }}>View profile →</button>
      </div>
    </Blueprint>
  );
}

/** Step 3 of the dashboard: the merchants driving the bulk of the portfolio's card volume. Rules choose and rank them from the data. */
export default function TopPerformers({ onView }: { onView: (id: string) => void }) {
  const [data, setData] = useState<TopPerformersData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let live = true;
    api.topPerformers().then((d) => live && (setData(d), setError(null))).catch((e) => live && setError(String(e.message)));
    return () => { live = false; };
  }, [tick]);

  return (
    <section aria-labelledby="top-performers-title" style={{ marginBottom: "var(--space-8)" }}>
      <div className="card-kicker">Keep close</div>
      <h2 id="top-performers-title" style={{ margin: "2px 0 4px", fontSize: 26 }}>Top performers</h2>
      {error ? (
        <ErrorCard message={`The top performers list could not be loaded: ${error}`} onRetry={() => setTick((t) => t + 1)} />
      ) : !data ? (
        <Loading />
      ) : (
        <>
          <p className="text-muted" style={{ fontSize: 12, margin: "0 0 var(--space-4)", maxWidth: 900 }}>
            The {data.top_performers} top performers hold {data.share_of_volume_pct}% of the portfolio's card volume. Showing the top {data.items.length} by card volume over the last
            30 days. Rules pick and rank them from the data. There is no record of when each was last contacted, so this list cannot say who is overdue for a check-in.
          </p>
          {data.items.length === 0 ? (
            <p className="text-muted">No top performers right now.</p>
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
