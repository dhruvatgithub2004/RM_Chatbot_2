"use client";
import { Fragment, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fmtAed } from "@/lib/format";
import type { ClientDecision, Dashboard as DashboardData, DashboardClient, DecisionKind, Feedback } from "@/lib/types";
import ActNow from "./ActNow";
import CrossSell from "./CrossSell";
import TopPerformers from "./TopPerformers";
import DormantReactivation from "./DormantReactivation";
import Blueprint, { ErrorCard, Loading } from "./Blueprint";
import { EvidencePanel, FeedbackSummaryStrip, ReviewControls, useRatings } from "./Review";

const DECISION_LABEL: Record<DecisionKind, string> = { lending: "Lending", cross_sell: "Cross-sell", retention: "Retain", engage: "Engage", none: "No action" };
// The dashboard shows only the "Act now" list for now. Set to true to bring back the Opportunities / All tabs, search, board and tables below it.
const SHOW_ALL_MERCHANTS = false;
const BOARD_SIZE = 9;   // top flagged clients shown as boxes on the Opportunities tab; the rest follow in the table
// AED amounts, percentages and day/month counts in a flag reason. The comparison window ("vs prior 30 days") is not a finding, so it is skipped.
const FLAG_NUMBER = /((?<!prior )(?<![\d.,])(?:AED\s?\d[\d,.]*[kM]?|\d[\d,.]*\s?%|\d[\d,.]*\s(?:days?|months?)))/g;

/** A flag reason with its figures emphasised. */
function Flag({ text, size }: { text: string; size: number }) {
  return (
    <span style={{ fontSize: size, lineHeight: 1.4 }}>
      {text.split(FLAG_NUMBER).map((part, i) =>
        i % 2 ? <strong key={i} style={{ color: "var(--color-accent-700)", fontWeight: 700 }}>{part}</strong> : part)}
    </span>
  );
}

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

/** What the cards and tables need to let the RM look into a suggestion and rate it. */
interface Review {
  onView: (id: string) => void;
  rating: (c: DashboardClient) => Feedback | null;
  isOpen: (id: string) => boolean;
  toggle: (id: string) => void;
  rate: (id: string, verdict: Feedback["verdict"] | null, reason?: string | null) => Promise<void>;
  version: number;
}

/** The "Why this?" and Useful? Yes / No controls for one client, for clients that have something suggested. */
function Controls({ c, rv }: { c: DashboardClient; rv: Review }) {
  if (!c.decision || c.decision.kind === "none") return null;
  return <ReviewControls feedback={rv.rating(c)} open={rv.isOpen(c.merchant_id)} onToggle={() => rv.toggle(c.merchant_id)}
                         onRate={(v, r) => rv.rate(c.merchant_id, v, r)} />;
}

/** One box on the Opportunities board. The whole box opens the client profile. */
function OpportunityCard({ c, rv }: { c: DashboardClient; rv: Review }) {
  const onView = rv.onView;
  return (
    <Blueprint className="opp-card" onClick={() => onView(c.merchant_id)}
               style={{ gap: "var(--space-3)", padding: "var(--space-4)", gridColumn: rv.isOpen(c.merchant_id) ? "1 / -1" : undefined }}>
      <div style={{ display: "flex", gap: "var(--space-3)", alignItems: "baseline" }}>
        <span style={{ fontFamily: "var(--font-heading)", fontSize: 28, lineHeight: 1, color: "var(--color-accent)" }}>{c.rank}</span>
        <div style={{ minWidth: 0 }}>
          <div className="card-title">{c.name}</div>
          <div className="text-muted" style={{ fontSize: 11 }}>{c.industry} · {c.city}</div>
        </div>
      </div>
      <div style={{ flex: 1 }}>
        <div className="card-kicker" style={{ marginBottom: 2 }}>Flag</div>
        <Flag text={c.reason} size={15} />
      </div>
      <div>
        <div className="card-kicker" style={{ marginBottom: 4 }}>Suggested action</div>
        <Decision d={c.decision} />
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
        <div>
          <button className="btn btn-ghost" onClick={(e) => { e.stopPropagation(); onView(c.merchant_id); }}>View profile →</button>
        </div>
        <Controls c={c} rv={rv} />
      </div>
      {rv.isOpen(c.merchant_id) && <EvidencePanel merchantId={c.merchant_id} version={rv.version} onProfile={() => onView(c.merchant_id)} />}
    </Blueprint>
  );
}

