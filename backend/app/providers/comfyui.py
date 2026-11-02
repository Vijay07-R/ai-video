"""ComfyUI adapters (local, open models).

ComfyUI (https://github.com/comfyanonymous/ComfyUI) runs the open models; this
engine talks to its HTTP API:
  POST /upload/image, POST /prompt, GET /history/{id}, GET /view, GET /object_info/{node}

Workflows are built in code below (API format). To use your own graph instead,
export it from ComfyUI with "Save (API format)" into backend/workflows/<name>.json
and use "{{placeholders}}" (see README). Node and model names were written for
ComfyUI's built-in FLUX / Wan 2.2 / ACE-Step support; if your ComfyUI version
differs, the availability check reports exactly which node or model is missing.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import requests

from ..config import BASE_DIR, Settings
from ..hardware import inspect_hardware
from .base import ClipRequest, ImageProvider, MusicProvider, ProviderError, ProviderUnavailable, VideoProvider

WORKFLOW_DIR = BASE_DIR / "workflows"


class ComfyClient:
    def __init__(self, url: str, timeout_s: int = 3600, session: requests.Session | None = None):
        self.url = url.rstrip("/")
        self.timeout_s = timeout_s
        self.http = session or requests.Session()
        self.client_id = uuid.uuid4().hex
        self._object_info: dict[str, dict] = {}

    def ping(self) -> dict:
        try:
            r = self.http.get(f"{self.url}/system_stats", timeout=3)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            raise ProviderUnavailable(f"ComfyUI not reachable at {self.url}") from e

    def vram_gb(self) -> float | None:
        try:
            devs = self.ping().get("devices", [])
            return max(d.get("vram_total", 0) for d in devs) / 2**30 if devs else None
        except Exception:
            return None

    def free(self) -> None:
        """Ask ComfyUI to unload models and release GPU memory."""
        try:
            self.http.post(f"{self.url}/free", json={"unload_models": True, "free_memory": True}, timeout=10)
        except requests.RequestException:
            pass

    def node_info(self, node: str) -> dict | None:
        if node not in self._object_info:
            try:
                r = self.http.get(f"{self.url}/object_info/{node}", timeout=10)
                r.raise_for_status()
                self._object_info[node] = r.json().get(node) or {}
            except requests.RequestException:
                return None
        return self._object_info[node] or None

    def model_choices(self, node: str, field: str) -> list[str]:
        info = self.node_info(node)
        if not info:
            return []
        spec = info.get("input", {}).get("required", {}).get(field)
        if not spec:
            return []
        first = spec[0]
        if isinstance(first, list):
            return first
        if isinstance(first, str) and len(spec) > 1 and isinstance(spec[1], dict):  # newer COMBO format
            return spec[1].get("options", [])
        return []

    def require(self, nodes: list[str], models: list[tuple[str, str, str]]) -> None:
        """Raise ProviderUnavailable naming the first missing node/model."""
        self.ping()
        for n in nodes:
            if not self.node_info(n):
                raise ProviderUnavailable(f"ComfyUI node '{n}' missing (update ComfyUI)")
        for node, field, filename in models:
            choices = self.model_choices(node, field)
            if filename not in choices:
                raise ProviderUnavailable(f"model '{filename}' not found for {node}.{field}")

    def upload_image(self, path: Path) -> str:
        with open(path, "rb") as f:
            r = self.http.post(f"{self.url}/upload/image", files={"image": (path.name, f, "image/png")},
                               data={"overwrite": "true"}, timeout=120)
        if r.status_code >= 400:
            raise ProviderError(f"upload failed: {r.text[:200]}")
        d = r.json()
        return f"{d['subfolder']}/{d['name']}" if d.get("subfolder") else d["name"]

    def run(self, workflow: dict) -> list[dict]:
        """Queue a workflow, wait for it, return the list of output file descriptors."""
        try:
            r = self.http.post(f"{self.url}/prompt", json={"prompt": workflow, "client_id": self.client_id}, timeout=60)
        except requests.RequestException as e:
            raise ProviderUnavailable(f"ComfyUI unreachable: {e}") from e
        if r.status_code >= 400:
            raise ProviderError(f"ComfyUI rejected workflow: {r.text[:500]}")
        pid = r.json()["prompt_id"]
        deadline = time.time() + self.timeout_s
        while time.time() < deadline:
            time.sleep(2)
            try:
                h = self.http.get(f"{self.url}/history/{pid}", timeout=30).json()
            except (requests.RequestException, ValueError):
                continue
            if pid not in h:
                continue
            entry = h[pid]
            st = entry.get("status", {})
            if st.get("status_str") == "error":
                msgs = [m for m in st.get("messages", []) if m and m[0] == "execution_error"]
                raise ProviderError(f"ComfyUI execution error: {json.dumps(msgs)[:500]}")
            if st.get("completed") or entry.get("outputs"):
                files = []
                for node_out in entry.get("outputs", {}).values():
                    for val in node_out.values():
                        if isinstance(val, list):
                            files += [v for v in val if isinstance(v, dict) and "filename" in v]
                if not files:
                    raise ProviderError("ComfyUI finished without output files")
                return files
        try:  # don't leave a long job hogging the GPU
            self.http.post(f"{self.url}/interrupt", timeout=5)
        except requests.RequestException:
            pass
        raise ProviderError(f"ComfyUI timed out after {self.timeout_s}s")

    def download(self, f: dict, out: Path) -> Path:
        r = self.http.get(f"{self.url}/view", params={"filename": f["filename"], "subfolder": f.get("subfolder", ""),
                                                      "type": f.get("type", "output")}, timeout=300)
        if r.status_code >= 400:
            raise ProviderError(f"download failed for {f['filename']}")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(r.content)
        return out


def load_override(name: str, values: dict) -> dict | None:
    """Load backend/workflows/<name>.json and replace "{{key}}" placeholders."""
    path = WORKFLOW_DIR / f"{name}.json"
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8")
    for k, v in values.items():
        raw = raw.replace(f'"{{{{{k}}}}}"', json.dumps(v)).replace(f"{{{{{k}}}}}", str(v))
    return json.loads(raw)


# ----------------------------------------------------------------- workflows
def image_workflow(s: Settings, prompt: str, negative: str, w: int, h: int, seed: int,
                   init_image: str | None, denoise: float) -> dict:
    wf = {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": s.comfy_image_checkpoint}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["4", 1]}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "3": {"class_type": "KSampler", "inputs": {
            "seed": seed, "steps": s.comfy_image_steps, "cfg": s.comfy_image_cfg, "sampler_name": "euler",
            "scheduler": "simple", "denoise": 1.0, "model": ["4", 0], "positive": ["6", 0],
            "negative": ["7", 0], "latent_image": ["5", 0]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "ave/img", "images": ["8", 0]}},
    }
    if init_image:
        wf["10"] = {"class_type": "LoadImage", "inputs": {"image": init_image}}
        wf["12"] = {"class_type": "ImageScale", "inputs": {"image": ["10", 0], "upscale_method": "lanczos",
                                                           "width": w, "height": h, "crop": "center"}}
        wf["11"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["12", 0], "vae": ["4", 2]}}
        wf["3"]["inputs"]["latent_image"] = ["11", 0]
        wf["3"]["inputs"]["denoise"] = denoise
        del wf["5"]
    return wf


def wan_workflow(s: Settings, image_name: str, prompt: str, negative: str, w: int, h: int, length: int, seed: int, fps: int) -> dict:
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": s.comfy_wan_unet, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": s.comfy_wan_clip, "type": "wan", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": s.comfy_wan_vae}},
        "4": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["2", 0]}},
        "7": {"class_type": "Wan22ImageToVideoLatent", "inputs": {"vae": ["3", 0], "width": w, "height": h,
                                                                   "length": length, "batch_size": 1, "start_image": ["4", 0]}},
        "8": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 8.0}},
        "9": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": s.comfy_wan_steps, "cfg": 5.0, "sampler_name": "uni_pc",
                                                    "scheduler": "simple", "denoise": 1.0, "model": ["8", 0],
                                                    "positive": ["5", 0], "negative": ["6", 0], "latent_image": ["7", 0]}},
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["3", 0]}},
        "11": {"class_type": "CreateVideo", "inputs": {"images": ["10", 0], "fps": float(fps)}},
        "12": {"class_type": "SaveVideo", "inputs": {"video": ["11", 0], "filename_prefix": "ave/clip", "format": "auto", "codec": "auto"}},
    }


def acestep_workflow(s: Settings, tags: str, seconds: float, seed: int) -> dict:
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": s.comfy_music_checkpoint}},
        "2": {"class_type": "TextEncodeAceStepAudio", "inputs": {"clip": ["1", 1], "tags": tags, "lyrics": "[inst]", "lyrics_strength": 0.99}},
        "3": {"class_type": "EmptyAceStepLatentAudio", "inputs": {"seconds": float(seconds), "batch_size": 1}},
        "4": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 5.0}},
        "5": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["2", 0]}},
        "6": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": 50, "cfg": 5.0, "sampler_name": "euler", "scheduler": "simple",
                                                    "denoise": 1.0, "model": ["4", 0], "positive": ["2", 0], "negative": ["5", 0],
                                                    "latent_image": ["3", 0]}},
        "7": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "8": {"class_type": "SaveAudio", "inputs": {"audio": ["7", 0], "filename_prefix": "ave/music"}},
    }


def _snap(v: int, m: int = 32) -> int:
    return max(m, int(round(v / m)) * m)


# ----------------------------------------------------------------- adapters
class ComfyImage(ImageProvider):
    name = "comfyui-image"
    limits = "Local. ~15-60 s per image on an 8 GB GPU with FLUX schnell/Klein; many minutes on CPU."
    license = "Model-dependent: FLUX.1 schnell & FLUX.2 Klein 4B = Apache 2.0 (FLUX.1 dev is non-commercial)"
    quality_label = "AI image"

    def __init__(self, settings: Settings, client: ComfyClient | None = None):
        self.s = settings
        self.c = client or ComfyClient(settings.comfyui_url, settings.comfy_timeout_s)

    def check(self) -> tuple[bool, str]:
        try:
            self.c.require(["CheckpointLoaderSimple", "KSampler", "SaveImage"],
                           [("CheckpointLoaderSimple", "ckpt_name", self.s.comfy_image_checkpoint)])
        except ProviderUnavailable as e:
            return False, str(e)
        return True, self.s.comfy_image_checkpoint

    def long_side(self) -> int:
        """Image size that fits the GPU ComfyUI runs on (CPU-only ComfyUI gets small, fast images)."""
        v = self.c.vram_gb()
        if v is None or v < 1:
            return 640
        return 1024 if v >= 10 else 896 if v >= 7 else 768

    def release(self) -> None:
        self.c.free()

    def generate(self, prompt, negative, width, height, seed, out, init_image=None, denoise=1.0):
        w, h = _snap(width, 64), _snap(height, 64)
        init_name = self.c.upload_image(init_image) if init_image else None
        values = {"prompt": prompt, "negative": negative, "width": w, "height": h, "seed": seed,
                  "init_image": init_name or "", "denoise": denoise}
        wf = load_override("image_img2img" if init_name else "image", values) or \
            image_workflow(self.s, prompt, negative, w, h, seed, init_name, denoise)
        files = self.c.run(wf)
        img = next((f for f in files if f["filename"].lower().endswith((".png", ".jpg", ".webp"))), files[0])
        return self.c.download(img, out)


class ComfyWanVideo(VideoProvider):
    name = "comfyui-wan"
    limits = ("Local Wan 2.2 TI2V-5B image-to-video. Needs an NVIDIA GPU (8 GB with GGUF/fp8, 12 GB+ for fp16). "
              "Roughly 5-30+ minutes per 5 s clip depending on GPU.")
    license = "Apache 2.0 (Wan 2.2)"
    quality_label = "AI video"

    def __init__(self, settings: Settings, client: ComfyClient | None = None):
        self.s = settings
        self.c = client or ComfyClient(settings.comfyui_url, settings.comfy_timeout_s)

    def check(self) -> tuple[bool, str]:
        mode = self.s.ai_video_mode
        if mode == "off":
            return False, "disabled (AI_VIDEO_MODE=off)"
        if mode == "auto" and self.s.comfyui_url.startswith(("http://127.0.0.1", "http://localhost")):
            hw = inspect_hardware()
            if hw["tier"] != "gpu-video":
                return False, f"local hardware tier is '{hw['tier']}' (needs an NVIDIA GPU with 8 GB+); set AI_VIDEO_MODE=on to force"
        try:
            self.c.require(["UNETLoader", "CLIPLoader", "VAELoader", "Wan22ImageToVideoLatent", "CreateVideo", "SaveVideo"],
                           [("UNETLoader", "unet_name", self.s.comfy_wan_unet),
                            ("CLIPLoader", "clip_name", self.s.comfy_wan_clip),
                            ("VAELoader", "vae_name", self.s.comfy_wan_vae)])
        except ProviderUnavailable as e:
            return False, str(e)
        return True, self.s.comfy_wan_unet

    def release(self) -> None:
        self.c.free()

    @staticmethod
    def dims(width: int, height: int) -> tuple[int, int]:
        """Keep generation at ~480p (long side 832) for speed; the renderer upscales."""
        long_side = 832
        if width >= height:
            return long_side, _snap(long_side * height / width)
        return _snap(long_side * width / height), long_side

    def generate(self, req: ClipRequest, out: Path) -> Path:
        w, h = self.dims(req.width, req.height)
        frames = min(121, int(req.duration_s * req.fps))
        length = max(5, (frames - 1) // 4 * 4 + 1)  # Wan needs 4n+1 frames
        name = self.c.upload_image(req.image)
        prompt = f"{req.prompt}. Camera: {req.camera}."
        negative = "blurry, distorted, deformed animal, extra legs, extra heads, text, watermark, flicker, low quality"
        values = {"image": name, "prompt": prompt, "negative": negative, "width": w, "height": h,
                  "length": length, "seed": req.seed, "fps": req.fps}
        wf = load_override("wan_i2v", values) or wan_workflow(self.s, name, prompt, negative, w, h, length, req.seed, req.fps)
        files = self.c.run(wf)
        vid = next((f for f in files if f["filename"].lower().endswith((".mp4", ".webm", ".mov"))), None)
        if not vid:
            raise ProviderError("Wan workflow produced no video file")
        return self.c.download(vid, out)


class ComfyAceStepMusic(MusicProvider):
    name = "comfyui-acestep"
    limits = "Local ACE-Step music model via ComfyUI. Fast on GPU (seconds per minute of music)."
    license = "Apache 2.0 (ACE-Step v1); ACE-Step 1.5 is MIT"
    quality_label = "AI music"

    def __init__(self, settings: Settings, client: ComfyClient | None = None):
        self.s = settings
        self.c = client or ComfyClient(settings.comfyui_url, settings.comfy_timeout_s)

    def check(self) -> tuple[bool, str]:
        try:
            self.c.require(["TextEncodeAceStepAudio", "EmptyAceStepLatentAudio", "VAEDecodeAudio", "SaveAudio"],
                           [("CheckpointLoaderSimple", "ckpt_name", self.s.comfy_music_checkpoint)])
        except ProviderUnavailable as e:
            return False, str(e)
        return True, self.s.comfy_music_checkpoint

    def compose(self, description: str, duration_s: float, out: Path, seed: int = 0) -> Path:
        tags = f"instrumental, cinematic, film score, no vocals, {description}"
        values = {"tags": tags, "seconds": duration_s, "seed": seed}
        wf = load_override("music", values) or acestep_workflow(self.s, tags, duration_s, seed)
        files = self.c.run(wf)
        raw = self.c.download(files[0], out.with_suffix(Path(files[0]["filename"]).suffix or ".flac"))
        if raw.suffix != out.suffix:
            if not shutil.which("ffmpeg"):
                raise ProviderError("ffmpeg needed to convert music")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-ar", "48000", "-ac", "2", str(out)], check=True)
            raw.unlink(missing_ok=True)
        return out
