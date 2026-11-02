export type Lang = "en" | "ta" | "te" | "hi";

export interface LanguageInfo {
  code: Lang;
  name: string;
  native: string;
  voice: string | null;
  natural: boolean;
  fix: string;
}

export interface Preflight {
  ok: boolean;
  problems: string[];
  warnings: string[];
  plan: Record<string, string | null>;
  language: string;
}

export type StageStatus = "waiting" | "processing" | "completed" | "skipped" | "failed";

export interface VideoSettings {
  duration_s: number;
  aspect_ratio: "16:9" | "9:16" | "1:1";
  quality: "720p" | "1080p" | "4k";
  style: string;
  language: Lang;
  voice: string;
  subtitles: boolean;
  subtitle_language: "same" | Lang;
  motion: "auto" | "ai" | "montage";
  ai_video_budget_min: number;
  approve_storyboard: boolean;
  consistency_mode: "prompt" | "img2img";
}

export interface Job {
  id: string;
  kind: string;
  status: "queued" | "running" | "paused" | "awaiting_approval" | "completed" | "failed" | "cancelled";
  progress: number;
  message: string | null;
  stages: Record<string, { status: StageStatus; detail: string; elapsed_s?: number; done?: number; total?: number }>;
  attempts: number;
  resume_after: string | null;
  elapsed_s: number | null;
  eta_s: number | null;
  stalled_min: number | null;
  queue: {
    position: number;
    worker_running: boolean;
    running: { job_id: string; project_id: string; title: string; step: string | null; progress: number; stalled_min: number | null }[];
  } | null;
  created_at: string;
}

export interface SceneData {
  number: number;
  duration_s: number;
  description: string;
  characters: string[];
  environment: string;
  image_prompt: string;
  video_prompt: string;
  camera_movement: string;
  camera_angle: string;
  lighting: string;
  emotions: string;
  dialogue: { character: string; line: string }[];
  narration: string;
  sfx: string[];
  music: string;
  transition: string;
}

export interface Scene {
  id: string;
  number: number;
  duration_s: number;
  data: SceneData;
  status: string;
  image?: string;
  video?: string;
  voice?: string;
  sfx?: string;
  video_provider: string | null;
  consistency_score: number | null;
  consistency_flag: boolean;
}

export interface Character {
  id: string;
  key: string;
  name: string;
  profile: Record<string, string>;
  identity_prompt: string;
  reference_image?: string;
}

export interface Project {
  id: string;
  title: string;
  animal: string;
  prompt: string;
  status: string;
  settings: VideoSettings & { reference_notes?: string; warnings?: string[] };
  preflight?: Preflight | null;
  final_video: string | null;
  thumbnail: string | null;
  created_at: string;
  scene_count: number;
  job: Job | null;
  script?: string | null;
  reference_url?: string | null;
  reference_file?: string | null;
  story?: { title: string; logline: string; visual_style: string; music_theme: string; llm_provider?: string; analysis?: Record<string, unknown> } | null;
  characters?: Character[];
  scenes?: Scene[];
}

export interface ProviderStatus {
  name: string;
  kind: string;
  available: boolean;
  detail: string;
  free: boolean;
  local: boolean;
  limits: string;
  license: string;
  quality: string;
  estimated_cost_usd: number;
  cooldown_s: number;
  blocked_by_cost_policy: boolean;
}

export interface SystemInfo {
  hardware: {
    os: string; cpu: string; cpu_cores: number; ram_gb: number; disk_free_gb: number;
    gpus: { vendor: string; name: string; vram_gb: number }[]; cuda: boolean; tier: string; recommendation: string; ffmpeg: boolean; note: string;
  };
  cost_policy: { spending_limit_usd: number; paid_providers_allowed: boolean; statement: string };
  comfyui_url: string;
  ai_video_mode: string;
  orders: Record<string, string[]>;
}

export interface Usage {
  total_cost_usd: number;
  items: { provider: string; kind: string; calls: number; seconds: number; cost_usd: number; cached: number; failures: number }[];
}

export interface Asset {
  id: string;
  project_id?: string;
  kind: string;
  url: string;
  provider: string | null;
  meta: Record<string, unknown>;
  created_at: string;
}
