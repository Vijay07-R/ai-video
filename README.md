# Animal Video Engine (zero-cost edition)

Type an animal and a story idea, press **GENERATE VIDEO**, and get a finished MP4. The engine writes the
story, designs consistent characters, draws every scene, animates it, records narration and dialogue,
composes music, adds sound effects, edits everything together with transitions and subtitles, then
checks the result.

**Everything runs on free tiers, open-source models and your own computer.** The spending limit is $0,
paid providers are disabled in code, and nothing is billed automatically.

---

## 1. What you need

| Item | Required? | Cost | Purpose |
|---|---|---|---|
| Python 3.10+ and FFmpeg | **yes** | free | Engine and video editing |
| Node.js (once) | to build the UI | free | Builds the web interface |
| **Gemini API key** | strongly recommended | free, no card | Writes the story, characters and storyboard |
| ComfyUI + model files | **yes for AI images** | free | Images (FLUX), AI video (Wan 2.2), AI music (ACE-Step) |
| Kokoro TTS | recommended | free | Natural narration and character voices |
| Ollama | optional | free | Offline story-writing fallback when the Gemini quota runs out |

The **only key** is the free Gemini key: <https://aistudio.google.com/apikey>.

## 2. Languages

Pick **English, Tamil (தமிழ்), Telugu (తెలుగు) or Hindi (हिन्दी)** on the Create screen. The language you pick
controls the story text, character dialogue, narration, voice and subtitles. Subtitles can be turned off, or shown in
a different language from the narration (for example, Tamil narration with English subtitles).

- The story AI is told to write **originally** in that language (natural, simple, spoken-style, native script).
  Its output is **checked**: if the narration isn't actually in Tamil/Telugu/Devanagari script, it's rejected and
  rewritten. Character names stay the same in every scene (`name` + `name_native`).
- Subtitles are timed line by line to the spoken audio. They use the bundled Noto fonts and complex text shaping,
  so Tamil, Telugu and Hindi vowel signs and conjuncts render correctly.
- **Voices.** The engine never switches to another language on its own. If no voice is installed for your language,
  **Generate is blocked** with instructions to fix it. If only the robotic eSpeak voice is available, you're warned
  before generating.

| Language | Natural free voice | Fast CPU option | Fallback |
|---|---|---|---|
| English | Kokoro (Apache 2.0) | Piper | eSpeak (robotic) |
| Hindi | Kokoro, or Indic Parler-TTS | Piper Hindi voice | eSpeak (robotic) |
| Tamil | Indic Parler-TTS (Apache 2.0) | Piper Tamil voice (community) | eSpeak (robotic) |
| Telugu | Indic Parler-TTS (Apache 2.0) | Piper Telugu voice | eSpeak (robotic) |

Indic Parler-TTS (`ai4bharat/indic-parler-tts`) is a gated download: create a free Hugging Face account, accept the
terms on the model page, and run `huggingface-cli login` once. It is fast on an NVIDIA GPU and slow on CPU. On a
CPU-only PC, Piper voices are the fast option. Set them with `PIPER_VOICES` in `.env`. eSpeak NG for Windows is a free
installer from <https://github.com/espeak-ng/espeak-ng/releases>; Kokoro also needs it for Hindi pronunciation.

## 3. Speed: what to expect

Measured in the build environment (2 CPU cores, no GPU) for a 60-second 9:16 video with 12 scenes: the non-AI work
(montage clips, music, sound effects, editing, subtitles, validation) takes **about 40 seconds** after the
optimisations, down from 58. On your PC the **AI steps** add their own time:

| Step | Typical time on an 8 GB+ NVIDIA GPU | On CPU only |
|---|---|---|
| Story (Gemini free tier) | 10–40 s | same (cloud) |
| 2 character + 12 scene images (FLUX schnell, 4 steps) | ~2–4 min | 20–60+ min |
| Voice, 12 scenes (Kokoro / Piper) | < 1 min | 1–2 min |
| Voice, 12 scenes (Indic Parler-TTS) | 1–3 min | 10–30+ min |
| AI video (Wan 2.2 5B), per 5 s clip | ~5–30 min | not practical |

