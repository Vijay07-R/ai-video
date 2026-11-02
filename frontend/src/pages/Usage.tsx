import { api } from "../api";
import { Empty, ErrorBox, PageHeader, useLoad } from "../ui";

export default function UsagePage() {
  const [usage, error] = useLoad(api.usage, [], 15000);
  const [errors] = useLoad(api.errors, []);
  return (
    <>
      <PageHeader title="Usage & cost" subtitle="Every provider call is logged. Cached calls reused an earlier result and spent no quota." />
      <ErrorBox error={error} />
      <div className="card mb-6 flex items-center justify-between">
        <div><div className="label">Total spent</div><div className="font-display text-4xl text-emerald-300">${(usage?.total_cost_usd ?? 0).toFixed(2)}</div></div>
        <p className="max-w-md text-right text-xs text-sand-400">Gemini free-tier limits are per model per day and are enforced by Google. When one is reached, jobs fall back to a local model or pause until the quota resets.</p>
      </div>
      {usage && (usage.items.length ? (
        <div className="card overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wider text-sand-400">
              <tr>{["Provider", "Kind", "Calls", "Cached", "Failures", "Time", "Cost"].map((h) => <th key={h} className="px-4 py-3">{h}</th>)}</tr>
            </thead>
            <tbody>
              {usage.items.map((r) => (
                <tr key={r.provider + r.kind} className="border-t border-ink-800">
                  <td className="px-4 py-2">{r.provider}</td><td className="px-4 py-2">{r.kind}</td><td className="px-4 py-2">{r.calls}</td>
                  <td className="px-4 py-2">{r.cached}</td><td className="px-4 py-2">{r.failures}</td>
                  <td className="px-4 py-2">{Math.round(r.seconds)} s</td><td className="px-4 py-2">${r.cost_usd.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <Empty>No provider calls yet.</Empty>)}
      {errors && errors.length > 0 && (
        <section className="mt-8">
          <h2 className="mb-3 font-display text-xl">Recent errors</h2>
          <div className="space-y-2">
            {errors.slice(0, 15).map((e) => (
              <details key={e.id} className="card p-3 text-xs">
                <summary className="cursor-pointer text-sand-200">{new Date(e.created_at).toLocaleString()} · {e.where} · {e.message.split("\n").filter(Boolean).pop()?.slice(0, 140)}</summary>
                <pre className="mt-2 whitespace-pre-wrap text-sand-400">{e.message}</pre>
              </details>
            ))}
          </div>
        </section>
      )}
    </>
  );
}
