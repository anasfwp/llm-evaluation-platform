import type { ReactNode } from "react";
import { ApiError } from "../api/client";
import type { RunStatus } from "../api/types";

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <p className="muted" role="status">
      {label}
    </p>
  );
}

export function ErrorMessage({ error }: { error: unknown }) {
  if (!error) return null;
  const apiError = error instanceof ApiError ? error : null;
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div className="alert" role="alert">
      <strong>{apiError?.status === 404 ? "Not found" : "Something went wrong"}</strong>
      <div>{message}</div>
      {apiError && apiError.details.length > 0 && (
        <ul>
          {apiError.details.map((detail, i) => (
            <li key={i}>
              {detail.field && <code>{detail.field}</code>} {detail.message}
            </li>
          ))}
        </ul>
      )}
      {apiError?.requestId && <div className="muted">Request ID: {apiError.requestId}</div>}
    </div>
  );
}

/** Async section: shows a spinner on first load, an error, or the content. */
export function AsyncBlock<T>({
  state,
  children,
}: {
  state: { data: T | undefined; error: unknown; loading: boolean };
  children: (data: T) => ReactNode;
}) {
  if (state.error) return <ErrorMessage error={state.error} />;
  if (state.data === undefined) return state.loading ? <Loading /> : null;
  return (
    <div style={{ opacity: state.loading ? 0.6 : 1, transition: "opacity 0.15s" }}>
      {children(state.data)}
    </div>
  );
}

type Tone = "good" | "bad" | "neutral";

/** A state indicator: icon + label, never colour alone. */
export function Badge({ tone, icon, children }: { tone: Tone; icon: string; children: ReactNode }) {
  return (
    <span className={`badge ${tone}`}>
      <span className="icon" aria-hidden="true">
        {icon}
      </span>
      {children}
    </span>
  );
}

const RUN_STATUS: Record<RunStatus, [Tone, string]> = {
  queued: ["neutral", "○"],
  running: ["neutral", "◐"],
  completed: ["good", "✓"],
  failed: ["bad", "✕"],
  cancelled: ["neutral", "⊘"],
};

export function RunStatusBadge({ status }: { status: RunStatus }) {
  const [tone, icon] = RUN_STATUS[status];
  return (
    <Badge tone={tone} icon={icon}>
      {status}
    </Badge>
  );
}

export function PassBadge({ passed, failText = "Regressed", passText = "No regressions" }: {
  passed: boolean;
  failText?: string;
  passText?: string;
}) {
  return passed ? (
    <Badge tone="good" icon="✓">
      {passText}
    </Badge>
  ) : (
    <Badge tone="bad" icon="✕">
      {failText}
    </Badge>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="card stat">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {hint && <div className="muted">{hint}</div>}
    </div>
  );
}

export function Pager({
  total,
  limit,
  offset,
  onChange,
}: {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
}) {
  if (total <= limit) return null;
  const page = Math.floor(offset / limit) + 1;
  const pages = Math.ceil(total / limit);
  return (
    <nav className="pager" aria-label="Pagination">
      <button disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>
        Previous
      </button>
      <span>
        Page {page} of {pages} ({total} items)
      </span>
      <button disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>
        Next
      </button>
    </nav>
  );
}

export function Tabs<T extends string>({
  tabs,
  active,
  onChange,
  label,
}: {
  tabs: readonly { id: T; label: string }[];
  active: T;
  onChange: (id: T) => void;
  label: string;
}) {
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          role="tab"
          id={`tab-${tab.id}`}
          aria-selected={tab.id === active}
          aria-controls={`panel-${tab.id}`}
          tabIndex={tab.id === active ? 0 : -1}
          onClick={() => onChange(tab.id)}
          onKeyDown={(event) => {
            const index = tabs.findIndex((t) => t.id === active);
            const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
            if (!step) return;
            const next = tabs[(index + step + tabs.length) % tabs.length]!;
            onChange(next.id);
            document.getElementById(`tab-${next.id}`)?.focus();
          }}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

export function TabPanel({ id, children }: { id: string; children: ReactNode }) {
  return (
    <div role="tabpanel" id={`panel-${id}`} aria-labelledby={`tab-${id}`}>
      {children}
    </div>
  );
}