So **5–10 minutes for 60 seconds is realistic only with an NVIDIA GPU and animated image montage** (no Wan). True
AI video for all 12 scenes takes 1–3+ hours on consumer GPUs. **Scene motion → Auto** uses Wan for as many scenes as
fit in the AI video time budget (default 10 min) and an animated image montage for the rest, and labels which is which.
The progress screen shows the real time for every step, plus an ETA once the engine has measurements.

What the engine does for speed: images on the GPU run at the same time as music and sound effects on the CPU; several
requests stay queued in ComfyUI so the model stays loaded; montage clips render in parallel at the final size, so they
aren't encoded twice; unchanged images come from a cache; image size is matched to the GPU's memory; voice models load
once per run; and ComfyUI is asked to free GPU memory between the image and video steps.

## 4. What your hardware can do

The engine inspects your machine (Providers page) and chooses automatically.

| Your computer | Images | Scene motion | Rough time for a 60 s video |
|---|---|---|---|
| NVIDIA GPU, 12 GB+ VRAM | FLUX, fast | **Real AI video** (Wan 2.2 TI2V-5B) | 1–3+ hours (most of it is video) |
| NVIDIA GPU, 8 GB | FLUX fp8 / GGUF | AI video with GGUF/fp8 Wan (slow) or motion comic | several hours, or ~15 min in motion-comic mode |
| NVIDIA GPU, 4–6 GB / Apple Silicon | FLUX (slower) | Motion comic | ~15–40 min |
| No GPU (CPU only) | very slow (minutes per image) | Motion comic | 1–3 hours, almost all of it images |

**Motion comic** means AI-drawn still images animated with camera moves (push-in, pan, tilt, zoom),
vignette and transitions. It is **not** AI-generated motion, and the app always says when it was used.
4K exports are **upscaled**, never native 4K.

## 5. Quick start (Windows)

```bat
winget install Python.Python.3.12 Gyan.FFmpeg OpenJS.NodeJS.LTS
:: unzip the project, then:
scripts\start.bat
```

On Linux or macOS, run `scripts/start.sh`. Then open <http://localhost:8000>.

On first run this creates `backend/.env`. Add your key there and restart:

```
GEMINI_API_KEY=your-free-key
```

Docker alternative: `docker compose up --build`. ComfyUI and Ollama keep running natively, because they need the GPU.

### Hosting the control panel on Vercel (optional)

Vercel can host the **web pages only**. The engine (Python, FFmpeg, AI models) must keep running on your PC
with `scripts\start.bat`. The hosted page connects to it at `http://localhost:8000`.

1. Leave **Root Directory empty** in Vercel. The included `vercel.json` builds `frontend/` and publishes `frontend/dist`.
   (If you set Root Directory to `frontend` instead, set Framework Preset to **Vite**.)
2. Add your site to `CORS_ORIGINS` in `backend/.env` (`https://animal-video-engine.vercel.app` is allowed by default).
3. Open the site **on the same PC** that runs the engine, and choose **Allow** if Chrome asks about local network access.

The page only works on that PC, because `localhost` always means the computer the browser is running on.

## 6. Install the free AI pieces

### 6.1 ComfyUI (images, AI video, AI music)

Install the **ComfyUI Desktop** app or the portable build from <https://www.comfy.org/download>, start it
(it listens on `http://127.0.0.1:8188`), then put these files in its `models` folders.

| Purpose | File | ComfyUI folder | Source (Hugging Face) | License |
|---|---|---|---|---|
| Images | `flux1-schnell-fp8.safetensors` | `models/checkpoints` | `Comfy-Org/flux1-schnell` | Apache 2.0 |
| AI video (GPU 8 GB+) | `wan2.2_ti2v_5B_fp16.safetensors` | `models/diffusion_models` | `Comfy-Org/Wan_2.2_ComfyUI_Repackaged` | Apache 2.0 |
| | `umt5_xxl_fp8_e4m3fn_scaled.safetensors` | `models/text_encoders` | same repo | Apache 2.0 |
| | `wan2.2_vae.safetensors` | `models/vae` | same repo | Apache 2.0 |
| AI music | `ace_step_v1_3.5b.safetensors` | `models/checkpoints` | `Comfy-Org/ACE-Step_ComfyUI_repackaged` | Apache 2.0 |

