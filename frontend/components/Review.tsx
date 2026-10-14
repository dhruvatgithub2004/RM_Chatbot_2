"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fmtAed } from "@/lib/format";
import type { Evidence, Feedback, FeedbackSummary, RatingSplit } from "@/lib/types";

export const NOT_USEFUL_REASONS = ["Already offered", "Not relevant for this client", "Figures look wrong", "Bad timing", "Other"];

/** Ratings the RM has just given, layered over what the server sent, and a counter that tells the panels and the summary to refresh. */
export function useRatings() {
  const [local, setLocal] = useState<Record<string, Feedback | null>>({});
  const [version, setVersion] = useState(0);
  const current = (id: string, fromServer?: Feedback | null): Feedback | null => (id in local ? local[id] : fromServer ?? null);
  const rate = async (id: string, verdict: Feedback["verdict"] | null, reason?: string | null) => {
    if (verdict === null) {
      await api.clearRating(id);
      setLocal((m) => ({ ...m, [id]: null }));
    } else {
      const saved = await api.rate(id, verdict, reason);
      setLocal((m) => ({ ...m, [id]: saved }));
    }
    setVersion((v) => v + 1);
  };
  return { current, rate, version };
}

const stop = (e: React.SyntheticEvent) => e.stopPropagation();

/** "Why this?" plus Useful? Yes / No. Clicking a chosen answer again removes the rating. A "No" offers an optional reason. */
export function ReviewControls({ feedback, open, onToggle, onRate }: {
  feedback: Feedback | null;
  open: boolean;
  onToggle: () => void;
  onRate: (verdict: Feedback["verdict"] | null, reason?: string | null) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const act = async (verdict: Feedback["verdict"] | null, reason?: string | null) => {
    setBusy(true);
    setError(null);
    try { await onRate(verdict, reason); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const answer = (label: string, verdict: Feedback["verdict"]) => {
    const on = feedback?.verdict === verdict;
    return (
      <button className={on ? "btn btn-primary" : "btn btn-secondary"} aria-pressed={on} disabled={busy} style={{ fontSize: 12, padding: "1px 10px" }}
              onClick={(e) => { stop(e); act(on ? null : verdict); }}>{label}</button>
    );
  };
  return (
    <div onClick={stop} style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
      <button className="btn btn-ghost" aria-expanded={open} onClick={(e) => { stop(e); onToggle(); }}>{open ? "Hide details" : "Why this?"}</button>
      <span className="text-muted" style={{ fontSize: 11 }}>Useful?</span>
      {answer("Yes", "useful")}
      {answer("No", "not_useful")}
      {feedback?.verdict === "not_useful" && (
        <select className="input" aria-label="Why was it not useful?" disabled={busy} value={feedback.reason ?? ""}
                style={{ fontSize: 12, padding: "1px 6px", width: "auto" }} onChange={(e) => act("not_useful", e.target.value || null)}>
          <option value="">Why not? (optional)</option>
          {NOT_USEFUL_REASONS.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
      )}
      {error && <span role="alert" style={{ fontSize: 11 }}>Could not save: {error}</span>}
    </div>
  );
}

function ratedText(x: RatingSplit, what: string) {
  return x.rated ? `${x.useful} of ${x.rated} ${what} rated useful` : `no ${what} rated yet`;
}

function shareText(x: RatingSplit) {
  return x.rated ? `${x.useful} of ${x.rated} useful` : "none rated yet";
}

/** The data behind a client's current suggestion, and what the code checked. Everything but the explanation text is computed from data. */
export function EvidencePanel({ merchantId, version, onProfile }: { merchantId: string; version: number; onProfile?: () => void }) {
  const [ev, setEv] = useState<Evidence | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    api.evidence(merchantId).then((e) => live && (setEv(e), setError(null))).catch((e) => live && setError(String(e.message)));
    return () => { live = false; };
  }, [merchantId, version]);

  if (error) return <div className="review-panel" onClick={stop} role="alert">Could not load the details: {error}</div>;
  if (!ev) return <div className="review-panel text-muted" onClick={stop}>Loading the evidence…</div>;
  const s = ev.suggestion;
  if (!s) return <div className="review-panel text-muted" onClick={stop}>{ev.message}</div>;
  const check = ev.explanation_check;
  const record = ev.track_record;
  return (
    <div className="review-panel" onClick={stop}>
      <section>
        <div className="card-kicker">What is suggested</div>
        <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
          <span className="tag tag-accent">{s.kind_label}</span>
          <strong>{s.product ?? "Retention call"}</strong>
          {s.amount_aed ? <span>· {fmtAed(s.amount_aed)}</span> : null}
          <span className="tag tag-outline" style={{ fontSize: 10 }}>{s.source === "llm" ? "AI" : "Rules"}</span>
        </div>
        <div className="text-muted">{s.how_decided}</div>
        {s.note && <div className="text-muted">Note from the checks when it was made: {s.note}</div>}
      </section>

      <section>
        <div className="card-kicker">Its explanation, as written</div>
        <div>{s.why}</div>
        {s.next_action && <div><strong>Next step:</strong> {s.next_action}</div>}
        {check && (
          <div style={{ marginTop: 4 }}>
            <span className="tag tag-outline" style={{ fontSize: 10, marginRight: 6 }}>{check.unverified.length ? "⚠ Check" : "✓ Figures match"}</span>
            {check.summary}
          </div>
        )}
      </section>

      <section>
        <div className="card-kicker">The client's data behind it (as of {ev.as_of_date})</div>
        <dl style={{ margin: 0, display: "grid", gridTemplateColumns: "minmax(120px, 190px) 1fr", gap: "3px var(--space-3)" }}>
          {(ev.facts ?? []).map((f) => (
            <div key={f.label} style={{ display: "contents" }}>
              <dt className="text-muted" style={{ fontWeight: f.key ? 700 : 400 }}>{f.label}</dt>
              <dd style={{ margin: 0, fontWeight: f.key ? 600 : 400 }}>{f.value}</dd>
            </div>
          ))}
        </dl>
      </section>

      {(ev.signals ?? []).length > 0 && (
        <section>
          <div className="card-kicker">Attention signals</div>
          <ul style={{ margin: 0, paddingLeft: 16 }}>
            {ev.signals!.map((x) => <li key={x.text}>{x.text} <span className="text-muted">(+{Math.round(x.points)} points)</span></li>)}
          </ul>
        </section>
      )}

      {(ev.checks ?? []).length > 0 && (
        <section>
          <div className="card-kicker">Checked just now, on current data</div>
          <ul style={{ margin: 0, paddingLeft: 0, listStyle: "none" }}>
            {ev.checks!.map((c) => (
              <li key={c.text}>
                <strong>{c.ok ? "✓" : c.kind === "caution" ? "⚠" : "✗"}</strong>{" "}
                {c.ok ? c.text : c.kind === "caution" ? `Caution: not true. ${c.text}` : `Failed: ${c.text}`}
              </li>
            ))}
          </ul>
        </section>
      )}

      {record && (
        <section>
          <div className="card-kicker">How useful RMs have found this</div>
          <div>
            {ratedText(record.same_suggestion, `${s.product ?? s.kind_label} suggestions`)}; {ratedText(record.same_source, s.source === "llm" ? "AI-decided suggestions" : "rule-based suggestions")}.
          </div>
        </section>
      )}

      {onProfile && <div><button className="btn btn-secondary" onClick={(e) => { stop(e); onProfile(); }}>Open the client profile →</button></div>}
    </div>
  );
}

/** One line on how useful suggestions have been so far, overall and by who decided. */
export function FeedbackSummaryStrip({ version }: { version: number }) {
  const [sum, setSum] = useState<FeedbackSummary | null>(null);
  useEffect(() => {
    let live = true;
    api.feedbackSummary().then((x) => live && setSum(x)).catch(() => live && setSum(null));
    return () => { live = false; };
  }, [version]);
  if (!sum) return null;
  const o = sum.overall;
  return (
    <p className="text-muted" style={{ fontSize: 11, marginTop: 0, marginBottom: "var(--space-4)" }}>
      {o.rated === 0
        ? "No suggestions rated yet. Answer “Useful? Yes / No” on a suggestion to see how useful they have been."
        : `Rated so far: ${o.useful} useful, ${o.not_useful} not useful (${Math.round((o.useful_share ?? 0) * 100)}% useful). `
          + `AI-decided: ${shareText(sum.by_source.llm)}. Rule-based: ${shareText(sum.by_source.rules)}.`}
    </p>
  );
}
