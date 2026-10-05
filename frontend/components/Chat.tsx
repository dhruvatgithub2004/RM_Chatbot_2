"use client";
import { useEffect, useRef, useState } from "react";
import type { ChatMsg } from "@/lib/types";
import Blueprint from "./Blueprint";

interface Props {
  messages: ChatMsg[];
  chips: string[];
  placeholder: string;
  busy: boolean;
  onSend: (text: string) => void;
}

/** Inline **bold** only. */
function inline(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((p, i) =>
    p.startsWith("**") && p.endsWith("**") && p.length > 4 ? <strong key={i}>{p.slice(2, -2)}</strong> : p);
}

/** Minimal formatter for co-pilot replies: paragraphs, "- " / "• " bullets (one nesting level) and **bold**. */
function FormattedText({ text }: { text: string }) {
  const blocks: React.ReactNode[] = [];
  let items: { text: string; nested: boolean }[] = [];
  const flush = () => {
    if (!items.length) return;
    blocks.push(
      <ul key={`ul${blocks.length}`} style={{ margin: "4px 0", paddingLeft: 18, display: "flex", flexDirection: "column", gap: 3 }}>
        {items.map((it, i) => <li key={i} style={{ marginLeft: it.nested ? 16 : 0 }}>{inline(it.text)}</li>)}
      </ul>);
    items = [];
  };
  for (const line of text.split("\n")) {
    const m = line.match(/^(\s*)[-•*]\s+(.*)$/);
    if (m) { items.push({ text: m[2], nested: m[1].length >= 2 }); continue; }
    flush();
    if (line.trim()) blocks.push(<p key={`p${blocks.length}`} style={{ margin: "4px 0" }}>{inline(line)}</p>);
  }
  flush();
  return <>{blocks}</>;
}

/** Chat card shared by the portfolio and merchant co-pilots (same markup as the design). */
export default function Chat({ messages, chips, placeholder, busy, onSend }: Props) {
  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ block: "end" }); }, [messages, busy]);

  const send = (text: string) => {
    const t = text.trim();
    if (!t || busy) return;
    setInput("");
    onSend(t);
  };

  return (
    <Blueprint style={{ display: "flex", flexDirection: "column", height: 520, padding: 0 }}>
      <div style={{ flex: 1, overflowY: "auto", padding: "var(--space-4)", display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
        {messages.map((m, i) => {
          const user = m.role === "user";
          return (
            <div key={i} style={{ display: "flex", justifyContent: user ? "flex-end" : "flex-start" }}>
              <div style={{ maxWidth: "78%" }}>
                <div style={{ padding: "var(--space-2) var(--space-3)", fontSize: 14, lineHeight: 1.45, whiteSpace: "pre-wrap",
                              background: user ? "var(--color-accent)" : "var(--color-surface)", color: user ? "var(--color-bg)" : "var(--color-text)",
                              border: "1px solid var(--color-divider)" }}>{user ? m.text : <FormattedText text={m.text} />}</div>
                {m.mode === "llm" && <div className="text-muted" style={{ fontSize: 10, marginTop: 2 }}>AI-generated · may contain errors · verify before acting</div>}
                {m.guardrail?.blocked && m.mode === "guard" && <div className="text-muted" style={{ fontSize: 10, marginTop: 2 }}>Guardrail: {m.guardrail.rail}</div>}
                {m.guardrail?.blocked && m.mode === "data" && <div className="text-muted" style={{ fontSize: 10, marginTop: 2 }}>The AI answer failed an accuracy check · showing a data-only answer</div>}
                {m.mode === "data" && !m.guardrail?.blocked && <div className="text-muted" style={{ fontSize: 10, marginTop: 2 }}>Data-only answer · LLM not connected</div>}
              </div>
            </div>
          );
        })}
        {busy && (
          <div style={{ display: "flex" }}>
            <div className="text-muted" style={{ padding: "var(--space-2) var(--space-3)", fontSize: 14, border: "1px solid var(--color-divider)", background: "var(--color-surface)" }}>Thinking…</div>
          </div>
        )}
        <div ref={endRef} />
      </div>
      <div style={{ padding: "var(--space-3)", borderTop: "1px solid var(--color-divider)" }}>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: "var(--space-2)" }}>
          {chips.map((label) => (
            <button key={label} className="tag tag-outline" style={{ cursor: "pointer", borderWidth: 1, background: "transparent", font: "inherit", fontSize: 11 }}
                    onClick={() => send(label)} disabled={busy}>{label}</button>
          ))}
        </div>
        <div style={{ display: "flex", gap: "var(--space-2)" }}>
          <input className="input" placeholder={placeholder} value={input} onChange={(e) => setInput(e.target.value)}
                 onKeyDown={(e) => { if (e.key === "Enter") send(input); }} />
          <button className="btn btn-primary" onClick={() => send(input)} disabled={busy}>Send</button>
        </div>
        <div className="text-muted" style={{ fontSize: 10, marginTop: "var(--space-2)" }}>
          AI-generated answers can be wrong. Verify before acting. Data shown is synthetic.
        </div>
      </div>
    </Blueprint>
  );
}
