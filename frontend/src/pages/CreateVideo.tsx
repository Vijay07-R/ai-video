import { useEffect, useState } from "react";
import { api } from "../api";
import type { Lang, LanguageInfo, Preflight, VideoSettings } from "../types";
import AnimalPicker from "../AnimalPicker";
import { ErrorBox, PageHeader, go, useLoad } from "../ui";
const STYLES = [
  "cinematic 3D animation, soft volumetric lighting, detailed fur",
  "photorealistic wildlife documentary, natural light, telephoto lens",
  "hand-painted watercolor storybook illustration",
  "2D cartoon, bold outlines, bright flat colours",
  "Studio-style anime, lush painted backgrounds",
  "claymation stop-motion look, handcrafted textures",
];
const LANGS: { code: Lang; name: string; native: string; sample: string }[] = [
  { code: "en", name: "English", native: "English", sample: "Once upon a time…" },
  { code: "ta", name: "Tamil", native: "தமிழ்", sample: "ஒரு காலத்தில்…" },
  { code: "te", name: "Telugu", native: "తెలుగు", sample: "ఒకానొకప్పుడు…" },
  { code: "hi", name: "Hindi", native: "हिन्दी", sample: "एक समय की बात है…" },
];

const DEFAULTS: VideoSettings = {
  duration_s: 60, aspect_ratio: "9:16", quality: "720p", style: STYLES[0], language: "en", voice: "warm, gentle storyteller",
  subtitles: true, subtitle_language: "same", motion: "auto", ai_video_budget_min: 10,
  approve_storyboard: false, consistency_mode: "prompt",
};

