import { useState } from "react";
import { api, fileUrl } from "../api";
import type { Character, Project, Scene } from "../types";
import { Empty, ErrorBox, PageHeader, Progress, STAGE_LABEL, StageList, StatusChip, fmtDuration, go, useLoad } from "../ui";
import { PreflightBox } from "./CreateVideo";

const ACTIVE = ["queued", "running"];
const LANG_NAME: Record<string, string> = { en: "English", ta: "தமிழ் Tamil", te: "తెలుగు Telugu", hi: "हिन्दी Hindi" };
const TABS = [["overview", "Generation"], ["storyboard", "Script & scenes"], ["characters", "Character studio"], ["assets", "Assets"]];

export default function Workspace({ id, tab }: { id: string; tab: string }) {
  const [p, error, reload] = useLoad(() => api.project(id), [id], (d) => (d?.job && ACTIVE.includes(d.job.status) ? 2000 : undefined));
  const [actionError, setActionError] = useState<string>();
  if (error) return <ErrorBox error={error} />;
  if (!p) return <p className="text-sand-400">Loading…</p>;

  const act = async (fn: () => Promise<unknown>) => {
    setActionError(undefined);
    try {
      await fn();
      await reload();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    }
  };
  const job = p.job;
  const running = job && ACTIVE.includes(job.status);

  return (
    <>
      <PageHeader
        title={p.title}
        subtitle={<>{p.animal} · {LANG_NAME[p.settings.language] ?? p.settings.language} · {p.settings.duration_s}s · {p.settings.aspect_ratio} · {p.settings.quality}{p.story?.logline ? ` — ${p.story.logline}` : ""}</>}
        actions={
          <>
            {running && <button className="btn-ghost" onClick={() => act(() => api.cancel(job!.id))}>Cancel</button>}
            {job?.status === "paused" && <button className="btn-primary" onClick={() => act(() => api.resume(job.id))}>Resume now</button>}
            {p.status === "awaiting_approval" && <button className="btn-primary" onClick={() => act(() => api.approve(p.id))}>Approve & continue</button>}
            {!running && job?.status !== "paused" && p.status !== "awaiting_approval" && (
              <button className="btn-primary" onClick={() => act(() => api.generate(p.id))}>{p.final_video ? "Re-render" : "Generate"}</button>
            )}
          </>
        }
      />
      <ErrorBox error={actionError} />
      <div className="mb-6 flex gap-1 overflow-x-auto border-b border-ink-800">
        {TABS.map(([k, label]) => (
          <button key={k} onClick={() => go(`project/${p.id}/${k}`)}
                  className={`whitespace-nowrap border-b-2 px-4 py-2 text-sm ${tab === k ? "border-mane-500 text-mane-300" : "border-transparent text-sand-400 hover:text-sand-100"}`}>{label}</button>
        ))}
      </div>
      {tab === "overview" && <Overview p={p} act={act} onDelete={() => act(async () => { await api.remove(p.id); go(""); })} />}
      {tab === "storyboard" && <Storyboard p={p} act={act} />}
      {tab === "characters" && <Characters p={p} act={act} />}
      {tab === "assets" && <ProjectAssets id={p.id} />}
    </>
  );
}

