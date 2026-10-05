"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fmtAed, fmtNum } from "@/lib/format";
import type { ClientDetail, DirectoryClient, DirectoryFilters, FilterOptions } from "@/lib/types";
import Blueprint, { ErrorCard, Loading, Row } from "./Blueprint";

interface Props {
  selectedId: string | null;
  onSelect: (id: string) => void;
  onBack: () => void;
  onSuggestions: () => void;
  onCopilot: () => void;
}

function FilterSelect({ label, all, value, options, onChange }: { label: string; all: string; value: string;
                       options: { value: string; count: number }[]; onChange: (v: string) => void }) {
  return (
    <label className="text-muted" style={{ fontSize: 11 }}>{label}
      <select className="input" style={{ marginTop: 2 }} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{all}</option>
        {options.map((o) => <option key={o.value} value={o.value}>{o.value} ({o.count})</option>)}
      </select>
    </label>
  );
}

const NO_FILTERS: DirectoryFilters = { balanceMin: "", balanceMax: "", segment: "", cardType: "", product: "" };

export default function Profile({ selectedId, onSelect, onBack, onSuggestions, onCopilot }: Props) {
  const [search, setSearch] = useState("");
  const [list, setList] = useState<DirectoryClient[]>([]);
  const [filters, setFilters] = useState<DirectoryFilters>(NO_FILTERS);
  const [options, setOptions] = useState<FilterOptions | null>(null);
  const [client, setClient] = useState<ClientDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let live = true;
    const t = setTimeout(() => {
      api.directory(search, filters).then((d) => live && setList(d)).catch((e) => live && setError(String(e.message)));
    }, search || filters.balanceMin || filters.balanceMax ? 200 : 0);
    return () => { live = false; clearTimeout(t); };
  }, [search, filters]);

  useEffect(() => { api.filterOptions().then(setOptions).catch(() => setOptions(null)); }, []);

  const setFilter = (k: keyof DirectoryFilters) => (v: string) => setFilters((f) => ({ ...f, [k]: v }));
  const filtered = Object.values(filters).some(Boolean);

  useEffect(() => {
    if (!selectedId) return;
    let live = true;
    setClient(null);
    api.client(selectedId).then((c) => live && (setClient(c), setError(null))).catch((e) => live && setError(String(e.message)));
    return () => { live = false; };
  }, [selectedId, tick]);

  const c = client;

  return (
    <div style={{ display: "flex", gap: "var(--space-6)" }}>
      <div style={{ width: 240, flex: "none" }}>
        <input className="input" style={{ marginBottom: "var(--space-3)" }} placeholder="Search merchants" value={search}
               onChange={(e) => setSearch(e.target.value)} />
        {options && (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)", marginBottom: "var(--space-3)" }}>
            <label className="text-muted" style={{ fontSize: 11 }}>Balance range (AED)
              <div style={{ display: "flex", gap: 6, marginTop: 2 }}>
                <input className="input" type="number" min={0} placeholder={`Min ${Math.floor(options.balance.min).toLocaleString("en-US")}`} value={filters.balanceMin}
                       onChange={(e) => setFilter("balanceMin")(e.target.value)} />
                <input className="input" type="number" min={0} placeholder={`Max ${Math.ceil(options.balance.max).toLocaleString("en-US")}`} value={filters.balanceMax}
                       onChange={(e) => setFilter("balanceMax")(e.target.value)} />
              </div>
            </label>
            <FilterSelect label="Segment" all="All segments" value={filters.segment} options={options.segment} onChange={setFilter("segment")} />
            <FilterSelect label="Card type" all="All card types" value={filters.cardType} options={options.card_type} onChange={setFilter("cardType")} />
            <FilterSelect label="Existing product" all="All products" value={filters.product} options={options.product} onChange={setFilter("product")} />
            {filtered && <button className="btn btn-ghost" onClick={() => setFilters(NO_FILTERS)}>Clear filters</button>}
          </div>
        )}
        <div className="text-muted" style={{ fontSize: 11, marginBottom: "var(--space-2)" }}>{list.length} merchant{list.length === 1 ? "" : "s"}</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 2, maxHeight: "calc(100vh - 140px)", overflowY: "auto" }}>
          {list.map((m) => {
            const active = m.merchant_id === selectedId;
            return (
              <button key={m.merchant_id} onClick={() => onSelect(m.merchant_id)}
                style={{ textAlign: "left", cursor: "pointer", padding: "var(--space-2) var(--space-3)", border: "1px solid var(--color-divider)",
                         borderRadius: "var(--radius-md)", background: active ? "var(--color-accent-100)" : "transparent",
                         color: active ? "var(--color-accent-800)" : "var(--color-text)", font: "inherit" }}>
                <div style={{ fontSize: 14, fontFamily: "var(--font-heading)" }}>{m.name}</div>
                <div className="text-muted" style={{ fontSize: 11 }}>{m.industry}</div>
              </button>
            );
          })}
          {list.length === 0 && <p className="text-muted" style={{ fontSize: 13 }}>No merchants match.</p>}
        </div>
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        {error ? (
          <ErrorCard message={error} onRetry={() => setTick((t) => t + 1)} />
        ) : !c ? (
          <Loading />
        ) : (
          <>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "var(--space-6)" }}>
              <div>
                <h1 style={{ marginBottom: 4 }}>{c.name}</h1>
                <div style={{ display: "flex", gap: "var(--space-2)", alignItems: "center" }}>
                  <span className="tag tag-outline">{c.industry}</span>
                  <span className="text-muted" style={{ fontSize: 13 }}>{c.city}</span>
                  {c.behaviour.is_dormant_now && (
                    <span className="tag tag-accent">Dormant · {c.behaviour.dormant_streak_days} days</span>
                  )}
                </div>
              </div>
              <button className="btn btn-secondary" onClick={onBack}>← Back to dashboard</button>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-4)", marginBottom: "var(--space-6)" }}>
              <Blueprint>
                <div className="card-kicker">Card &amp; POS</div>
                <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)", fontSize: 14 }}>
                  <Row label="Card no.">{c.card_pos.card_no}</Row>
                  <Row label="Card type">{c.card_pos.card_type}</Row>
                  <Row label="Monthly POS limit">{fmtAed(c.card_pos.monthly_pos_limit_aed)}</Row>
                  <Row label="Daily POS limit">{fmtAed(c.card_pos.daily_pos_limit_aed)}</Row>
                  <Row label="POS volume / mo">{fmtAed(c.card_pos.volume_t30)}</Row>
                  <Row label="POS frequency / mo">{c.card_pos.txn_t30 === null ? "—" : `${fmtNum(c.card_pos.txn_t30)} txns`}</Row>
                </div>
              </Blueprint>

              <Blueprint>
                <div className="card-kicker">Profile &amp; behavior</div>
                <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)", fontSize: 14, marginBottom: "var(--space-2)" }}>
                  <Row label="Balance">{fmtAed(c.profile.balance_aed)}</Row>
                  <Row label="Behavior / risk">{c.profile.risk_segment}</Row>
                  <Row label="Segment">{c.profile.segment}</Row>
                </div>
                <div className="card-kicker" style={{ marginTop: "var(--space-2)" }}>Existing products</div>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  {c.profile.existing_products.length === 0 ? (
                    <span className="text-muted">None on file</span>
                  ) : (
                    c.profile.existing_products.map((p) => <span className="tag tag-neutral" key={p}>{p}</span>)
                  )}
                </div>
              </Blueprint>
            </div>

            <div style={{ display: "flex", gap: "var(--space-3)", marginBottom: "var(--space-6)" }}>
              <button className="btn btn-secondary" onClick={onSuggestions}>View suggestions</button>
              <button className="btn btn-primary" onClick={onCopilot}>Ask co-pilot about this client</button>
            </div>

            <Blueprint style={{ marginBottom: "var(--space-4)" }}>
              <div className="card-kicker">Rate suggestion</div>
              <div style={{ display: "flex", gap: "var(--space-8)", alignItems: "baseline", margin: "var(--space-2) 0" }}>
                <div>
                  <div className="text-muted" style={{ fontSize: 11 }}>Current</div>
                  <div style={{ fontFamily: "var(--font-heading)", fontSize: 28 }}>{c.rate.current_pct.toFixed(2)}%</div>
                </div>
                <div style={{ fontSize: 20, color: "var(--color-accent)" }}>→</div>
                <div>
                  <div className="text-muted" style={{ fontSize: 11 }}>Suggested</div>
                  <div style={{ fontFamily: "var(--font-heading)", fontSize: 28, color: "var(--color-accent-700)" }}>{c.rate.change_recommended ? `${c.rate.suggested_pct.toFixed(2)}%` : "No change"}</div>
                </div>
              </div>
              <p className="card-body">
                {c.rate.rationale}
              </p>
            </Blueprint>

            <div style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr", gap: "var(--space-4)" }}>
              <Blueprint>
                <div className="card-kicker">Volume tracking (6 mo, AED k)</div>
                <div style={{ display: "flex", alignItems: "flex-end", gap: "var(--space-3)", height: 150, marginTop: "var(--space-3)" }}>
                  {c.volume_bars.map((bar) => (
                    <div key={bar.month_key} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 6, height: "100%", justifyContent: "flex-end" }}>
                      <div className="text-muted" style={{ fontSize: 10 }}>{Math.round(bar.volume_aed / 1000).toLocaleString("en-US")}</div>
                      <div style={{ width: "100%", background: "var(--color-accent-500)", height: `${bar.height_pct}%` }} />
                      <div className="text-muted" style={{ fontSize: 11 }}>{bar.month}</div>
                    </div>
                  ))}
                  {c.volume_bars.length === 0 && <span className="text-muted">No POS data</span>}
                </div>
              </Blueprint>

              <Blueprint>
                <div className="card-kicker">Card mix analysis</div>
                <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)", marginTop: "var(--space-2)" }}>
                  {c.card_mix.map((mix) => (
                    <div key={mix.type}>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 4 }}>
                        <span>{mix.type}</span>
                        <span className="text-muted">{fmtNum(mix.txns)} txns</span>
                      </div>
                      <div style={{ height: 8, background: "var(--color-surface)", border: "1px solid var(--color-divider)" }}>
                        <div style={{ height: "100%", width: `${mix.pct}%`, background: "var(--color-accent)" }} />
                      </div>
                    </div>
                  ))}
                  {c.card_mix.length === 0 && <span className="text-muted">No POS data</span>}
                </div>
              </Blueprint>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