export default function CreateVideo() {
  const [cast, setCast] = useState<string[]>(["Lion"]);
  const [mode, setMode] = useState<"together" | "each">("together");
  const [prompt, setPrompt] = useState("");
  const [title, setTitle] = useState("");
  const [script, setScript] = useState("");
  const [refUrl, setRefUrl] = useState("");
  const [refFile, setRefFile] = useState<File | null>(null);
  const [s, setS] = useState<VideoSettings>(DEFAULTS);
  const [advanced, setAdvanced] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [pre, setPre] = useState<Preflight>();
  const [langs] = useLoad(api.languages, []);
  const set = <K extends keyof VideoSettings>(k: K, v: VideoSettings[K]) => setS((o) => ({ ...o, [k]: v }));

  // live readiness check whenever settings change (no generation, no quota used)
  useEffect(() => {
    const t = setTimeout(() => api.preflight(s).then(setPre).catch(() => setPre(undefined)), 300);
    return () => clearTimeout(t);
  }, [s]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      // "together": one film starring every selected animal. "each": one film per animal (queued one after another).
      const groups = mode === "together" ? [cast] : cast.map((c) => [c]);
      const ids: string[] = [];
      for (const g of groups) {
        const p = await api.create({ title: groups.length > 1 && title ? `${title} – ${g[0]}` : title, animal: g.join(", "), cast: g,
                                     prompt, script: script || undefined, reference_url: refUrl || undefined, settings: s, auto_start: !refFile });
        if (refFile) {
          await api.uploadReference(p.id, refFile);
          await api.generate(p.id).catch(() => undefined);
        }
        ids.push(p.id);
      }
      go(ids.length === 1 ? `project/${ids[0]}` : "history");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  const info = (code: Lang) => langs?.find((l) => l.code === code);

  return (
    <form onSubmit={submit} className="mx-auto max-w-3xl">
      <PageHeader title="Create a new video" subtitle="Pick the language, the animal and the idea. Everything else is automatic." />
      <ErrorBox error={error} />

      <div className="card mt-4 space-y-5">
        <div>
          <label className="label">Language (story, dialogue, voice and subtitles)</label>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {LANGS.map((l) => <LangCard key={l.code} l={l} info={info(l.code)} active={s.language === l.code} onPick={() => set("language", l.code)} />)}
          </div>
        </div>

        <div>
          <label className="label">Characters: animals, birds, pets…</label>
          <AnimalPicker cast={cast} onChange={setCast} />
          {cast.length > 1 && (
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              <label className={`flex cursor-pointer items-start gap-2 rounded-xl border px-3 py-2 text-sm ${mode === "together" ? "border-mane-500" : "border-ink-600"}`}>
                <input type="radio" className="mt-1 accent-mane-500" checked={mode === "together"} onChange={() => setMode("together")} />
                <span><b>One video</b> starring all {cast.length} animals together</span>
              </label>
              <label className={`flex cursor-pointer items-start gap-2 rounded-xl border px-3 py-2 text-sm ${mode === "each" ? "border-mane-500" : "border-ink-600"}`}>
                <input type="radio" className="mt-1 accent-mane-500" checked={mode === "each"} onChange={() => setMode("each")} />
                <span><b>{cast.length} separate videos</b>, one per animal (made one after another)</span>
              </label>
            </div>
          )}
        </div>
        <div>
          <label className="label">Story idea (any language)</label>
          <textarea className="input min-h-[100px]" value={prompt} onChange={(e) => setPrompt(e.target.value)} required minLength={5}
                    placeholder="A lion gets trapped in a hunter's net and a little rabbit bites through the net to free him." />
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <div>
            <label className="label">Duration</label>
            <select className="input" value={s.duration_s} onChange={(e) => set("duration_s", +e.target.value)}>
              {[15, 30, 45, 60, 90, 120].map((d) => <option key={d} value={d}>{d} seconds</option>)}
            </select>
          </div>
          <div>
            <label className="label">Format</label>
            <select className="input" value={s.aspect_ratio} onChange={(e) => set("aspect_ratio", e.target.value as VideoSettings["aspect_ratio"])}>
              <option value="9:16">9:16 Shorts / Reels</option>
              <option value="16:9">16:9 YouTube</option>
              <option value="1:1">1:1 Square</option>
            </select>
          </div>
          <div>
            <label className="label">Quality</label>
            <select className="input" value={s.quality} onChange={(e) => set("quality", e.target.value as VideoSettings["quality"])}>
              <option value="720p">720p (fastest)</option>
              <option value="1080p">1080p</option>
              <option value="4k">4K (upscaled)</option>
            </select>
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="label">Subtitles</label>
            <div className="flex gap-2">
              <select className="input" value={s.subtitles ? "on" : "off"} onChange={(e) => set("subtitles", e.target.value === "on")}>
                <option value="on">On</option>
                <option value="off">Off</option>
              </select>
              <select className="input" disabled={!s.subtitles} value={s.subtitle_language} onChange={(e) => set("subtitle_language", e.target.value as VideoSettings["subtitle_language"])}>
                <option value="same">Same as narration</option>
                {LANGS.filter((l) => l.code !== s.language).map((l) => <option key={l.code} value={l.code}>{l.name} ({l.native})</option>)}
              </select>
            </div>
          </div>
          <div>
            <label className="label">Scene motion</label>
            <select className="input" value={s.motion} onChange={(e) => set("motion", e.target.value as VideoSettings["motion"])}>
              <option value="auto">Auto: AI video within {s.ai_video_budget_min} min, montage for the rest</option>
              <option value="ai">AI video for every scene (slow)</option>
              <option value="montage">Animated image montage only (fastest)</option>
            </select>
          </div>
        </div>
        <div>
          <label className="label">Visual style</label>
          <select className="input" value={STYLES.includes(s.style) ? s.style : "custom"} onChange={(e) => e.target.value !== "custom" && set("style", e.target.value)}>
            {STYLES.map((x) => <option key={x} value={x}>{x}</option>)}
            <option value="custom">Custom…</option>
          </select>
          {!STYLES.includes(s.style) && <input className="input mt-2" value={s.style} onChange={(e) => set("style", e.target.value)} />}
        </div>

        <button type="button" className="text-sm text-mane-300 hover:underline" onClick={() => setAdvanced(!advanced)}>
          {advanced ? "Hide" : "Show"} advanced settings
        </button>

        {advanced && (
          <div className="space-y-4 border-t border-ink-700 pt-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="label">Title (optional)</label>
                <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Generated automatically" />
              </div>
              <div>
                <label className="label">AI video time budget (minutes)</label>
                <input className="input" type="number" min={0} max={600} value={s.ai_video_budget_min} onChange={(e) => set("ai_video_budget_min", +e.target.value)} />
              </div>
            </div>
            <div>
              <label className="label">Narrator voice style</label>
              <input className="input" value={s.voice} onChange={(e) => set("voice", e.target.value)} />
            </div>
            <div>
              <label className="label">Full script (optional, in the chosen language)</label>
              <textarea className="input min-h-[120px]" value={script} onChange={(e) => setScript(e.target.value)} placeholder="Paste your own narration script; it will be split into scenes." />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="label">Reference link (optional)</label>
                <input className="input" value={refUrl} onChange={(e) => setRefUrl(e.target.value)} placeholder="https://…" type="url" />
                <p className="mt-1 text-xs text-sand-400">Links are not downloaded. Upload a file to have its style analysed.</p>
              </div>
              <div>
                <label className="label">Reference video / image (optional)</label>
                <input className="input file:mr-3 file:rounded-lg file:border-0 file:bg-ink-700 file:px-3 file:py-1 file:text-sand-100" type="file"
                       accept="video/*,image/*" onChange={(e) => setRefFile(e.target.files?.[0] ?? null)} />
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Toggle label="Approve story before images" checked={s.approve_storyboard} onChange={(v) => set("approve_storyboard", v)} />
              <Toggle label="Strong consistency (img2img)" checked={s.consistency_mode === "img2img"} onChange={(v) => set("consistency_mode", v ? "img2img" : "prompt")} />
            </div>
          </div>
        )}
      </div>

      {pre && <PreflightBox pre={pre} />}

      <button type="submit" disabled={busy || !prompt.trim() || cast.length === 0 || (pre && !pre.ok)}
              className="btn-primary mt-6 w-full py-4 text-base font-semibold tracking-wide">
        {busy ? "Starting…" : pre && !pre.ok ? "Fix the items above to generate" : mode === "each" && cast.length > 1 ? `GENERATE ${cast.length} VIDEOS` : "GENERATE VIDEO"}
      </button>
      <p className="mt-3 text-center text-xs text-sand-400">Free and local AI only. Time depends on your hardware; the progress screen shows real measured times.</p>
    </form>
  );
}

function LangCard({ l, info, active, onPick }: { l: (typeof LANGS)[number]; info?: LanguageInfo; active: boolean; onPick: () => void }) {
  const status = !info ? "checking voice…" : info.voice ? (info.natural ? `voice: ${info.voice}` : "robotic voice only") : "no voice installed";
  const color = !info ? "text-sand-400" : info.voice ? (info.natural ? "text-emerald-300" : "text-amber-300") : "text-red-300";
  return (
    <button type="button" onClick={onPick}
            className={`rounded-xl border px-3 py-3 text-left transition ${active ? "border-mane-500 bg-mane-500/10" : "border-ink-600 hover:border-sand-400"}`}>
      <div className="font-display text-xl leading-tight">{l.native}</div>
      <div className="text-xs text-sand-300">{l.name}</div>
      <div className={`mt-1 text-[11px] ${color}`}>{status}</div>
    </button>
  );
}

export function PreflightBox({ pre }: { pre: { ok: boolean; problems: string[]; warnings: string[] } }) {
  if (pre.ok && !pre.warnings.length) {
    return <div className="mt-4 rounded-xl border border-emerald-900 bg-emerald-950/30 px-4 py-3 text-sm text-emerald-200">Ready: every step has a free provider.</div>;
  }
  return (
    <div className="mt-4 space-y-2">
      {pre.problems.map((p, i) => <div key={i} className="rounded-xl border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-200">{p}</div>)}
      {pre.warnings.map((w, i) => <div key={i} className="rounded-xl border border-amber-900 bg-amber-950/30 px-4 py-3 text-sm text-amber-200">{w}</div>)}
    </div>
  );
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-ink-700 px-3 py-2 text-sm">
      <input type="checkbox" className="accent-mane-500" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}
