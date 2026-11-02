import type { Asset, Job, LanguageInfo, Preflight, Project, ProviderStatus, SystemInfo, Usage, VideoSettings } from "./types";

const TOKEN_KEY = "ave.token";
const BASE_KEY = "ave.base";

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export const config = {
  get token() {
    return storage()?.getItem(TOKEN_KEY) ?? "";
  },
  set token(v: string) {
    storage()?.setItem(TOKEN_KEY, v);
  },
  /** Engine address. Empty = same site (UI served by the engine or the Vite dev proxy).
   *  When the UI is hosted elsewhere (e.g. Vercel), default to the engine on this computer. */
  get base() {
    const saved = storage()?.getItem(BASE_KEY);
    if (saved !== null && saved !== undefined) return saved;
    return isHostedUi() ? "http://localhost:8000" : "";
  },
  set base(v: string) {
    storage()?.setItem(BASE_KEY, v.replace(/\/$/, ""));
  },
};

export function isHostedUi(): boolean {
  const h = window.location.hostname;
  return !["localhost", "127.0.0.1", "::1", ""].includes(h);
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  if (config.token) headers.Authorization = `Bearer ${config.token}`;
  if (init.body && !(init.body instanceof FormData)) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(`${config.base}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, `Cannot reach the engine at ${config.base || window.location.origin}. Is it running?`);
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      const d = body.detail;
      msg = typeof d === "string" ? d : d?.problems ? `${d.message ?? ""} ${d.problems.join(" ")}`.trim()
        : Array.isArray(d) ? d.map((x: { msg?: string }) => x.msg).join("; ") : JSON.stringify(d ?? body);
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, msg);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

/** URL for media files; adds the token so <video>/<img> tags can load them. */
export function fileUrl(path: string | null | undefined): string | undefined {
  if (!path) return undefined;
  const t = config.token ? `?token=${encodeURIComponent(config.token)}` : "";
  return `${config.base}${path}${t}`;
}

export interface CreateProject {
  title?: string;
  animal: string;
  cast?: string[];
  prompt: string;
  script?: string;
  reference_url?: string;
  settings: VideoSettings;
  auto_start?: boolean;
}

export const api = {
  system: () => req<SystemInfo>("/api/system"),
  providers: () => req<ProviderStatus[]>("/api/providers"),
  languages: () => req<LanguageInfo[]>("/api/languages"),
  preflight: (s: VideoSettings) => req<Preflight>("/api/preflight", { method: "POST", body: JSON.stringify(s) }),
  usage: () => req<Usage>("/api/usage"),
  errors: () => req<{ id: number; where: string; message: string; created_at: string; project_id: string | null }[]>("/api/errors"),
  projects: () => req<Project[]>("/api/projects"),
  project: (id: string) => req<Project>(`/api/projects/${id}`),
  create: (body: CreateProject) => req<Project>("/api/projects", { method: "POST", body: JSON.stringify(body) }),
  update: (id: string, body: Partial<{ title: string; prompt: string; script: string; settings: VideoSettings }>) =>
    req<Project>(`/api/projects/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  remove: (id: string) => req<void>(`/api/projects/${id}`, { method: "DELETE" }),
  uploadReference: (id: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return req<{ reference_file: string }>(`/api/projects/${id}/reference`, { method: "POST", body: fd });
  },
  generate: (id: string) => req<Job>(`/api/projects/${id}/generate`, { method: "POST" }),
  approve: (id: string) => req<Job>(`/api/projects/${id}/approve`, { method: "POST" }),
  cancel: (jobId: string) => req<Job>(`/api/jobs/${jobId}/cancel`, { method: "POST" }),
  resume: (jobId: string) => req<Job>(`/api/jobs/${jobId}/resume`, { method: "POST" }),
  updateScene: (id: string, body: Record<string, unknown>) =>
    req<{ cleared: string[] }>(`/api/scenes/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  regenerateScene: (id: string, parts: string[]) =>
    req<Job>(`/api/scenes/${id}/regenerate`, { method: "POST", body: JSON.stringify({ parts }) }),
  updateCharacter: (id: string, body: Record<string, string>) =>
    req<unknown>(`/api/characters/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  assets: (projectId?: string, kind?: string) =>
    projectId ? req<Asset[]>(`/api/projects/${projectId}/assets`) : req<Asset[]>(`/api/assets${kind ? `?kind=${kind}` : ""}`),
};