Notes:

- Repositories and file names change over time. The **Free providers** page names the exact node or file
  ComfyUI is missing; change the matching `COMFY_*` setting in `.env` if your file has a different name.
- Avoid **FLUX.1 dev** if you plan to publish commercially; its license is non-commercial.
- For 8 GB cards, or to use FLUX.2 Klein 4B, IP-Adapter or GGUF models, export your own ComfyUI graph into
  `backend/workflows/` (see the README there).
- Docker on a PC with no capable GPU: set `AI_VIDEO_MODE=off` so Wan is never tried on the CPU.

### 6.2 Voices (see section 2 for Tamil, Telugu and Hindi)

Kokoro (Apache 2.0) for English and Hindi:

```bat
backend\.venv\Scripts\pip install kokoro soundfile
```

The ~330 MB model downloads on first use. Languages: English, Hindi, Spanish, French, Italian, Portuguese,
Japanese and Chinese. Fallbacks are **Piper** (set `PIPER_MODEL` to a downloaded `.onnx` voice) and
**eSpeak NG**, which sounds robotic and is a last resort only.

### 6.3 Optional: offline story writing (Ollama)

Install <https://ollama.com>, then run `ollama pull gemma3:4b`. The engine uses it automatically when the
Gemini free quota is used up.

### 6.4 Music and sound effects with no setup

If ACE-Step isn't installed, the engine composes an original score procedurally: pads, plucks, bass and
reverb, with the mood taken from the story. Sound effects are also synthesised: wind, birds, water,
rain, rustle, growls, thunder, crickets and fire. Both run on any CPU in seconds and carry no licensing
issues. They sound simpler than AI audio.

## 7. How a video is made

```
User input (animal + idea [+ script, reference file])
   │
   ▼
analysis   reference file → pacing, colour, motion notes          (OpenCV, local)
story      ONE Gemini call → title, characters, scene storyboard  (Gemini free → Ollama)
characters identity profile + reference portrait per character   (ComfyUI FLUX)
voice      narration + dialogue per scene; scene length grows to fit the speech (Kokoro → Piper → eSpeak)
images     each scene, with character traits restated + fixed seeds, colour-match check
video      image-to-video per scene                               (Wan 2.2 → motion comic)
music      score for the whole film                               (ACE-Step → procedural)
sfx        ambience + effects per scene                           (procedural)
render     normalise clips → xfade transitions → voice placement → music ducking
           → loudness normalisation (-16 LUFS) → subtitles → H.264/AAC MP4
qc         ffprobe validation: streams, size, duration
```

**Free Provider Manager** (`app/providers/manager.py`) controls every call. It:

- tries providers in the order set in `.env`, skipping any that aren't installed or running;
- on a free-quota or rate-limit error (HTTP 429), puts that provider on cooldown and switches to the next free one;
- if no free provider is left, pauses the job and shows why; it resumes automatically when the quota resets, or when you press **Resume**;
- reuses cached results for identical requests, so no quota is spent twice;
- refuses any provider that isn't free unless `ALLOW_PAID_PROVIDERS=true` **and** `SPENDING_LIMIT_USD>0`. There are no paid providers in this version.

**Resumable jobs:** every finished image, clip and audio file is saved. Restarts, pauses, cancellations
and edits only redo what's missing. In the Script & scenes tab you can edit narration, prompts, camera or
duration for one scene, then press **Re-render**. Only the affected parts are regenerated.

**Character consistency:** each character has an identity profile (species, body, colours, face, eyes,
markings, accessories, personality, voice) and a reference portrait. Every scene prompt restates those
traits and uses the character's fixed seed. "Strong consistency" mode generates scenes image-to-image from
the portrait. Each scene image gets a colour-palette match score against the portrait, and low scores are
flagged for review. This check catches wrong colours or the wrong animal; it can't prove identity.

