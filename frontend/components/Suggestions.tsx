"use client";
import { Fragment, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Suggestion } from "@/lib/types";
import Blueprint, { ErrorCard, Loading } from "./Blueprint";
import { EvidencePanel, FeedbackSummaryStrip, ReviewControls, useRatings } from "./Review";

export default function Suggestions({ onCopilot, onProfile }: { onCopilot: (id: string) => void; onProfile?: (id: string) => void }) {
  const ratings = useRatings();
  const [openIds, setOpenIds] = useState<Set<string>>(new Set());
  const toggle = (id: string) => setOpenIds((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const [rows, setRows] = useState<Suggestion[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const [product, setProduct] = useState("");
  const [products, setProducts] = useState<{ product: string; count: number }[]>([]);

  useEffect(() => {
    api.suggestionProducts().then(setProducts).catch(() => setProducts([]));
  }, [tick]);

  useEffect(() => {
    api.suggestions(product || undefined).then((r) => (setRows(r), setError(null))).catch((e) => setError(String(e.message)));
  }, [tick, product]);

  return (
    <div>
      <h1 style={{ marginBottom: 4 }}>Suggestions</h1>
      <p className="text-muted" style={{ marginBottom: "var(--space-4)" }}>
        Top 10 merchants to pitch — lending and new-to-bank cross-sell
      </p>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", marginBottom: "var(--space-6)" }}>
        <label htmlFor="product-filter" className="text-muted" style={{ fontSize: 12 }}>Filter by product</label>
        <select id="product-filter" className="input" style={{ maxWidth: 360 }} value={product} onChange={(e) => setProduct(e.target.value)}>
          <option value="">All products</option>
          {products.map((p) => <option key={p.product} value={p.product}>{p.product} ({p.count})</option>)}
        </select>
      </div>
      <FeedbackSummaryStrip version={ratings.version} />
      {rows && rows.length > 0 && (
        <p className="text-muted" style={{ fontSize: 11, marginTop: 0, marginBottom: "var(--space-4)" }}>
          {rows[0].source === "llm"
            ? `Decided by the AI suggestion engine from the bank product knowledge page · ${rows[0].model}`
            : "Rule-based on the supplied data (AI suggestions not generated yet)"}
        </p>
      )}
      {error ? (
        <ErrorCard message={error} onRetry={() => setTick((t) => t + 1)} />
      ) : !rows ? (
        <Loading />
      ) : (
        <Blueprint style={{ padding: 0 }}>
          <table className="table">
            <thead>
              <tr><th>Rank</th><th>Merchant</th><th>Recommended product</th><th>Why</th><th>Review</th><th></th></tr>
            </thead>
            <tbody>
              {rows.map((t) => (
                <Fragment key={t.merchant_id}>
                <tr>
                  <td style={{ fontFamily: "var(--font-heading)" }}>{t.rank}</td>
                  <td>{t.name}<div className="text-muted" style={{ fontSize: 11 }}>{t.industry}</div></td>
                  <td><span className="tag tag-accent">{t.category} — {t.product}{t.amount_aed ? ` · AED ${Math.round(t.amount_aed).toLocaleString("en-US")}` : ""}</span></td>
                  <td className="text-muted" style={{ fontSize: 12, maxWidth: 340 }}>{t.explanation}</td>
                  <td style={{ minWidth: 200 }}>
                    <ReviewControls feedback={ratings.current(t.merchant_id, t.feedback)} open={openIds.has(t.merchant_id)} onToggle={() => toggle(t.merchant_id)}
                                    onRate={(v, r) => ratings.rate(t.merchant_id, v, r)} />
                  </td>
                  <td><button className="btn btn-ghost" onClick={() => onCopilot(t.merchant_id)}>Co-pilot →</button></td>
                </tr>
                {openIds.has(t.merchant_id) && (
                  <tr><td colSpan={7}><EvidencePanel merchantId={t.merchant_id} version={ratings.version} onProfile={onProfile ? () => onProfile(t.merchant_id) : undefined} /></td></tr>
                )}
                </Fragment>
              ))}
              {rows.length === 0 && (
                <tr><td colSpan={7} className="text-muted" style={{ textAlign: "center", padding: "var(--space-6)" }}>{product ? "No clients are pitched this product right now." : "No recommendations right now."}</td></tr>
              )}
            </tbody>
          </table>
        </Blueprint>
      )}
    </div>
  );
}