function Overview({ p, onDelete, act }: { p: Project; onDelete: () => void; act: (fn: () => Promise<unknown>) => Promise<void> }) {
  const job = p.job;
  const vertical = p.settings.aspect_ratio === "9:16";
  const motionComic = p.scenes?.some((s) => s.video_provider === "motion-comic");
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
      <div className="space-y-4">
        <div className={`card flex items-center justify-center bg-black/40 p-3 ${vertical ? "min-h-[520px]" : ""}`}>
          {p.final_video ? (
            <video key={p.final_video} src={fileUrl(p.final_video)} controls className={`rounded-xl ${vertical ? "max-h-[640px]" : "w-full"}`} />
          ) : (
            <div className="grid min-h-[300px] w-full place-items-center text-center text-sm text-sand-400">
              {job?.status === "running" ? "Your film is being made. The preview appears here when rendering finishes." : "No video yet."}
            </div>
          )}
        </div>
        {p.final_video && (
          <div className="flex flex-wrap items-center gap-3">
            <a className="btn-primary" href={fileUrl(p.final_video)} download>Download MP4</a>
            {motionComic && <span className="chip bg-amber-900/40 text-amber-200">Some scenes are an animated image montage (not AI video)</span>}
            {p.settings.quality === "4k" && <span className="chip bg-ink-700 text-sand-300">4K is upscaled</span>}
          </div>
        )}
        {p.scenes && p.scenes.length > 0 && (
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-6">
            {p.scenes.map((s) => (
              <div key={s.id} className="relative overflow-hidden rounded-xl bg-ink-800">
                {s.image ? <img src={fileUrl(s.image)} alt="" className="aspect-video w-full object-cover" /> : <div className="aspect-video" />}
                <span className="absolute left-1 top-1 rounded bg-black/60 px-1.5 text-[10px]">{s.number}</span>
                {s.consistency_flag && <span className="absolute right-1 top-1 rounded bg-amber-500 px-1.5 text-[10px] text-ink-950">check</span>}
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="space-y-4">
        {p.preflight && !p.preflight.ok && <PreflightBox pre={p.preflight} />}
        {job ? (
          <div className="card">
            <div className="mb-3 flex items-center justify-between">
              <span className="font-display text-lg">Progress</span>
              <StatusChip status={job.status} />
            </div>
            <div className="mb-1 flex items-baseline justify-between text-sm">
              <span className="text-sand-100">{currentStep(job)}</span>
              <span className="font-display text-2xl">{Math.floor(job.progress)}%</span>
            </div>
            <Progress value={job.progress} />
            <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
              <div className="rounded-lg bg-ink-850 px-3 py-2"><div className="text-sand-400">Elapsed</div><div className="text-sand-100">{fmtDuration(job.elapsed_s)}</div></div>
              <div className="rounded-lg bg-ink-850 px-3 py-2"><div className="text-sand-400">Remaining (estimate)</div>
                <div className="text-sand-100">{job.status === "running" ? (job.eta_s !== null ? `~${fmtDuration(job.eta_s)}` : "not measurable yet") : "—"}</div></div>
            </div>
            <QueueNotice job={job} act={act} />
            {job.message && (
              <p className={`mb-4 mt-3 rounded-lg px-3 py-2 text-xs ${["failed", "paused"].includes(job.status) ? "bg-red-950/40 text-red-200" : "text-sand-400"}`}>{job.message}</p>
            )}
            <StageList job={job} />
          </div>
        ) : <Empty>Not started.</Empty>}
        {!!p.settings.warnings?.length && (
          <div className="space-y-2">{p.settings.warnings.map((w, i) => <div key={i} className="rounded-xl border border-amber-900 bg-amber-950/30 px-3 py-2 text-xs text-amber-200">{w}</div>)}</div>
        )}
        {p.settings.reference_notes && (
          <div className="card text-sm"><div className="label">Reference style</div><p className="text-sand-300">{p.settings.reference_notes}</p></div>
        )}
        <div className="card text-sm">
          <div className="label">Idea</div>
          <p className="text-sand-200">{p.prompt}</p>
          {p.story?.llm_provider && <p className="mt-2 text-xs text-sand-400">Story written by: {p.story.llm_provider}</p>}
        </div>
        <button className="btn-danger w-full" onClick={() => confirmDelete(onDelete)}>Delete project</button>
      </div>
    </div>
  );
}

function QueueNotice({ job, act }: { job: Project["job"] & {}; act: (fn: () => Promise<unknown>) => Promise<void> }) {
  if (job.stalled_min)
    return (
      <div className="mt-3 rounded-lg bg-amber-950/40 px-3 py-2 text-xs text-amber-200">
        No progress update for {job.stalled_min} min. One AI video clip, or one image drawn on the CPU, can take this long.
        If it stays stuck, check the engine window for errors or cancel and resume.
      </div>
    );
  const q = job.queue;
  if (!q) return null;
  if (!q.worker_running)
    return <div className="mt-3 rounded-lg bg-red-950/40 px-3 py-2 text-xs text-red-200">The background worker is not running, so nothing will start. Close the engine window and run scripts\start.bat again.</div>;
  if (!q.running.length) return <div className="mt-3 rounded-lg bg-ink-850 px-3 py-2 text-xs text-sand-300">Starting…</div>;
  return (
    <div className="mt-3 space-y-2 rounded-lg bg-sky-950/40 px-3 py-2 text-xs text-sky-100">
      <p>Videos are made one at a time (they share your GPU/CPU). This one is #{q.position} in the queue and starts when this finishes:</p>
      {q.running.map((r) => (
        <div key={r.job_id} className="flex items-center justify-between gap-2 rounded bg-black/30 px-2 py-1.5">
          <a className="truncate underline" href={`#/project/${r.project_id}`}>{r.title}</a>
          <span className="whitespace-nowrap text-sky-300">{r.step ?? "starting"} · {Math.floor(r.progress)}%{r.stalled_min ? ` · no update ${r.stalled_min} min` : ""}</span>
          <button className="btn-ghost px-2 py-0.5 text-[11px]" onClick={() => act(() => api.cancel(r.job_id))}>Cancel that video</button>
        </div>
      ))}
    </div>
  );
}

function currentStep(job: Project["job"] & {}) {
  if (job.status === "completed") return "Finished";
  if (job.status === "failed") return "Failed";
  const cur = Object.entries(job.stages).find(([, v]) => v.status === "processing");
  return cur ? STAGE_LABEL[cur[0]] ?? cur[0] : job.status === "queued" ? "Waiting to start" : job.status.replace("_", " ");
}

function confirmDelete(fn: () => void) {
  // inline two-step confirm without browser dialogs
  const el = document.activeElement as HTMLButtonElement | null;
  if (el && el.dataset.armed === "1") return fn();
  if (el) {
    el.dataset.armed = "1";
    el.textContent = "Click again to delete permanently";
    setTimeout(() => { el.dataset.armed = ""; el.textContent = "Delete project"; }, 4000);
  }
}

function Storyboard({ p, act }: { p: Project; act: (fn: () => Promise<unknown>) => Promise<void> }) {
  const [script, setScript] = useState(p.script ?? "");
  if (!p.scenes?.length)
    return (
      <div className="space-y-4">
        <Empty>The storyboard appears after the story stage finishes.</Empty>
        <div className="card">
          <label className="label">Script (optional, used when the story is written)</label>
          <textarea className="input min-h-[160px]" value={script} onChange={(e) => setScript(e.target.value)} />
          <button className="btn-ghost mt-3" onClick={() => act(() => api.update(p.id, { script }))}>Save script</button>
        </div>
      </div>
    );
  return (
    <div className="space-y-4">
      <div className="card text-sm">
        <div className="grid gap-4 md:grid-cols-3">
          <div><div className="label">Visual style</div><p className="text-sand-200">{p.story?.visual_style}</p></div>
          <div><div className="label">Music theme</div><p className="text-sand-200">{p.story?.music_theme}</p></div>
          <div><div className="label">Total</div><p className="text-sand-200">{p.scenes.length} scenes · {p.scenes.reduce((a, s) => a + s.duration_s, 0).toFixed(1)} s</p></div>
        </div>
        <p className="mt-3 text-xs text-sand-400">Editing a scene clears only the parts it affects. Press Generate / Re-render to rebuild just those parts.</p>
      </div>
      {p.scenes.map((s) => <SceneEditor key={s.id + s.status + (s.image ?? "")} s={s} act={act} />)}
    </div>
  );
}

function SceneEditor({ s, act }: { s: Scene; act: (fn: () => Promise<unknown>) => Promise<void> }) {
  const [d, setD] = useState({
    narration: s.data.narration, image_prompt: s.data.image_prompt, video_prompt: s.data.video_prompt,
    camera_movement: s.data.camera_movement, duration_s: s.duration_s, transition: s.data.transition,
  });
  const dirty = d.narration !== s.data.narration || d.image_prompt !== s.data.image_prompt || d.video_prompt !== s.data.video_prompt ||
    d.camera_movement !== s.data.camera_movement || d.duration_s !== s.duration_s || d.transition !== s.data.transition;
  return (
    <div className="card grid gap-4 lg:grid-cols-[260px_1fr]">
      <div className="space-y-2">
        <div className="overflow-hidden rounded-xl bg-ink-800">
          {s.video ? <video src={fileUrl(s.video)} muted loop controls className="aspect-video w-full object-cover" />
            : s.image ? <img src={fileUrl(s.image)} alt="" className="aspect-video w-full object-cover" /> : <div className="aspect-video" />}
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="font-display text-base">Scene {s.number}</span>
          <StatusChip status={s.status === "ready" ? "completed" : "waiting"} />
          {s.video_provider && <span className={`chip ${s.video_provider === "motion-comic" ? "bg-amber-900/40 text-amber-200" : "bg-emerald-900/40 text-emerald-300"}`}>
            {s.video_provider === "motion-comic" ? "image montage" : "AI video"}</span>}
          {s.consistency_score !== null && (
            <span className={`chip ${s.consistency_flag ? "bg-amber-900/50 text-amber-200" : "bg-emerald-900/40 text-emerald-300"}`}>
              colour match {(s.consistency_score * 100).toFixed(0)}%
            </span>
          )}
        </div>
        {s.voice && <audio src={fileUrl(s.voice)} controls className="w-full" />}
        <div className="flex flex-wrap gap-2">
          <button className="btn-ghost px-3 py-1 text-xs" onClick={() => act(() => api.regenerateScene(s.id, ["image", "video"]))}>New image</button>
          <button className="btn-ghost px-3 py-1 text-xs" onClick={() => act(() => api.regenerateScene(s.id, ["video"]))}>New motion</button>
          <button className="btn-ghost px-3 py-1 text-xs" onClick={() => act(() => api.regenerateScene(s.id, ["voice"]))}>New voice</button>
        </div>
      </div>
      <div className="space-y-3">
        <p className="text-sm text-sand-300">{s.data.description}</p>
        <Field label="Narration">
          <textarea className="input min-h-[60px]" value={d.narration} onChange={(e) => setD({ ...d, narration: e.target.value })} />
        </Field>
        {s.data.dialogue.length > 0 && (
          <div className="text-sm">
            <div className="label">Dialogue</div>
            {s.data.dialogue.map((l, i) => <p key={i} className="text-sand-200"><b className="text-mane-300">{l.character}:</b> {l.line}</p>)}
          </div>
        )}
        <Field label="Image prompt"><textarea className="input min-h-[70px]" value={d.image_prompt} onChange={(e) => setD({ ...d, image_prompt: e.target.value })} /></Field>
        <div className="grid gap-3 sm:grid-cols-4">
          <Field label="Motion prompt" className="sm:col-span-2"><input className="input" value={d.video_prompt} onChange={(e) => setD({ ...d, video_prompt: e.target.value })} /></Field>
          <Field label="Camera"><input className="input" value={d.camera_movement} onChange={(e) => setD({ ...d, camera_movement: e.target.value })} /></Field>
          <Field label="Seconds"><input className="input" type="number" min={1} max={30} step={0.5} value={d.duration_s} onChange={(e) => setD({ ...d, duration_s: +e.target.value })} /></Field>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-xs text-sand-400">
          <span>Angle: {s.data.camera_angle}</span><span>Light: {s.data.lighting}</span><span>Mood: {s.data.emotions}</span>
          <span>SFX: {s.data.sfx.join(", ") || "—"}</span>
          <select className="input w-auto py-1 text-xs" value={d.transition} onChange={(e) => setD({ ...d, transition: e.target.value })}>
            {["dissolve", "fade", "fadeblack", "wipeleft", "slideleft", "circleopen", "cut"].map((t) => <option key={t}>{t}</option>)}
          </select>
        </div>
        {dirty && <button className="btn-primary" onClick={() => act(() => api.updateScene(s.id, d))}>Save scene changes</button>}
      </div>
    </div>
  );
}

function Field({ label, children, className = "" }: { label: string; children: React.ReactNode; className?: string }) {
  return <div className={className}><label className="label">{label}</label>{children}</div>;
}

function Characters({ p, act }: { p: Project; act: (fn: () => Promise<unknown>) => Promise<void> }) {
  if (!p.characters?.length) return <Empty>Characters are designed right after the story is written.</Empty>;
  return <div className="grid gap-4 md:grid-cols-2">{p.characters.map((c) => <CharacterCard key={c.id + (c.reference_image ?? "")} c={c} act={act} />)}</div>;
}

const TRAITS = ["body_shape", "color", "face", "eye_color", "markings", "accessories", "personality", "voice"];

function CharacterCard({ c, act }: { c: Character; act: (fn: () => Promise<unknown>) => Promise<void> }) {
  const [edit, setEdit] = useState<Record<string, string>>(() => Object.fromEntries(TRAITS.map((t) => [t, c.profile[t] ?? ""])));
  const dirty = TRAITS.some((t) => (c.profile[t] ?? "") !== edit[t]);
  return (
    <div className="card">
      <div className="flex gap-4">
        <div className="h-40 w-40 flex-none overflow-hidden rounded-xl bg-ink-800">
          {c.reference_image ? <img src={fileUrl(c.reference_image)} alt={c.name} className="h-full w-full object-cover" /> : <div className="grid h-full place-items-center text-xs text-sand-400">designing…</div>}
        </div>
        <div className="min-w-0">
          <div className="font-display text-xl">{c.name}</div>
          <div className="text-sm text-sand-400">{c.profile.species} · {c.profile.role}</div>
          <p className="mt-2 text-xs text-sand-300">{c.identity_prompt}</p>
        </div>
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        {TRAITS.map((t) => (
          <div key={t}><label className="label">{t.replace("_", " ")}</label>
            <input className="input py-1.5" value={edit[t]} onChange={(e) => setEdit({ ...edit, [t]: e.target.value })} /></div>
        ))}
      </div>
      {dirty && (
        <button className="btn-primary mt-3" onClick={() => act(() => api.updateCharacter(c.id, edit))}>
          Save &amp; redesign (redraws this character's scenes)
        </button>
      )}
    </div>
  );
}

function ProjectAssets({ id }: { id: string }) {
  const [assets, error] = useLoad(() => api.assets(id), [id]);
  if (error) return <ErrorBox error={error} />;
  if (!assets?.length) return <Empty>No assets yet.</Empty>;
  return <AssetGrid assets={assets} />;
}

export function AssetGrid({ assets }: { assets: { id: string; kind: string; url: string; provider: string | null; meta: Record<string, unknown> }[] }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {assets.map((a) => (
        <div key={a.id} className="overflow-hidden rounded-xl border border-ink-700 bg-ink-900">
          <div className="bg-ink-800">
            {a.kind === "image" ? <img src={fileUrl(a.url)} alt="" className="aspect-video w-full object-cover" />
              : a.kind === "video" || a.kind === "final" ? <video src={fileUrl(a.url)} controls muted className="aspect-video w-full" />
              : ["voice", "music", "sfx"].includes(a.kind) ? <div className="p-3"><audio src={fileUrl(a.url)} controls className="w-full" /></div>
              : <div className="aspect-video" />}
          </div>
          <div className="flex items-center justify-between p-2 text-xs">
            <span className="chip bg-ink-700 text-sand-200">{a.kind}{a.meta.scene ? ` · scene ${a.meta.scene}` : ""}</span>
            <a href={fileUrl(a.url)} download className="text-mane-300 hover:underline">{a.provider ?? "download"}</a>
          </div>
        </div>
      ))}
    </div>
  );
}