**Reference links:** the URL is passed to the story writer as context but is **not** downloaded. Platforms
such as YouTube don't allow downloading. Upload a file you have the right to use if you want its style
measured.

## 8. Project layout

```
backend/
  app/main.py              REST API, file serving, serves the built UI
  app/worker.py            background worker (inline or `python -m app.worker`)
  app/hardware.py          OS/CPU/RAM/GPU/VRAM/disk/CUDA inspection and tier choice
  app/providers/           adapters: llm.py (Gemini, Ollama), comfyui.py (FLUX, Wan, ACE-Step),
                           motion.py, voice.py (Kokoro, Piper, eSpeak), procedural.py, manager.py
  app/services/            story.py, pipeline.py, render.py, consistency.py, reference.py
  app/models.py            projects, characters, scenes, jobs, assets, provider_usage,
                           generation_cache, error_logs, schema_version
  workflows/               optional custom ComfyUI graphs
  tests/                   42 tests, including a full prompt-to-MP4 run
frontend/                  React + TypeScript + Tailwind (Vite)
scripts/start.bat|.sh      one-command local start
Dockerfile, docker-compose.yml
```

## 9. API (summary)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/projects` | create (`auto_start` queues generation) |
| GET | `/api/projects/{id}` | project with story, characters, scenes and live job status |
| POST | `/api/projects/{id}/reference` | upload a reference video or image |
| POST | `/api/projects/{id}/generate` · `/approve` | start or resume · approve the storyboard |
| POST | `/api/jobs/{id}/cancel` · `/resume` | job control |
| PUT | `/api/scenes/{id}` · POST `/api/scenes/{id}/regenerate` | edit or regenerate one scene |
| PUT | `/api/characters/{id}` | edit a character profile (redraws its scenes) |
| GET | `/api/languages` · POST `/api/preflight` | voice per language · readiness check before generating |
| GET | `/api/system` · `/api/providers` · `/api/usage` · `/api/errors` | hardware, provider status, usage, logs |

Interactive docs are at `http://localhost:8000/docs`. If `ENGINE_ACCESS_TOKEN` is set, send
`Authorization: Bearer <token>`.

## 10. Tests

```bash
cd backend
pip install -r requirements.txt pytest
python -m pytest -q
```

The suite covers the provider manager (fallback, quotas, cooldown, cache, paid-provider block), the Gemini
and Ollama adapters (with mocked HTTP), the ComfyUI workflows, the motion-comic renderer, procedural audio,
the full FFmpeg render (transitions, ducking, subtitles), reference analysis, consistency scoring, job
pause/resume/cancel/approval, and the live REST API. The end-to-end tests use clearly labelled **test
doubles** for the LLM, image and voice models. Everything else (animation, audio, editing, rendering,
validation) runs for real.

## 11. Known limits

- The real Gemini, ComfyUI and Kokoro calls follow the official APIs, but they could not be run in the
  build environment because it had no internet access to those services and no GPU. Run the Lion test
  (section 12) on your machine first.
- Gemini free-tier quotas are small and set per model per day by Google. A 60-second video uses 1–2
  requests, and free-tier prompts may be used by Google to improve its products.
- Wan 2.2 on consumer GPUs is slow, and clips are generated at about 480p, then upscaled.
- Lip-sync isn't included; characters are narrated or voiced over.
- Auth is a single access token for local or personal use, not multi-user accounts.

## 12. Acceptance test

1. Start ComfyUI (with the FLUX checkpoint at minimum) and the engine.
2. Check that **Free providers** shows story AI, images, voice, music and SFX as *ready*.
3. Create: Language **Tamil**, Animal `Lion cub`, Story `A lion cub makes a new friend in the forest`,
   Duration 60 s, Style `cinematic 3D animation`, Format 9:16. Repeat with English, Telugu and Hindi.
4. Watch the measured step times, preview the result and download the MP4.

The same flow runs offline with `python tests/acceptance_run.py ta` (or `en`, `te`, `hi`; add `en` as a second
argument for English subtitles). It uses a pre-written native story and stand-in images, and real voice, montage,
music, subtitles, rendering and validation.
