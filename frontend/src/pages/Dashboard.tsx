import { api, fileUrl } from "../api";
import type { Project, ProviderStatus } from "../types";
import { Empty, ErrorBox, PageHeader, Progress, StatusChip, timeAgo, useLoad } from "../ui";

export default function Dashboard() {
  const [projects, error] = useLoad(api.projects, [], (d) => (d?.some((p) => ["queued", "running", "generating"].includes(p.job?.status ?? p.status)) ? 3000 : 15000));
  const [providers] = useLoad(api.providers, []);
  const [system] = useLoad(api.system, []);

  const active = projects?.filter((p) => p.job && ["queued", "running", "paused"].includes(p.job.status)) ?? [];
  const done = projects?.filter((p) => p.final_video) ?? [];

  return (
    <>
      <PageHeader title="Dashboard" subtitle="Type an animal and an idea. The engine writes, designs, animates, voices, scores and edits the film."
                  actions={<a className="btn-primary" href="#/create">+ New video</a>} />
      <ErrorBox error={error} />

      <div className="mb-8 grid gap-4 md:grid-cols-3">
        <Stat label="Videos finished" value={done.length} />
        <Stat label="In progress" value={active.length} />
        <Stat label="Money spent" value="$0.00" hint="Zero-cost mode" />
      </div>

      {system && (
        <div className="card mb-8 flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="label">This machine</div>
            <p className="text-sm text-sand-200">{system.hardware.recommendation}</p>
          </div>
          <a href="#/providers" className="btn-ghost">Check providers</a>
        </div>
      )}
      {providers && <ReadinessBar providers={providers} />}

      {active.length > 0 && (
        <section className="mb-8">
          <h2 className="mb-3 font-display text-xl">Generating now</h2>
          <div className="grid gap-4 md:grid-cols-2">{active.map((p) => <ActiveCard key={p.id} p={p} />)}</div>
        </section>
      )}

      <section>
        <h2 className="mb-3 font-display text-xl">Recent videos</h2>
        {projects && projects.length === 0 ? (
          <Empty>No videos yet. <a className="text-mane-300 underline" href="#/create">Create your first one</a>.</Empty>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{projects?.slice(0, 9).map((p) => <ProjectCard key={p.id} p={p} />)}</div>
        )}
      </section>
    </>
  );
}

function Stat({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="card">
      <div className="label">{label}</div>
      <div className="font-display text-3xl">{value}</div>
      {hint && <div className="text-xs text-emerald-300">{hint}</div>}
    </div>
  );
}

function ReadinessBar({ providers }: { providers: ProviderStatus[] }) {
  const kinds = ["llm", "image", "video", "voice", "music", "sfx"];
  const label: Record<string, string> = { llm: "Story AI", image: "Images", video: "Video", voice: "Voice", music: "Music", sfx: "Sound FX" };
  return (
    <div className="mb-8 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
      {kinds.map((k) => {
        const ok = providers.filter((p) => p.kind === k && p.available);
        return (
          <div key={k} className={`rounded-xl border px-3 py-2 text-xs ${ok.length ? "border-emerald-900/70 bg-emerald-950/20" : "border-red-900/70 bg-red-950/20"}`}>
            <div className="font-medium text-sand-100">{label[k]}</div>
            <div className={ok.length ? "text-emerald-300" : "text-red-300"}>{ok.length ? ok[0].name : "not ready"}</div>
          </div>
        );
      })}
    </div>
  );
}

function ActiveCard({ p }: { p: Project }) {
  return (
    <a href={`#/project/${p.id}`} className="card block transition hover:border-mane-600">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-medium">{p.title}</span>
        <StatusChip status={p.job!.status} />
      </div>
      <Progress value={p.job!.progress} />
      <p className="mt-2 truncate text-xs text-sand-400">{p.job!.message}</p>
    </a>
  );
}

export function ProjectCard({ p }: { p: Project }) {
  return (
    <a href={`#/project/${p.id}`} className="group overflow-hidden rounded-2xl border border-ink-700 bg-ink-900 transition hover:border-mane-600">
      <div className="aspect-video bg-ink-800">
        {p.thumbnail ? <img src={fileUrl(p.thumbnail)} alt="" className="h-full w-full object-cover transition group-hover:scale-105" />
          : <div className="grid h-full place-items-center font-display text-4xl text-ink-600">{p.animal.slice(0, 1).toUpperCase()}</div>}
      </div>
      <div className="p-4">
        <div className="flex items-start justify-between gap-2">
          <span className="font-medium leading-snug">{p.title}</span>
          <StatusChip status={p.job?.status ?? p.status} />
        </div>
        <p className="mt-1 text-xs text-sand-400">{p.animal} · {p.settings.duration_s}s · {p.settings.aspect_ratio} · {timeAgo(p.created_at)}</p>
      </div>
    </a>
  );
}