function ClientTable({ clients, rv }: { clients: DashboardClient[]; rv: Review }) {
  const onView = rv.onView;
  return (
    <Blueprint style={{ padding: 0 }}>
      <table className="table">
        <thead>
          <tr><th>Rank</th><th>Client</th><th>Industry</th><th>Flag</th><th>Suggested action</th><th>Review</th><th></th></tr>
        </thead>
        <tbody>
          {clients.map((c) => (
            <Fragment key={c.merchant_id}>
            <tr>
              <td style={{ fontFamily: "var(--font-heading)" }}>{c.rank}</td>
              <td>
                <button className="link-plain" onClick={() => onView(c.merchant_id)}>{c.name}</button>
                <div className="text-muted" style={{ fontSize: 11 }}>{c.city}</div>
              </td>
              <td>{c.industry}</td>
              <td className="text-muted" style={{ maxWidth: 280 }}><Flag text={c.reason} size={13} /></td>
              <td style={{ maxWidth: 300 }}><Decision d={c.decision} /></td>
              <td style={{ minWidth: 200 }}><Controls c={c} rv={rv} /></td>
              <td><button className="btn btn-ghost" onClick={() => onView(c.merchant_id)}>View →</button></td>
            </tr>
            {rv.isOpen(c.merchant_id) && (
              <tr><td colSpan={7}><EvidencePanel merchantId={c.merchant_id} version={rv.version} onProfile={() => onView(c.merchant_id)} /></td></tr>
            )}
            </Fragment>
          ))}
          {clients.length === 0 && (
            <tr><td colSpan={7} className="text-muted" style={{ textAlign: "center", padding: "var(--space-6)" }}>No clients match.</td></tr>
          )}
        </tbody>
      </table>
    </Blueprint>
  );
}

export default function Dashboard({ onView }: { onView: (id: string) => void }) {
  const [filter, setFilter] = useState<"all" | "opp">("opp");
  const [search, setSearch] = useState("");
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const [openIds, setOpenIds] = useState<Set<string>>(new Set());
  const ratings = useRatings();
  // Demo deep link: /?review=MER2074 opens that client's "Why this?" panel on load.
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("review");
    if (id) setOpenIds(new Set([id]));
  }, []);
  const rv: Review = {
    onView,
    rating: (c) => ratings.current(c.merchant_id, c.feedback),
    isOpen: (id) => openIds.has(id),
    toggle: (id) => setOpenIds((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; }),
    rate: ratings.rate,
    version: ratings.version,
  };

  useEffect(() => {
    let live = true;
    const t = setTimeout(() => {
      api.dashboard(filter, search).then((d) => live && (setData(d), setError(null))).catch((e) => live && setError(String(e.message)));
    }, search ? 200 : 0);
    return () => { live = false; clearTimeout(t); };
  }, [filter, search, tick]);

  const options: { key: "all" | "opp"; label: string }[] = [
    { key: "opp", label: "Opportunities" },
    { key: "all", label: "All" },
  ];
  const board = data && filter === "opp" ? data.clients.slice(0, BOARD_SIZE) : [];
  const rest = data && filter === "opp" ? data.clients.slice(BOARD_SIZE) : data?.clients ?? [];

  return (
    <div>
      <h1 style={{ marginBottom: 4 }}>Dashboard</h1>
      <p className="text-muted" style={{ marginBottom: "var(--space-6)" }}>
        {data ? data.flagged_count : "…"} clients flagged for attention this week
      </p>
      <CrossSell onView={onView} />
      <ActNow onView={onView} />
      <TopPerformers onView={onView} />
      <DormantReactivation onView={onView} />
      {SHOW_ALL_MERCHANTS && (<>
      <div className="card-kicker" style={{ marginBottom: "var(--space-2)" }}>All merchants</div>
      <p className="text-muted" style={{ fontSize: 11, marginTop: 0, marginBottom: "var(--space-4)" }}>
        {data?.decisions_source === "llm"
          ? "Suggested action: decided by the AI suggestion engine, checked in code against the product catalogue. The RM decides."
          : "Suggested action: rule-based on the supplied data (AI suggestions not generated yet)"}
      </p>
      <FeedbackSummaryStrip version={ratings.version} />

      <div style={{ display: "flex", gap: "var(--space-4)", alignItems: "center", marginBottom: "var(--space-4)", flexWrap: "wrap" }}>
        <div className="seg">
          {options.map((o) => (
            <label className="seg-opt" key={o.key}>
              <input type="radio" name="filter" checked={filter === o.key} onChange={() => { setData(null); setFilter(o.key); }} />
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
      ) : filter === "opp" ? (
        <>
          <div className="card-kicker" style={{ marginBottom: "var(--space-3)" }}>Top {board.length} to act on · ranked by suggestion priority</div>
          {board.length === 0 ? (
            <p className="text-muted">No opportunities match.</p>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", alignItems: "start", gap: "var(--space-6)", marginBottom: "var(--space-8)" }}>
              {board.map((c) => <OpportunityCard key={c.merchant_id} c={c} rv={rv} />)}
            </div>
          )}
          {rest.length > 0 && (
            <>
              <div className="card-kicker" style={{ marginBottom: "var(--space-3)" }}>More opportunities ({rest.length})</div>
              <ClientTable clients={rest} rv={rv} />
            </>
          )}
        </>
      ) : (
        <ClientTable clients={rest} rv={rv} />
      )}
      </>)}
    </div>
  );
}
