"""The production pipeline.

Every stage is idempotent: finished work is stored in the DB / data folder and
skipped on re-run, so jobs resume after a crash, a pause (free quota exhausted),
cancellation or a single-scene regeneration.

Speed: independent work runs concurrently (GPU images || CPU music + sound
effects; animated clips in parallel), models stay loaded between scenes, unchanged
images come from the cache, clips are produced at the final size so the renderer
does not re-encode them, and AI video is limited to a time budget.
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from .. import ffmpeg, languages
from ..config import get_settings
from ..db import session_scope
from ..models import Asset, Character, Job, Project, Scene
from ..providers import get_manager
from ..providers.base import ClipRequest, ProviderError
from ..storage import absolute, project_dir, rel
from . import consistency, reference
from .render import RenderSpec, SceneMedia, output_size, render
from .story import TRANSITION_S, build_prompt, identity_prompt, normalize_story, subtitle_lang

log = logging.getLogger("pipeline")

# display order = run order (images run at the same time as music + sfx)
STAGES = ["analysis", "story", "characters", "voice", "images", "music", "sfx", "video", "render", "qc"]
WEIGHTS = {"analysis": 2, "story": 8, "characters": 8, "voice": 8, "images": 22, "video": 30, "music": 6, "sfx": 4, "render": 10, "qc": 2}
NEGATIVE = "text, watermark, logo, signature, blurry, deformed, extra limbs, extra heads, mutated paws, low quality, jpeg artifacts, human"
MONTAGE = "motion-comic"


class Cancelled(Exception):
    pass


class AwaitingApproval(Exception):
    pass


def _seed(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def workers() -> int:
    n = get_settings().parallel_jobs
    return n if n > 0 else max(1, min(4, (os.cpu_count() or 2) - 0))


def segment_cues(text: str, start: float, dur: float) -> list[tuple[float, float, str]]:
    """Split one spoken segment into short cues, timed in proportion to text length."""
    chunks = languages.split_cues(text)
    total = sum(len(c) for c in chunks) or 1
    cues, t = [], start
    for c in chunks:
        d = dur * len(c) / total
        cues.append((round(t, 3), round(t + d, 3), c))
        t += d
    return cues


class Pipeline:
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.s = get_settings()
        self.m = get_manager()
        self._lock = threading.Lock()
        self.warnings: list[str] = []
        with session_scope() as db:
            job = db.get(Job, job_id)
            self.project_id = job.project_id
            self.params = dict(job.params or {})
            if not job.stages:
                job.stages = {k: {"status": "waiting", "detail": ""} for k in STAGES}
        self.dir = project_dir(self.project_id)

    # ------------------------------------------------------------ job state
    def stage(self, name: str, status: str, detail: str = "", done: int | None = None, total: int | None = None) -> None:
        now = time.time()
        with self._lock, session_scope() as db:
            job = db.get(Job, self.job_id)
            stages = {k: dict(v) for k, v in (job.stages or {}).items()}
            st = stages.get(name, {})
            if status == "processing" and st.get("status") != "processing":
                st["started"] = now
            st.update({"status": status, "detail": detail})
            if done is not None:
                st["done"] = done
            if total is not None:
                st["total"] = total
            if status in ("completed", "skipped", "failed"):
                st["finished"] = now
                st["elapsed_s"] = round(now - st.get("started", now), 2)
            elif st.get("started"):
                st["elapsed_s"] = round(now - st["started"], 2)
            stages[name] = st
            job.stages = stages
            done_w = sum(WEIGHTS[k] for k, v in stages.items() if v.get("status") in ("completed", "skipped"))
            part_w = sum(WEIGHTS[k] * v.get("done", 0) / v["total"] for k, v in stages.items()
                         if v.get("status") == "processing" and v.get("total"))
            job.progress = round(min(99.0, (done_w + part_w) / sum(WEIGHTS.values()) * 100), 1)  # 100 only after QC
            if status == "processing":
                job.message = f"{name}: {detail}" if detail else name
            if job.cancel_requested:
                raise Cancelled()

    def check_cancel(self) -> None:
        with session_scope() as db:
            if db.get(Job, self.job_id).cancel_requested:
                raise Cancelled()

    def project(self, db) -> Project:
        return db.get(Project, self.project_id)

    def _asset(self, db, kind: str, file: Path, provider: str | None, **meta) -> None:
        db.add(Asset(project_id=self.project_id, kind=kind, path=rel(file), provider=provider,
                     meta={k: v for k, v in meta.items() if k != "path"}))

    def warn(self, msg: str) -> None:
        if msg not in self.warnings:
            self.warnings.append(msg)
            with session_scope() as db:
                p = self.project(db)
                ws = list((p.settings or {}).get("warnings", []))
                if msg not in ws:
                    p.settings = {**(p.settings or {}), "warnings": ws + [msg]}

    # ------------------------------------------------------------ run
    def run(self) -> None:
        with session_scope() as db:
            p = self.project(db)
            p.status = "generating"
            p.settings = {**(p.settings or {}), "warnings": []}
        for name in ("analysis", "story", "characters", "voice"):
            self.check_cancel()
            getattr(self, f"do_{name}")()
        self.m.release("voice")  # free TTS memory before the GPU-heavy image stage
        self.check_cancel()
        # GPU work (images) and CPU work (music, sound effects) at the same time
        with ThreadPoolExecutor(max_workers=2) as pool:
            gpu = pool.submit(self.do_images)
            cpu = pool.submit(lambda: (self.do_music(), self.do_sfx()))
            gpu.result()
            cpu.result()
        self.check_cancel()
        self.do_video()
        self.check_cancel()
        self.do_render()
        self.do_qc()
        with session_scope() as db:
            self.project(db).status = "completed"

    # ------------------------------------------------------------ stages
    def do_analysis(self) -> None:
        with session_scope() as db:
            p = self.project(db)
            st = dict(p.settings or {})
            if p.story or st.get("reference_analysis") or not p.reference_file:
                self.stage("analysis", "skipped" if not p.reference_file else "completed",
                           "no reference file" if not p.reference_file else "already analysed")
                return
            ref = p.reference_file
        self.stage("analysis", "processing", "measuring reference style")
        try:
            a = reference.analyze(absolute(ref))
            notes = reference.to_style_notes(a)
        except Exception as e:  # reference is optional; never block the video
            self.stage("analysis", "completed", f"reference not usable: {e}")
            return
        with session_scope() as db:
            p = self.project(db)
            p.settings = {**(p.settings or {}), "reference_analysis": a, "reference_notes": notes}
        self.stage("analysis", "completed", notes[:120])

    def do_story(self) -> None:
        with session_scope() as db:
            p = self.project(db)
            if p.story and p.scenes:
                self.stage("story", "completed", "already written")
                return
            pdict = {"animal": p.animal, "prompt": p.prompt, "script": p.script, "reference_url": p.reference_url, "settings": p.settings or {}}
        st = pdict["settings"]
        lang, sub = st.get("language", "en"), subtitle_lang(st)
        self.stage("story", "processing", f"writing story in {languages.get(lang).name}")
        system, prompt = build_prompt(pdict, st.get("reference_notes"))
        duration = int(st.get("duration_s", 30))
        cast = st.get("cast") or [pdict["animal"]]

        def fn(provider):
            raw = provider.generate_json(system, prompt)
            try:
                return normalize_story(raw, duration, cast[0], lang, sub, cast)
            except ProviderError as e:  # one repair attempt on the same provider
                fixed = provider.generate_json(system, f"{prompt}\n\nYour previous answer was invalid ({e}). Return the complete, valid JSON object.")
                return normalize_story(fixed, duration, cast[0], lang, sub, cast)

        res = self.m.call("llm", fn, cache_payload={"system": system, "prompt": prompt}, project_id=self.project_id)
        story = res.value
        with session_scope() as db:
            p = self.project(db)
            p.story = {**story, "llm_provider": res.provider}
            if not p.title or p.title.lower().startswith("untitled"):
                p.title = story["title"]
            for c in list(p.characters):
                db.delete(c)
            for sc in list(p.scenes):
                db.delete(sc)
            db.flush()
            for c in story["characters"]:
                db.add(Character(project_id=p.id, key=c["key"], name=c["name"], profile=c,
                                 identity_prompt=identity_prompt(c), seed=_seed(p.id, c["key"]) % 2**31))
            for sc in story["scenes"]:
                db.add(Scene(project_id=p.id, number=sc["number"], duration_s=sc["duration_s"], data=sc))
        self.stage("story", "completed", f"{len(story['scenes'])} scenes in {languages.get(lang).name} via {res.provider}"
                   f"{' (cached)' if res.cached else ''}")

    # -- images (shared by characters + scenes) --------------------------------
    def _image(self, prompt: str, w: int, h: int, seed: int, out: Path, init: Path | None = None, denoise: float = 1.0):
        """Generate one image; identical requests are served from the cache (no GPU time)."""
        payload = {"p": prompt, "n": NEGATIVE, "w": w, "h": h, "seed": seed, "init": str(init) if init else None,
                   "d": denoise, "ckpt": self.s.comfy_image_checkpoint, "steps": self.s.comfy_image_steps}

        def ser(path):
            return {"path": rel(path)}

        def de(hit):
            src = absolute(hit["path"])
            if not src.exists():
                return None
            if src.resolve() != out.resolve():
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(src, out)
            return out

        def fn(pr):
            long = self.s.image_long_side or getattr(pr, "long_side", lambda: 1024)()
            scale = long / max(w, h)
            return pr.generate(prompt, NEGATIVE, int(w * scale), int(h * scale), seed, out, init, denoise)

        return self.m.call("image", fn, cache_payload=payload, serialize=ser, deserialize=de, project_id=self.project_id)

    def do_characters(self) -> None:
        with session_scope() as db:
            p = self.project(db)
            style = (p.story or {}).get("visual_style", "")
            todo = [(c.id, c.key, c.identity_prompt, c.seed) for c in p.characters
                    if not c.reference_image or not absolute(c.reference_image).exists()]
            approve = bool((p.settings or {}).get("approve_storyboard")) and not self.params.get("approved")
        for i, (cid, key, ident, seed) in enumerate(todo):
            self.stage("characters", "processing", f"designing {key}", done=i, total=len(todo))
            out = self.dir / "characters" / f"{key}.png"
            prompt = (f"character reference sheet, full body portrait of {ident}, {style}, centered, facing camera three-quarter view, "
                      "neutral soft studio lighting, plain light grey background, highly detailed, sharp focus")
            res = self._image(prompt, 1024, 1024, seed, out)
            with session_scope() as db:
                db.get(Character, cid).reference_image = rel(out)
                self._asset(db, "image", out, res.provider, role="character_reference", character=key, cached=res.cached)
        self.stage("characters", "completed", f"{len(todo)} designed" if todo else "already designed", done=len(todo), total=len(todo))
        if approve:
            with session_scope() as db:
                self.project(db).status = "awaiting_approval"
            raise AwaitingApproval()

    # -- voice -------------------------------------------------------------------
    def do_voice(self) -> None:
        with session_scope() as db:
            p = self.project(db)
            st = p.settings or {}
            lang = st.get("language", "en")
            sub = subtitle_lang(st)
            char_keys = sorted(c.key for c in p.characters)
            todo = [(sc.id, sc.number, sc.data) for sc in p.scenes if not sc.voice_path or not absolute(sc.voice_path).exists()]
        L = languages.get(lang)
        provider, reasons = self.m.first_available("voice", language=lang)
        if provider is None:
            raise ProviderError(f"No free {L.name} voice is installed: " + "; ".join(f"{k}: {v}" for k, v in reasons.items()))
        if provider.name == "espeak":
            self.warn(f"{L.name} narration uses eSpeak (robotic) because no natural {L.name} voice is installed. "
                      f"Install Piper or Indic Parler-TTS for natural speech.")
        used = set()
        for idx, (sid, num, data) in enumerate(todo):
            segments = []  # (spoken text, subtitle text, speaker key)
            if data.get("narration"):
                segments.append((data["narration"], data.get("narration_subtitle") if sub else data["narration"], None))
            for d in data.get("dialogue", []):
                segments.append((d["line"], d.get("subtitle") if sub else d["line"], d.get("character")))
            if not segments:
                with session_scope() as db:
                    db.get(Scene, sid).voice_path = None
                continue
            self.stage("voice", "processing", f"scene {num} in {L.name}", done=idx, total=len(todo))
            parts, cues, t = [], [], 0.0
            for j, (text, subtitle, who) in enumerate(segments):
                part = self.dir / "voice" / f"s{num:02d}_{j}.wav"

                def fn(pr, text=text, who=who, part=part):
                    vs = pr.voices(lang) if hasattr(pr, "voices") else []
                    voice = None
                    if vs:
                        voice = vs[0] if who in (None, "", "narrator") or who not in char_keys else \
                            (vs[1:] or vs)[char_keys.index(who) % len(vs[1:] or vs)]
                    return pr.synthesize(text, part, voice, lang)

                res = self.m.call("voice", fn, needs={"language": lang}, project_id=self.project_id)
                used.add(res.provider)
                d = ffmpeg.duration(part)
                cues += segment_cues(subtitle or text, t, d)
                parts.append(part)
                t += d + 0.25
            out = self.dir / "voice" / f"s{num:02d}.wav"
            inputs, fc = [], []
            for k, pth in enumerate(parts):
                inputs += ["-i", str(pth)]
                fc.append(f"[{k}:a]aformat=sample_rates=48000:channel_layouts=stereo,apad=pad_dur=0.25[p{k}]")
            fc.append("".join(f"[p{k}]" for k in range(len(parts))) + f"concat=n={len(parts)}:v=0:a=1[a]")
            ffmpeg.run([*inputs, "-filter_complex", ";".join(fc), "-map", "[a]", str(out)])
            vd = ffmpeg.duration(out)
            with session_scope() as db:
                sc = db.get(Scene, sid)
                sc.voice_path = rel(out)
                sc.data = {**sc.data, "cues": cues, "voice_provider": res.provider}
                if vd + 0.6 > sc.duration_s:  # never cut a line off: lengthen the scene
                    sc.duration_s = round(vd + 0.6, 2)
                self._asset(db, "voice", out, res.provider, scene=num, duration_s=round(vd, 2), language=lang)
        if todo:
            self._fit_duration()
        self.stage("voice", "completed", (f"{len(todo)} scenes in {L.name} via {', '.join(sorted(used))}") if todo else "already voiced",
                   done=len(todo), total=len(todo))

    def _fit_duration(self) -> None:
        """Speech that runs long lengthens its scene; win that time back from scenes with
        spare time (never cutting speech) so the film stays close to the requested length."""
        with session_scope() as db:
            p = self.project(db)
            scenes = list(p.scenes)
            target = float((p.settings or {}).get("duration_s", 60)) + TRANSITION_S * (len(scenes) - 1)
            speech = {sc.id: ffmpeg.duration(absolute(sc.voice_path)) for sc in scenes if sc.voice_path}
            # If the words themselves don't fit, speak up to 15 % faster (pitch preserved); beyond that the
            # film runs a little long rather than cutting words.
            gaps = 0.6 * len(speech) + 2.5 * (len(scenes) - len(speech))
            factor = min(1.15, (sum(speech.values()) + gaps) / target) if speech else 1.0
            if factor > 1.02:
                for sc in scenes:
                    if sc.id not in speech:
                        continue
                    src = absolute(sc.voice_path)
                    tmp = src.with_name(src.stem + "_fit.wav")
                    ffmpeg.run(["-i", str(src), "-filter:a", f"atempo={factor:.3f}", str(tmp)])
                    os.replace(tmp, src)
                    speech[sc.id] = ffmpeg.duration(src)
                    sc.data = {**sc.data, "cues": [[a / factor, b / factor, t] for a, b, t in sc.data.get("cues", [])],
                               "speech_tempo": round(factor, 3)}
                    sc.duration_s = round(max(float(sc.data.get("duration_s", 2.5)), speech[sc.id] + 0.6), 2)
                self.warn(f"The narration was too long for the requested length, so it is spoken {factor - 1:.0%} faster.")
            need = {sc.id: (speech[sc.id] + 0.6 if sc.id in speech else 2.5) for sc in scenes}
            over = sum(sc.duration_s for sc in scenes) - target
            if over <= 0.5:
                return
            slack = {sc.id: max(0.0, sc.duration_s - max(need[sc.id], 2.5)) for sc in scenes}
            total_slack = sum(slack.values())
            if total_slack <= 0:
                return
            cut = min(over, total_slack)
            for sc in scenes:
                sc.duration_s = round(sc.duration_s - cut * slack[sc.id] / total_slack, 2)

    def do_images(self) -> None:
        with session_scope() as db:
            p = self.project(db)
            st = p.settings or {}
            style = (p.story or {}).get("visual_style", st.get("style", ""))
            chars = {c.key: (c.identity_prompt, c.reference_image, c.seed) for c in p.characters}
            todo = [(sc.id, sc.number, sc.data) for sc in p.scenes if not sc.image_path or not absolute(sc.image_path).exists()]
            aspect = st.get("aspect_ratio", "16:9")
            mode = st.get("consistency_mode", "prompt")
        w, h = {"9:16": (576, 1024), "1:1": (1024, 1024)}.get(aspect, (1024, 576))
        state = {"done": 0, "flagged": 0}
        self.stage("images", "processing", f"0/{len(todo)} scenes", done=0, total=len(todo))

        def one(item):
            sid, num, d = item
            keys = d.get("characters") or list(chars)[:1]
            idents = "; ".join(chars[k][0] for k in keys if k in chars)
            prompt = (f"{style}. {d['image_prompt']}. Characters: {idents}. Environment: {d.get('environment', '')}. "
                      f"{d.get('camera_angle', '')}, {d.get('lighting', '')} lighting, mood: {d.get('emotions', '')}. "
                      "cinematic composition, highly detailed")
            main = chars.get(keys[0]) if keys else None
            ref = absolute(main[1]) if main and main[1] else None
            seed = (main[2] if main else _seed(self.project_id, num)) + num + 1000 * int(d.get("variant", 0))
            init = ref if (mode == "img2img" and ref and len(keys) == 1) else None
            out = self.dir / "images" / f"s{num:02d}.png"
            res = self._image(prompt, w, h, seed, out, init, 0.8)
            score, flag = consistency.check(ref, out)
            with session_scope() as db:
                sc = db.get(Scene, sid)
                sc.image_path, sc.consistency_score, sc.consistency_flag = rel(out), score, flag
                self._asset(db, "image", out, res.provider, scene=num, prompt=prompt[:1000], cached=res.cached)
            with self._lock:
                state["done"] += 1
                state["flagged"] += int(flag)
            self.stage("images", "processing", f"{state['done']}/{len(todo)} scenes", done=state["done"], total=len(todo))

        # A few requests in flight keeps ComfyUI's queue full; it runs them back to back with the model loaded once.
        with ThreadPoolExecutor(max_workers=3) as pool:
            for f in [pool.submit(one, it) for it in todo]:
                f.result()
        self.m.release("image")  # ask ComfyUI to unload the image model before video generation
        fl = state["flagged"]
        self.stage("images", "completed", (f"{len(todo)} images" + (f", {fl} flagged for consistency" if fl else "")) if todo
                   else "already generated", done=len(todo), total=len(todo))

    def do_video(self) -> None:
        with session_scope() as db:
            p = self.project(db)
            st = p.settings or {}
            style = (p.story or {}).get("visual_style", "")
            todo = [(sc.id, sc.number, sc.data, sc.duration_s, sc.image_path) for sc in p.scenes
                    if not sc.video_path or not absolute(sc.video_path).exists()]
        # Clips are produced at the final size (max 1080p) so the renderer can use them without re-encoding.
        q = st.get("quality", "720p")
        w, h = output_size(st.get("aspect_ratio", "16:9"), "1080p" if q in ("1080p", "4k") else "720p")
        mode = st.get("motion", "auto")  # auto | ai | montage
        ai, _ = self.m.first_available("video") if mode != "montage" else (None, {})
        use_ai = ai is not None and ai.name != MONTAGE
        budget = float(st.get("ai_video_budget_min", self.s.ai_video_budget_min)) * 60
        state = {"done": 0, "ai": 0, "ai_time": 0.0, "montage": 0}
        lock = threading.Lock()

        def req(d, dur, img, num):
            return ClipRequest(image=absolute(img), prompt=f"{d.get('video_prompt', '')}. {style}", duration_s=dur, width=w, height=h,
                               camera=d.get("camera_movement", "slow push in"), seed=_seed(self.project_id, "v", num) % 2**31)

        def save(sid, num, out, provider):
            with session_scope() as db:
                sc = db.get(Scene, sid)
                sc.video_path, sc.video_provider, sc.status = rel(out), provider, "ready"
                self._asset(db, "video", out, provider, scene=num, ai_video=provider != MONTAGE)
            with lock:
                state["done"] += 1
                state["montage" if provider == MONTAGE else "ai"] += 1
            self.stage("video", "processing", f"{state['done']}/{len(todo)} clips", done=state["done"], total=len(todo))

        self.stage("video", "processing", f"0/{len(todo)} clips", done=0, total=len(todo))
        montage = []
        for sid, num, d, dur, img in todo:
            if not use_ai:
                montage.append((sid, num, d, dur, img))
                continue
            avg = state["ai_time"] / state["ai"] if state["ai"] else 0.0
            if state["ai"] and state["ai_time"] + avg > budget:
                montage.append((sid, num, d, dur, img))  # budget used up: remaining scenes become montage
                continue
            self.check_cancel()
            out = self.dir / "clips" / f"s{num:02d}.mp4"
            t0 = time.time()
            res = self.m.call("video", lambda pr, r=req(d, dur, img, num): pr.generate(r, out), project_id=self.project_id)
            state["ai_time"] += time.time() - t0
            save(sid, num, out, res.provider)
        if use_ai and montage:
            self.warn(f"AI video budget ({budget / 60:.0f} min) reached: {len(montage)} scene(s) use animated image montage instead of AI video.")

        def mk(item):
            sid, num, d, dur, img = item
            out = self.dir / "clips" / f"s{num:02d}.mp4"
            res = self.m.call("video", lambda pr: pr.generate(req(d, dur, img, num), out), only=[MONTAGE], project_id=self.project_id)
            save(sid, num, out, res.provider)

        with ThreadPoolExecutor(max_workers=workers()) as pool:
            for f in [pool.submit(mk, it) for it in montage]:
                f.result()
        self.m.release("video")
        detail = f"{state['ai']} AI video clip(s), {state['montage']} animated montage clip(s)" if todo else "already generated"
        self.stage("video", "completed", detail, done=len(todo), total=len(todo))

    def do_music(self) -> None:
        with session_scope() as db:
            p = self.project(db)
            existing = [a for a in p.assets if a.kind == "music" and absolute(a.path).exists()]
            total = sum(sc.duration_s for sc in p.scenes)
            story = p.story or {}
            desc = story.get("music_theme", "") + ". " + " ".join(sc.data.get("music", "") + " " + sc.data.get("emotions", "") for sc in p.scenes)
        if existing:
            self.stage("music", "completed", "already composed")
            return
        self.stage("music", "processing", "composing original score")
        out = self.dir / "music" / "score.wav"
        res = self.m.call("music", lambda pr: pr.compose(desc[:600], total + 1, out, _seed(self.project_id, "music") % 2**31), project_id=self.project_id)
        with session_scope() as db:
            self._asset(db, "music", out, res.provider, duration_s=round(total, 1))
        self.stage("music", "completed", f"via {res.provider}")

    def do_sfx(self) -> None:
        with session_scope() as db:
            p = self.project(db)
            todo = [(sc.id, sc.number, sc.data, sc.duration_s) for sc in p.scenes if not sc.sfx_path or not absolute(sc.sfx_path).exists()]
        state = {"done": 0}

        def one(item):
            sid, num, d, dur = item
            cues = list(d.get("sfx", [])) + [d.get("environment", "")]
            out = self.dir / "sfx" / f"s{num:02d}.wav"
            res = self.m.call("sfx", lambda pr: pr.create(cues, dur, out, _seed(self.project_id, "sfx", num) % 2**31), project_id=self.project_id)
            with session_scope() as db:
                db.get(Scene, sid).sfx_path = rel(out)
                self._asset(db, "sfx", out, res.provider, scene=num)
            with self._lock:
                state["done"] += 1
            self.stage("sfx", "processing", f"{state['done']}/{len(todo)} scenes", done=state["done"], total=len(todo))

        with ThreadPoolExecutor(max_workers=workers()) as pool:
            for f in [pool.submit(one, it) for it in todo]:
                f.result()
        self.stage("sfx", "completed", f"{len(todo)} scenes" if todo else "already created", done=len(todo), total=len(todo))

    def do_render(self) -> None:
        with session_scope() as db:
            p = self.project(db)
            st = p.settings or {}
            music = next((absolute(a.path) for a in sorted(p.assets, key=lambda a: a.created_at, reverse=True) if a.kind == "music"), None)
            scenes = [SceneMedia(clip=absolute(sc.video_path), duration=sc.duration_s, transition=sc.data.get("transition", "dissolve"),
                                 voice=absolute(sc.voice_path) if sc.voice_path else None,
                                 sfx=absolute(sc.sfx_path) if sc.sfx_path else None,
                                 cues=[tuple(c) for c in sc.data.get("cues", [])])
                      for sc in p.scenes]
            providers = sorted({sc.video_provider for sc in p.scenes if sc.video_provider})
        aspect, quality = st.get("aspect_ratio", "16:9"), st.get("quality", "720p")
        sub_lang = subtitle_lang(st) or st.get("language", "en")
        w, h = output_size(aspect, quality)
        self.stage("render", "processing", f"editing {len(scenes)} scenes at {w}x{h}")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        out = self.dir / "render" / f"final_{aspect.replace(':', 'x')}_{quality}_{stamp}.mp4"
        result = render(RenderSpec(scenes=scenes, out=out, width=w, height=h, music=music, subtitles=bool(st.get("subtitles", True)),
                                   subtitle_language=sub_lang, workers=workers()))
        notes = list(self.warnings)
        if quality == "4k":
            notes.append("4K output is upscaled from lower-resolution generation (not native 4K).")
        if MONTAGE in providers:
            notes.append("Some or all scenes are an animated image montage (still AI images with camera moves), not AI-generated video.")
        result.update(notes=notes, video_providers=providers, language=st.get("language", "en"), subtitle_language=sub_lang)
        self.result, self.candidate = result, out
        self.stage("render", "completed", f"{result['duration_s']} s, {result['size_mb']} MB")

    def do_qc(self) -> None:
        r, out = getattr(self, "result", None), getattr(self, "candidate", None)
        self.stage("qc", "processing", "validating MP4")
        if not r or not r["ok"]:
            problems = "; ".join(r["problems"]) if r else "no render"
            self.stage("qc", "failed", problems)
            raise ProviderError("quality check failed: " + problems)
        with session_scope() as db:
            p = self.project(db)
            p.final_video = rel(out)  # the MP4 becomes downloadable only now
            self._asset(db, "final", out, None, **r)
            flagged = sum(1 for sc in p.scenes if sc.consistency_flag)
        self.stage("qc", "completed", "video validated" + (f"; {flagged} scene(s) flagged for character consistency" if flagged else ""))


def clear_scene_outputs(project_id: str, scene_id: str, parts: list[str]) -> None:
    """Forget outputs so the next run regenerates only what was asked."""
    order = ["voice", "image", "video", "sfx"]
    with session_scope() as db:
        sc = db.get(Scene, scene_id)
        if not sc or sc.project_id != project_id:
            raise ValueError("scene not found")
        if "image" in parts and "video" not in parts:  # a new image invalidates its clip
            parts = [*parts, "video"]
        if "voice" in parts:  # timing may change -> clip + sfx must follow the new duration
            parts = [*parts, "video", "sfx"]
            sc.duration_s = float(sc.data.get("duration_s", sc.duration_s))
        for part in order:
            if part in parts:
                setattr(sc, f"{part}_path", None)
        if "image" in parts:
            sc.consistency_score, sc.consistency_flag = None, False
        sc.status = "pending"
        db.get(Project, project_id).final_video = None
