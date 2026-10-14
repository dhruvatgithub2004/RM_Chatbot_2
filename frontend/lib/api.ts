import type { ActNowData, ChatMode, CrossSellData, TopPerformersData, DormantData, ChatMsg, GuardrailInfo, ClientDetail, Dashboard, DataStatus, DirectoryClient, DirectoryFilters, Evidence, Feedback, FeedbackSummary, FilterOptions, Suggestion } from "./types";

const CHAT_API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) {
    let msg = `${res.status}`;
    try {
      const body = await res.json();
      msg = body?.detail?.message ?? body?.detail ?? msg;
    } catch {}
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return res.json();
}

async function send<T>(method: "POST" | "DELETE", path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, { method, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!res.ok) {
    let msg = `${res.status}`;
    try {
      const j = await res.json();
      msg = j?.detail?.message ?? j?.detail ?? msg;
    } catch {}
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return res.json();
}

export const api = {
  status: () => get<DataStatus>("/api/data/status"),
  dashboard: (filter: "all" | "opp" | "churn" | "top" | "dormant", q: string) =>
    get<Dashboard>(`/api/dashboard?filter=${filter}&q=${encodeURIComponent(q)}`),
  actNow: () => get<ActNowData>("/api/dashboard/act-now"),
  crossSell: () => get<CrossSellData>("/api/dashboard/cross-sell"),
  topPerformers: () => get<TopPerformersData>("/api/dashboard/top-performers"),
  dormant: () => get<DormantData>("/api/dashboard/dormant"),
  directory: (q: string, f?: DirectoryFilters) => {
    const p = new URLSearchParams({ q });
    if (f?.balanceMin) p.set("balance_min", f.balanceMin);
    if (f?.balanceMax) p.set("balance_max", f.balanceMax);
    if (f?.segment) p.set("segment", f.segment);
    if (f?.cardType) p.set("card_type", f.cardType);
    if (f?.product) p.set("product", f.product);
    return get<DirectoryClient[]>(`/api/clients?${p}`);
  },
  filterOptions: () => get<FilterOptions>("/api/clients/filter-options"),
  client: (id: string) => get<ClientDetail>(`/api/clients/${encodeURIComponent(id)}`),
  suggestions: (product?: string) => get<Suggestion[]>(`/api/suggestions${product ? `?product=${encodeURIComponent(product)}` : ""}`),
  evidence: (id: string) => get<Evidence>(`/api/clients/${encodeURIComponent(id)}/evidence`),
  rate: (id: string, verdict: Feedback["verdict"], reason?: string | null) =>
    send<Feedback>("POST", `/api/clients/${encodeURIComponent(id)}/feedback`, { verdict, reason: reason ?? null }),
  clearRating: (id: string) => send<{ cleared: boolean }>("DELETE", `/api/clients/${encodeURIComponent(id)}/feedback`),
  feedbackSummary: () => get<FeedbackSummary>("/api/feedback/summary"),
  suggestionProducts: () => get<{ product: string; count: number }[]>("/api/suggestions/products"),
  chat: async (
    scope: { kind: "portfolio" } | { kind: "client"; id: string },
    messages: ChatMsg[],
  ): Promise<{ reply: string; mode: ChatMode; llm_error?: string; guardrail?: GuardrailInfo }> => {
    const path = scope.kind === "portfolio" ? "/api/copilot/portfolio" : `/api/copilot/clients/${encodeURIComponent(scope.id)}`;
    const url = `${CHAT_API_BASE}${path}`;
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: messages.slice(-12).map(({ role, text }) => ({ role, text })) }),
    });
    if (res.status === 429) throw new Error("Too many questions in a short time, please wait a moment and try again");
    if (!res.ok) throw new Error(`Co-pilot request failed (${res.status})`);
    return res.json();
  },
};
