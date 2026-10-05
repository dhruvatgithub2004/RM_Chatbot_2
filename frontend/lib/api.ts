import type { ChatMode, ChatMsg, GuardrailInfo, ClientDetail, Dashboard, DataStatus, DirectoryClient, DirectoryFilters, FilterOptions, Suggestion } from "./types";

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

export const api = {
  status: () => get<DataStatus>("/api/data/status"),
  dashboard: (filter: "all" | "opp", q: string) =>
    get<Dashboard>(`/api/dashboard?filter=${filter}&q=${encodeURIComponent(q)}`),
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
  suggestionProducts: () => get<{ product: string; count: number }[]>("/api/suggestions/products"),
  chat: async (
    scope: { kind: "portfolio" } | { kind: "client"; id: string },
    messages: ChatMsg[],
  ): Promise<{ reply: string; mode: ChatMode; llm_error?: string; guardrail?: GuardrailInfo }> => {
    const url = scope.kind === "portfolio" ? "/api/copilot/portfolio" : `/api/copilot/clients/${encodeURIComponent(scope.id)}`;
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
