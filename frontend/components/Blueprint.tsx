import type { CSSProperties, ReactNode } from "react";

/** Industry design-system card: hairline frame with four corner registration marks. */
export default function Blueprint({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <div className="card blueprint elev-sm" style={style}>
      <i className="corner tl" />
      <i className="corner tr" />
      <i className="corner bl" />
      <i className="corner br" />
      {children}
    </div>
  );
}

export function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
      <span className="text-muted">{label}</span>
      <span style={{ textAlign: "right" }}>{children}</span>
    </div>
  );
}

export function NotInData({ children = "Not in source data" }: { children?: ReactNode }) {
  return <span className="text-muted" style={{ fontStyle: "italic" }}>{children}</span>;
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return <p className="text-muted">{label}</p>;
}

export function ErrorCard({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <Blueprint style={{ maxWidth: 560 }}>
      <div className="card-kicker">Something went wrong</div>
      <p className="card-body">{message}</p>
      {onRetry && (
        <div>
          <button className="btn btn-secondary" onClick={onRetry}>Retry</button>
        </div>
      )}
    </Blueprint>
  );
}
