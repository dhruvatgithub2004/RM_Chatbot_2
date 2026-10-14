"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fmtAsOf } from "@/lib/format";
import type { ChatMsg, ClientDetail, CopilotMode, DataStatus, View } from "@/lib/types";
import Chat from "./Chat";
import Dashboard from "./Dashboard";
import Profile from "./Profile";
import Suggestions from "./Suggestions";

const NAV: { key: View; label: string }[] = [
  { key: "dashboard", label: "Dashboard" },
  { key: "profile", label: "Profile & analytics" },
  { key: "suggestions", label: "Suggestions" },
  { key: "copilot", label: "Co-pilot" },
];
const MERCHANT_CHIPS = ["Summarize this client", "Any risk flags?", "What's the best cross-sell?", "Rate recommendation?"];
const GENERAL_CHIPS = ["Which clients are flagged?", "Lending opportunities?", "Cross-sell candidates?", "Portfolio summary"];

export default function App() {
  const [view, setView] = useState<View>("dashboard");
  const [copilotMode, setCopilotMode] = useState<CopilotMode>("general");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedName, setSelectedName] = useState<string>("");
  const [status, setStatus] = useState<DataStatus | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [generalChat, setGeneralChat] = useState<ChatMsg[]>([]);
  const [chatByClient, setChatByClient] = useState<Record<string, ChatMsg[]>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // Deep links for demos: /?view=profile&client=MER2005  |  /?view=copilot&mode=merchant&client=MER2005
    const q = new URLSearchParams(window.location.search);
    const v = q.get("view") as View | null;
    if (v && NAV.some((n) => n.key === v)) setView(v);
    if (q.get("mode") === "merchant") setCopilotMode("merchant");
    const cid = q.get("client");
    if (cid) { setSelectedId(cid); api.client(cid).then((c) => setSelectedName(c.name)).catch(() => {}); }
    api.status().then(setStatus).catch(() => setBackendError("Cannot reach the API. Start the backend (uvicorn app.main:app) and reload."));
    api.directory("").then((d) => {
      if (d.length) { setSelectedId((cur) => cur ?? d[0].merchant_id); setSelectedName((cur) => cur || d[0].name); }
    }).catch(() => {});
  }, []);

  const select = useCallback((id: string) => {
    setSelectedId(id);
    api.client(id).then((c: ClientDetail) => setSelectedName(c.name)).catch(() => {});
  }, []);

  const go = (v: View, mode?: CopilotMode) => { setView(v); if (mode) setCopilotMode(mode); };
  const openProfile = (id: string) => { select(id); go("profile"); };
  const openMerchantCopilot = (id: string) => { select(id); go("copilot", "merchant"); };

  const ask = async (text: string, scope: "portfolio" | "client") => {
    const id = selectedId;
    if (scope === "client" && !id) return;
    const prev = scope === "portfolio" ? generalChat : chatByClient[id as string] ?? [];
    const next: ChatMsg[] = [...prev, { role: "user", text }];
    const store = (msgs: ChatMsg[]) =>
      scope === "portfolio" ? setGeneralChat(msgs) : setChatByClient((m) => ({ ...m, [id as string]: msgs }));
    store(next);
    setBusy(true);
    try {
      const r = await api.chat(scope === "portfolio" ? { kind: "portfolio" } : { kind: "client", id: id as string }, next);
      store([...next, { role: "bot", text: r.reply, mode: r.mode, guardrail: r.guardrail }]);
    } catch (e) {
      store([...next, { role: "bot", text: `Sorry — I couldn't get an answer (${(e as Error).message}).` }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: "flex", height: "100vh", background: "var(--color-bg)", color: "var(--color-text)", fontFamily: "var(--font-body)", overflow: "hidden" }}>
      <div style={{ width: 230, flex: "none", borderRight: "1px solid var(--color-divider)", display: "flex", flexDirection: "column", padding: "var(--space-4)", gap: "var(--space-6)" }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 20 }}>InfoRM</h2>
          <div style={{ fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--color-accent-700)" }}>RM Co-pilot</div>
        </div>
        <div>
          {NAV.map((n) => {
            const active = view === n.key;
            return (
              <button key={n.key} onClick={() => go(n.key, n.key === "copilot" ? "general" : undefined)}
                style={{ display: "block", width: "100%", textAlign: "left", fontFamily: "var(--font-heading)", fontSize: 14, cursor: "pointer",
                         padding: "var(--space-2) var(--space-3)", border: "1px solid transparent", borderRadius: "var(--radius-md)", marginBottom: 2,
                         background: active ? "var(--color-accent-100)" : "transparent", color: active ? "var(--color-accent-800)" : "var(--color-text)" }}>
                {n.label}
              </button>
            );
          })}
        </div>
        <div style={{ marginTop: "auto" }} title={status?.disclaimer}>
          <span className="tag tag-outline" style={{ whiteSpace: "normal" }}>
            {status?.as_of_date ? `Data as of ${fmtAsOf(status.as_of_date)} · Synthetic` : "Synthetic data"}
          </span>
        </div>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "var(--space-8)" }}>
        {backendError ? (
          <div className="card blueprint" style={{ maxWidth: 560 }}>
            <i className="corner tl" /><i className="corner tr" /><i className="corner bl" /><i className="corner br" />
            <div className="card-kicker">Backend unavailable</div>
            <p className="card-body">{backendError}</p>
          </div>
        ) : (
          <>
            {view === "dashboard" && <Dashboard onView={openProfile} />}
            {view === "profile" && (
              <Profile selectedId={selectedId} onSelect={select} onBack={() => go("dashboard")}
                       onSuggestions={() => go("suggestions")} onCopilot={() => go("copilot", "merchant")} />
            )}
            {view === "suggestions" && <Suggestions onCopilot={openMerchantCopilot} onProfile={openProfile} />}
            {view === "copilot" && (
              <div>
                {copilotMode === "general" ? (
                  <>
                    <h1 style={{ marginBottom: 4 }}>Co-pilot</h1>
                    <p className="text-muted" style={{ marginBottom: "var(--space-6)" }}>Ask about any client across the portfolio</p>
                  </>
                ) : (
                  <>
                    <h1 style={{ marginBottom: 4 }}>Co-pilot — {selectedName}</h1>
                    <p className="text-muted" style={{ marginBottom: "var(--space-6)" }}>Scoped to this merchant only</p>
                  </>
                )}
                <div style={{ maxWidth: 720 }}>
                  {copilotMode === "general" ? (
                    <Chat messages={generalChat} chips={GENERAL_CHIPS} placeholder="Ask about any client…" busy={busy} onSend={(t) => ask(t, "portfolio")} />
                  ) : (
                    <Chat key={selectedId} messages={(selectedId && chatByClient[selectedId]) || []} chips={MERCHANT_CHIPS}
                          placeholder="Ask about this client…" busy={busy} onSend={(t) => ask(t, "client")} />
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
