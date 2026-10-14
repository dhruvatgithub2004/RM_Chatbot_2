"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fmtAed } from "@/lib/format";
import type { CrossSellData, CrossSellItem } from "@/lib/types";
import { Figures } from "./ActNow";
import Blueprint, { ErrorCard, Loading } from "./Blueprint";

function Card({ item, onView }: { item: CrossSellItem; onView: (id: string) => void }) {
  const o = item.offer;
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
        <span className="tag tag-accent">{item.value_tier} value</span>
      </div>

      <div>
        <div className="card-kicker" style={{ marginBottom: 2 }}>Why it is a target</div>
        <ul style={{ margin: 0, paddingLeft: 16, display: "flex", flexDirection: "column", gap: 3, fontSize: 13, lineHeight: 1.4 }}>
          {item.reasons.map((r) => <li key={r}><Figures text={r} /></li>)}
        </ul>
      </div>

      <div style={{ flex: 1 }}>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <span className="card-kicker">What to offer</span>
          <span className="tag tag-outline" style={{ fontSize: 10 }} title={o.source === "llm" ? `Decided by the AI suggestion engine · ${o.model ?? ""}` : "Rule-based pitch; the AI engine has not decided this one"}>
            {o.source === "llm" ? "AI" : "Rules"}
          </span>
        </div>
        <div style={{ fontSize: 13, fontWeight: 600, marginTop: 2 }}>{o.product}</div>
        {o.source === "llm" && <div className="text-muted" style={{ fontSize: 11, marginTop: 2 }}>{o.why}</div>}
        {item.also_lending && (
          <div className="text-muted" style={{ fontSize: 12, marginTop: "var(--space-2)" }}>
            Also qualifies for: {item.also_lending.product}{item.also_lending.amount_aed ? ` · up to ${fmtAed(item.also_lending.amount_aed)}` : ""}
          </div>
        )}
      </div>

      <div>
        <button className="btn btn-ghost" onClick={(e) => { e.stopPropagation(); onView(item.merchant_id); }}>View profile →</button>
      </div>
    </Blueprint>
  );
}

/** Step 2 of the dashboard: merchants that lack a product we can offer. Rules choose and rank them from the data. */
export default function CrossSell({ onView }: { onView: (id: string) => void }) {
  const [data, setData] = useState<CrossSellData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let live = true;
    api.crossSell().then((d) => live && (setData(d), setError(null))).catch((e) => live && setError(String(e.message)));
    return () => { live = false; };
  }, [tick]);

  return (
    <section aria-labelledby="cross-sell-title" style={{ marginBottom: "var(--space-8)" }}>
      <div className="card-kicker">Grow</div>
      <h2 id="cross-sell-title" style={{ margin: "2px 0 4px", fontSize: 26 }}>Cross-sell targets</h2>
      {error ? (
        <ErrorCard message={`The cross-sell list could not be loaded: ${error}`} onRetry={() => setTick((t) => t + 1)} />
      ) : !data ? (
        <Loading />
      ) : (
        <>
          <p className="text-muted" style={{ fontSize: 12, margin: "0 0 var(--space-4)", maxWidth: 900 }}>
            Top {data.items.length} of {data.candidates} merchants that do not yet hold a product we can offer ({data.growth_ready} of them are also growing or close to
            their POS limit), ranked by estimated monthly revenue plus any growth. Rules pick and rank them from the data.
          </p>
          {data.items.length === 0 ? (
            <p className="text-muted">No merchant has a product to offer right now.</p>
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
