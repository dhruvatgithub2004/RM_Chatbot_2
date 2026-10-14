"use client";
import { useState } from "react";
import { fmtAed } from "@/lib/format";

export interface MixSlice { type: string; pct: number; txns: number; volume_aed: number }

// One fixed colour per card type, so a type never changes colour between clients. Hues are the first five slots of the validated
// categorical palette; the order was chosen so Debit (never 0%) sits between orange and yellow, which are too close in normal vision.
const COLOUR: Record<string, string> = {
  Mass: "#2a78d6", Premium: "#eb6834", Debit: "#1baf7a", "Super Premium": "#eda100", Business: "#e87ba4",
};
const FALLBACK = "#898781";
// Pairs that fail the normal-vision floor when they touch (orange beside magenta, orange beside yellow). The slice order avoids them
// when the client's mix allows it; otherwise the 2px gaps, the on-slice labels and the legend carry identity.
const CLASHES: [string, string][] = [["Premium", "Business"], ["Premium", "Super Premium"]];
const SIZE = 168, R = 76, C = SIZE / 2, MIN_LABEL_SHARE = 0.08;

const colourOf = (t: string) => COLOUR[t] ?? FALLBACK;

/** White or near-black text, whichever reads better on a slice colour. */
function inkOn(hex: string): string {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return 1.05 / (lum + 0.05) >= (lum + 0.05) / 0.0533 ? "#ffffff" : "#0b0b0b";      // contrast with white vs with #0b0b0b
}

function permutations<T>(xs: T[]): T[][] {
  if (xs.length <= 1) return [xs];
  return xs.flatMap((x, i) => permutations([...xs.slice(0, i), ...xs.slice(i + 1)]).map((rest) => [x, ...rest]));
}

/** Largest slice first, then reordered (at most 5! = 120 orders) so clashing colours do not touch, moving slices as little as needed. */
export function arrange<T extends { type: string }>(bySize: T[]): T[] {
  if (bySize.length <= 2) return bySize;
  const clashes = (order: T[]) => order.reduce((n, s, i) => {
    const next = order[(i + 1) % order.length].type;
    return n + CLASHES.filter(([a, b]) => (s.type === a && next === b) || (s.type === b && next === a)).length;
  }, 0);
  const moved = (order: T[]) => order.reduce((n, s, i) => n + Math.abs(i - bySize.indexOf(s)), 0);
  return permutations(bySize).reduce((best, o) => {
    const [cb, co] = [clashes(best), clashes(o)];
    return co < cb || (co === cb && moved(o) < moved(best)) ? o : best;
  }, bySize);
}

function wedge(start: number, end: number): string {
  const p = (a: number) => `${(C + R * Math.cos(a)).toFixed(2)} ${(C + R * Math.sin(a)).toFixed(2)}`;
  return `M ${C} ${C} L ${p(start)} A ${R} ${R} 0 ${end - start > Math.PI ? 1 : 0} 1 ${p(end)} Z`;
}

/** Card mix as a pie of each card type's share of the last 30 days' card volume, with a legend that is also the table of values. */
export default function CardMixPie({ mix }: { mix: MixSlice[] }) {
  const [active, setActive] = useState<string | null>(null);
  const total = mix.reduce((s, m) => s + m.volume_aed, 0);
  const slices = arrange(mix.filter((m) => m.volume_aed > 0).sort((a, b) => b.volume_aed - a.volume_aed));
  if (!slices.length || total <= 0) return <span className="text-muted">No POS data</span>;
  const legend = [...slices].sort((a, b) => b.volume_aed - a.volume_aed);
  const hovered = mix.find((m) => m.type === active);

  let angle = -Math.PI / 2;      // start at 12 o'clock, clockwise
  const wedges = slices.map((s) => {
    const share = s.volume_aed / total, start = angle, end = angle + share * 2 * Math.PI;
    angle = end;
    return { s, share, start, end, mid: (start + end) / 2 };
  });

  return (
    <div role="group" aria-label="Card mix by share of card volume, last 30 days">
      <div style={{ display: "flex", gap: "var(--space-4)", alignItems: "center", flexWrap: "wrap" }}>
        <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} style={{ flex: "none", overflow: "visible" }}>
          {wedges.map(({ s, share, start, end, mid }) => {
            const on = active === s.type, dim = active !== null && !on;
            const common = {
              fill: colourOf(s.type), stroke: "var(--color-bg)", strokeWidth: 2, tabIndex: 0, role: "img",
              "aria-label": `${s.type}, ${s.pct.toFixed(1)}% of volume`,
              style: { opacity: dim ? 0.45 : 1, transition: "opacity 120ms, transform 120ms", outline: "none",
                       transform: on ? `translate(${(3 * Math.cos(mid)).toFixed(2)}px, ${(3 * Math.sin(mid)).toFixed(2)}px)` : undefined },
              onMouseEnter: () => setActive(s.type), onMouseLeave: () => setActive(null), onFocus: () => setActive(s.type), onBlur: () => setActive(null),
            };
            const label = share >= MIN_LABEL_SHARE && (
              <text x={C + R * 0.62 * Math.cos(mid)} y={C + R * 0.62 * Math.sin(mid)} textAnchor="middle" dominantBaseline="central"
                    fontSize="12" fontWeight="600" fill={inkOn(colourOf(s.type))} pointerEvents="none">{Math.round(share * 100)}%</text>
            );
            return (
              <g key={s.type}>
                {share > 0.9999 ? <circle cx={C} cy={C} r={R} {...common} /> : <path d={wedge(start, end)} {...common} />}
                {label}
              </g>
            );
          })}
        </svg>

        <table style={{ borderCollapse: "collapse", fontSize: 13, flex: 1, minWidth: 190 }}>
          <caption className="text-muted" style={{ captionSide: "top", textAlign: "left", fontSize: 11, paddingBottom: 4 }}>
            Share of card volume, last 30 days
          </caption>
          <tbody>
            {legend.map((m) => (
              <tr key={m.type} onMouseEnter={() => setActive(m.type)} onMouseLeave={() => setActive(null)}
                  style={{ background: active === m.type ? "color-mix(in srgb, var(--color-text) 6%, transparent)" : undefined }}>
                <td style={{ padding: "3px 8px 3px 4px", width: 14 }}>
                  <span aria-hidden style={{ display: "inline-block", width: 10, height: 10, background: colourOf(m.type), verticalAlign: "middle" }} />
                </td>
                <th scope="row" style={{ textAlign: "left", fontWeight: 400, padding: "3px 8px 3px 0" }}>{m.type}</th>
                <td style={{ textAlign: "right", padding: "3px 4px", fontWeight: 600 }}>{m.pct.toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="text-muted" aria-live="polite" style={{ fontSize: 11, marginTop: "var(--space-2)", minHeight: 16 }}>
        {hovered ? `${hovered.type}: ${hovered.pct.toFixed(1)}% of card volume · ${fmtAed(hovered.volume_aed)}` : "Hover a slice or a row for the amount."}
      </div>
    </div>
  );
}
