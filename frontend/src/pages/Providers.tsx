import { api } from "../api";
import { ErrorBox, PageHeader, useLoad } from "../ui";

const KIND_LABEL: Record<string, string> = { llm: "Story & script AI", image: "Image generation", video: "Video generation", voice: "Voice", music: "Music", sfx: "Sound effects" };

export default function Providers() {
  const [system, sysErr] = useLoad(api.system, []);
  const [providers, provErr, reload] = useLoad(api.providers, []);
  const hw = system?.hardware;
  return (
    <>
      <PageHeader title="Free providers & hardware" subtitle="The engine picks the first available free provider in each row, in order. Paid services are never used."
                  actions={<button className="btn-ghost" onClick={reload}>Re-check</button>} />
      <ErrorBox error={sysErr || provErr} />
      {hw && (
        <div className="card mb-6">
          <div className="mb-3 flex items-center justify-between">
            <span className="font-display text-lg">This machine</span>
            <span className="chip bg-mane-500/20 text-mane-300">tier: {hw.tier}</span>
          </div>
          <div className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <Info k="OS" v={hw.os} /><Info k="CPU" v={`${hw.cpu} (${hw.cpu_cores} cores)`} /><Info k="RAM" v={`${hw.ram_gb} GB`} />
            <Info k="Free disk" v={`${hw.disk_free_gb} GB`} />
            <Info k="GPU" v={hw.gpus.length ? hw.gpus.map((g) => `${g.name} (${g.vram_gb} GB)`).join(", ") : "none detected"} />
            <Info k="CUDA" v={hw.cuda ? "yes" : "no"} /><Info k="FFmpeg" v={hw.ffmpeg ? "installed" : "MISSING"} />
            <Info k="ComfyUI" v={system!.comfyui_url} />
          </div>
          <p className="mt-3 text-sm text-sand-200">{hw.recommendation}</p>
          <p className="mt-1 text-xs text-sand-400">{hw.note}</p>
        </div>
      )}
      {system && (
        <div className="card mb-6 border-emerald-900/70 text-sm text-emerald-200">
          {system.cost_policy.statement} Spending limit: ${system.cost_policy.spending_limit_usd.toFixed(2)}.
        </div>
      )}
      {providers && Object.keys(KIND_LABEL).map((kind) => (
        <section key={kind} className="mb-6">
          <h2 className="mb-2 font-display text-lg">{KIND_LABEL[kind]}</h2>
          <div className="space-y-2">
            {(system?.orders[kind] ?? []).map((n) => providers.find((p) => p.name === n)).filter(Boolean)
              .concat(providers.filter((p) => p.kind === kind && !(system?.orders[kind] ?? []).includes(p.name)))
              .map((p, i) => p && (
                <div key={p.name} className="card grid gap-2 p-4 md:grid-cols-[200px_1fr_auto] md:items-center">
                  <div>
                    <div className="font-medium">{i + 1}. {p.name}</div>
                    <div className="text-xs text-sand-400">{p.quality} · {p.local ? "local" : "cloud free tier"}</div>
                  </div>
                  <div className="text-xs text-sand-300">
                    <p>{p.limits}</p>
                    <p className="text-sand-400">License: {p.license}</p>
                    {!p.available && <p className="mt-1 text-amber-300">Not ready: {p.detail}</p>}
                    {p.cooldown_s > 0 && <p className="mt-1 text-amber-300">Free quota cooldown: {Math.ceil(p.cooldown_s / 60)} min</p>}
                  </div>
                  <span className={`chip justify-self-start ${p.available ? "bg-emerald-900/50 text-emerald-300" : "bg-ink-700 text-sand-400"}`}>
                    {p.available ? "ready" : "not ready"}
                  </span>
                </div>
              ))}
          </div>
        </section>
      ))}
      <p className="text-xs text-sand-400">Setup instructions for each provider are in the README (Gemini key, Ollama, ComfyUI models, Kokoro).</p>
    </>
  );
}

function Info({ k, v }: { k: string; v: string }) {
  return <div><div className="label">{k}</div><div className="break-words text-sand-100">{v}</div></div>;
}
