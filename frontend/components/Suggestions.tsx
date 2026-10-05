"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Suggestion } from "@/lib/types";
import Blueprint, { ErrorCard, Loading } from "./Blueprint";

export default function Suggestions({ onCopilot }: { onCopilot: (id: string) => void }) {
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
              <tr><th>Rank</th><th>Merchant</th><th>Recommended product</th><th>Why</th><th></th></tr>
            </thead>
            <tbody>
              {rows.map((t) => (
                <tr key={t.merchant_id}>
                  <td style={{ fontFamily: "var(--font-heading)" }}>{t.rank}</td>
                  <td>{t.name}<div className="text-muted" style={{ fontSize: 11 }}>{t.industry}</div></td>
                  <td><span className="tag tag-accent">{t.category} — {t.product}{t.amount_aed ? ` · AED ${Math.round(t.amount_aed).toLocaleString("en-US")}` : ""}</span></td>
                  <td className="text-muted" style={{ fontSize: 12, maxWidth: 340 }}>{t.explanation}</td>
                  <td><button className="btn btn-ghost" onClick={() => onCopilot(t.merchant_id)}>Co-pilot →</button></td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr><td colSpan={5} className="text-muted" style={{ textAlign: "center", padding: "var(--space-6)" }}>{product ? "No clients are pitched this product right now." : "No recommendations right now."}</td></tr>
              )}
            </tbody>
          </table>
        </Blueprint>
      )}
    </div>
  );
}
