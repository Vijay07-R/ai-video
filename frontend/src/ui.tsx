import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import type { Job, StageStatus } from "./types";

/** Tiny hash router: #/path/segments */
export function useRoute(): string[] {
  const read = () => window.location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const on = () => setRoute(read());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

export const go = (path: string) => {
  window.location.hash = `#/${path}`;
};

/** Load data, optionally polling. Returns [data, error, reload]. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[], pollMs?: number | ((d: T | undefined) => number | undefined)) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<string>();
  const dataRef = useRef<T>();
  const reload = useCallback(async () => {
    try {
      const d = await fn();
      dataRef.current = d;
      setData(d);
      setError(undefined);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => {
    let timer: number | undefined;
    let alive = true;
    const tick = async () => {
      await reload();
      if (!alive) return;
      const ms = typeof pollMs === "function" ? pollMs(dataRef.current) : pollMs;
      if (ms) timer = window.setTimeout(tick, ms);
    };
    tick();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [reload]); // eslint-disable-line react-hooks/exhaustive-deps
  return [data, error, reload] as const;
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-sand-100">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-sand-400">{subtitle}</p>}
      </div>
      {actions && <div className="flex gap-2">{actions}</div>}
    </div>
  );
}

const STATUS_STYLE: Record<string, string> = {
  completed: "bg-emerald-900/50 text-emerald-300",
  skipped: "bg-ink-700 text-sand-400",
  processing: "bg-mane-500/20 text-mane-300",
  running: "bg-mane-500/20 text-mane-300",
  generating: "bg-mane-500/20 text-mane-300",
  queued: "bg-sky-900/40 text-sky-300",
  waiting: "bg-ink-800 text-sand-400",
  paused: "bg-amber-900/40 text-amber-300",
  awaiting_approval: "bg-violet-900/40 text-violet-300",
  failed: "bg-red-900/40 text-red-300",
  cancelled: "bg-ink-700 text-sand-400",
  draft: "bg-ink-700 text-sand-300",
};

export function StatusChip({ status }: { status: string }) {
  return <span className={`chip ${STATUS_STYLE[status] ?? "bg-ink-700 text-sand-300"}`}>{status.replace(/_/g, " ")}</span>;
}

export const STAGE_LABEL: Record<string, string> = {
  analysis: "Analysing reference", story: "Preparing story", characters: "Creating characters", voice: "Generating voice",
  images: "Generating scenes", music: "Creating music", sfx: "Creating sound effects", video: "Creating video clips",
  render: "Editing video", qc: "Exporting & validating MP4",
};

export function fmtDuration(s: number | null | undefined): string {
  if (s === null || s === undefined) return "—";
  const m = Math.floor(s / 60), r = Math.round(s % 60);
  return m ? `${m} min ${r.toString().padStart(2, "0")} s` : `${r} s`;
}

export function StageList({ job }: { job: Job }) {
  return (
    <ol className="space-y-2">
      {Object.entries(job.stages).map(([k, v]) => (
        <li key={k} className="flex items-start gap-3">
          <StageDot status={v.status} />
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between gap-2">
              <span className={`text-sm ${v.status === "waiting" ? "text-sand-400" : "text-sand-100"}`}>{STAGE_LABEL[k] ?? k}</span>
              <span className="text-xs text-sand-400">
                {v.total ? `${v.done ?? 0}/${v.total} · ` : ""}
                {v.elapsed_s !== undefined && v.status !== "waiting" ? fmtDuration(v.elapsed_s) : <span className="capitalize">{v.status}</span>}
              </span>
            </div>
            {v.detail && <p className="truncate text-xs text-sand-400">{v.detail}</p>}
          </div>
        </li>
      ))}
    </ol>
  );
}

function StageDot({ status }: { status: StageStatus }) {
  const cls =
    status === "completed" ? "bg-emerald-400" : status === "processing" ? "bg-mane-400 animate-pulse" : status === "failed" ? "bg-red-400" : status === "skipped" ? "bg-ink-600" : "border border-ink-600";
  return <span className={`mt-1.5 h-2.5 w-2.5 flex-none rounded-full ${cls}`} />;
}

export function Progress({ value }: { value: number }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-ink-800">
      <div className="h-full rounded-full bg-gradient-to-r from-mane-600 to-mane-300 transition-all duration-700" style={{ width: `${Math.max(2, value)}%` }} />
    </div>
  );
}

export function ErrorBox({ error }: { error?: string }) {
  if (!error) return null;
  return <div className="rounded-xl border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-200">{error}</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-2xl border border-dashed border-ink-700 p-10 text-center text-sm text-sand-400">{children}</div>;
}

export function timeAgo(iso: string) {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return new Date(iso).toLocaleDateString();
}
