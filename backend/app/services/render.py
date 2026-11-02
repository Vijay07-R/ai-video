"""Automatic editing + final rendering with FFmpeg.

1. Normalise each scene clip to the output size / fps / exact scene length.
2. Join clips with transitions (xfade).
3. Place narration/dialogue at each scene start, layer SFX, duck music under voice.
4. Loudness-normalise (EBU R128, -16 LUFS), optional burned-in subtitles.
5. Validate the output with ffprobe.
"""
from __future__ import annotations

import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .. import ffmpeg, languages

RESOLUTIONS = {"720p": 720, "1080p": 1080, "4k": 2160}
XFADE = {"fade": "fade", "dissolve": "dissolve", "wipeleft": "wipeleft", "wiperight": "wiperight", "slideleft": "slideleft",
         "slideright": "slideright", "fadeblack": "fadeblack", "circleopen": "circleopen", "smoothleft": "smoothleft", "cut": "fade"}


def output_size(aspect: str, quality: str) -> tuple[int, int]:
    short = RESOLUTIONS.get(quality.lower(), 720)
    if aspect == "9:16":
        return short, int(short * 16 / 9) // 2 * 2
    if aspect == "1:1":
        return short, short
    return int(short * 16 / 9) // 2 * 2, short


@dataclass
class SceneMedia:
    clip: Path
    duration: float
    transition: str = "dissolve"
    voice: Path | None = None
    voice_offset: float = 0.3
    sfx: Path | None = None
    subtitle: str = ""                       # whole-scene text (used when no timed cues)
    cues: list[tuple[float, float, str]] = field(default_factory=list)  # (start, end, text) relative to voice start


@dataclass
class RenderSpec:
    scenes: list[SceneMedia]
    out: Path
    width: int
    height: int
    fps: int = 24
    music: Path | None = None
    subtitles: bool = False
    transition_s: float = 0.5
    preset: str = field(default_factory=lambda: os.getenv("RENDER_PRESET", "veryfast"))
    crf: int = 20
    subtitle_language: str = "en"
    workers: int = 2


def scene_starts(durations: list[float], transitions: list[str], t: float) -> list[float]:
    starts, acc = [], 0.0
    for i, d in enumerate(durations):
        starts.append(round(acc, 3))
        overlap = 0.0 if i == len(durations) - 1 else (0.04 if transitions[i + 1] == "cut" else t)
        acc += d - overlap
    return starts


def total_duration(durations: list[float], transitions: list[str], t: float) -> float:
    starts = scene_starts(durations, transitions, t)
    return round(starts[-1] + durations[-1], 3)


def clip_matches(src: Path, w: int, h: int, fps: int, dur: float) -> bool:
    """A clip already at the output size/fps and long enough is used as-is (no re-encode)."""
    try:
        info = ffmpeg.probe(src)
    except ffmpeg.FFmpegError:
        return False
    v = next((x for x in info["streams"] if x["codec_type"] == "video"), None)
    if not v or (v.get("width"), v.get("height")) != (w, h) or v.get("pix_fmt") != "yuv420p":
        return False
    num, _, den = str(v.get("r_frame_rate", "0/1")).partition("/")
    rate = float(num) / float(den or 1)
    return abs(rate - fps) < 0.01 and float(info["format"].get("duration", 0)) >= dur - 0.02


def normalize_clip(src: Path, dst: Path, w: int, h: int, fps: int, dur: float) -> Path:
    if clip_matches(src, w, h, fps, dur):
        return src
    src_d = ffmpeg.duration(src)
    pad = max(0.0, dur - src_d) + 0.1
    vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={fps},"
          f"tpad=stop_mode=clone:stop_duration={pad:.3f},trim=duration={dur:.3f},setpts=PTS-STARTPTS,format=yuv420p")
    ffmpeg.run(["-i", str(src), "-an", "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", str(dst)])
    return dst


def _srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def write_srt(path: Path, items: list[tuple[float, float, str]]) -> Path:
    lines = []
    for i, (a, b, text) in enumerate([x for x in items if x[2].strip()], 1):
        lines += [str(i), f"{_srt_time(a)} --> {_srt_time(b)}", text.strip(), ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _ass_time(t: float) -> str:
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def write_ass(path: Path, items: list[tuple[float, float, str]], w: int, h: int, font: str) -> Path:
    """ASS subtitles at the real video size. Rendered with libass COMPLEX shaping, which Tamil,
    Telugu and Devanagari need (vowel signs, conjuncts); plain SRT rendering garbles them."""
    size = round(min(w, h) * 0.06)
    head = (
        "[Script Info]\nScriptType: v4.00+\nWrapStyle: 0\nScaledBorderAndShadow: yes\n"
        f"PlayResX: {w}\nPlayResY: {h}\n\n[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
        "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,"
        f"{max(2, size // 14)},1,2,{int(w * 0.06)},{int(w * 0.06)},{int(h * 0.08)},1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines = []
    for a, b, text in items:
        if text.strip() and b > a:
            t = text.strip().replace("{", "(").replace("}", ")").replace("\n", "\\N")
            lines.append(f"Dialogue: 0,{_ass_time(a)},{_ass_time(b)},Default,,0,0,0,,{t}")
    path.write_text(head + "\n".join(lines) + "\n", encoding="utf-8")
    return path


def render(spec: RenderSpec) -> dict:
    if not spec.scenes:
        raise ValueError("nothing to render")
    work = (spec.out.parent / "work").resolve()
    work.mkdir(parents=True, exist_ok=True)
    w, h, fps, T = spec.width, spec.height, spec.fps, spec.transition_s
    durs = [max(1.0, s.duration) for s in spec.scenes]
    trans = [s.transition for s in spec.scenes]

    # 1) normalise clips (in parallel; clips already in the right format are not re-encoded)
    with ThreadPoolExecutor(max_workers=max(1, spec.workers)) as pool:
        norm = list(pool.map(lambda a: normalize_clip(a[1].clip, work / f"n{a[0]:03d}.mp4", w, h, fps, durs[a[0]]),
                             enumerate(spec.scenes)))

    # 2) video chain with transitions
    starts = scene_starts(durs, trans, T)
    total = total_duration(durs, trans, T)
    args: list[str] = []
    for p in norm:
        args += ["-i", str(p)]
    fc, last = [], "[0:v]"
    for i in range(1, len(norm)):
        tr = trans[i]
        dur = 0.04 if tr == "cut" else T
        off = starts[i]
        fc.append(f"{last}[{i}:v]xfade=transition={XFADE.get(tr, 'dissolve')}:duration={dur}:offset={off:.3f}[x{i}]")
        last = f"[x{i}]"
    vlabel = last

    # 3) audio
    n_in = len(norm)
    voice_labels, sfx_labels = [], []
    for i, s in enumerate(spec.scenes):
        if s.voice and s.voice.exists():
            args += ["-i", str(s.voice)]
            ms = int((starts[i] + s.voice_offset) * 1000)
            fc.append(f"[{n_in}:a]aformat=sample_rates=48000:channel_layouts=stereo,adelay={ms}|{ms}[v{i}]")
            voice_labels.append(f"[v{i}]")
            n_in += 1
        if s.sfx and s.sfx.exists():
            args += ["-i", str(s.sfx)]
            ms = int(starts[i] * 1000)
            fc.append(f"[{n_in}:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=0:{durs[i]:.3f},"
                      f"afade=t=out:st={max(0, durs[i] - 0.4):.3f}:d=0.4,volume=0.45,adelay={ms}|{ms}[s{i}]")
            sfx_labels.append(f"[s{i}]")
            n_in += 1
    music_label = None
    if spec.music and spec.music.exists():
        args += ["-stream_loop", "-1", "-i", str(spec.music)]
        fc.append(f"[{n_in}:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=0:{total:.3f},"
                  f"afade=t=out:st={max(0, total - 2.5):.3f}:d=2.5,volume=0.32[mus]")
        music_label = "[mus]"
        n_in += 1

    mix_inputs = []
    if voice_labels:
        fc.append(f"{''.join(voice_labels)}amix=inputs={len(voice_labels)}:normalize=0:dropout_transition=0[vox]")
        if music_label:
            fc.append("[vox]asplit=2[vox1][vox2]")
            fc.append(f"{music_label}[vox2]sidechaincompress=threshold=0.04:ratio=6:attack=30:release=500[duck]")
            mix_inputs += ["[vox1]", "[duck]"]
        else:
            mix_inputs.append("[vox]")
    elif music_label:
        mix_inputs.append(music_label)
    mix_inputs += sfx_labels
    if mix_inputs:
        fc.append(f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:normalize=0:dropout_transition=0,"
                  f"apad,atrim=0:{total:.3f},loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[aout]")
    else:
        fc.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{total:.3f}[aout]")

    # 4) subtitles
    cwd = None
    if spec.subtitles:
        items = []
        for i, s in enumerate(spec.scenes):
            base = starts[i] + s.voice_offset
            scene_end = starts[i] + durs[i]
            if s.cues:
                items += [(base + a, min(base + b, scene_end), t) for a, b, t in s.cues if t.strip() and base + a < scene_end]
            elif s.subtitle:
                vd = ffmpeg.duration(s.voice) if s.voice and s.voice.exists() else durs[i] - 0.6
                items.append((base, min(base + vd, scene_end), s.subtitle))
        if items:
            write_srt(work / "subs.srt", items)  # also kept as a downloadable caption file
            font, font_dir = languages.subtitle_font(spec.subtitle_language)
            write_ass(work / "subs.ass", items, w, h, font)
            fonts = work / "fonts"  # relative fontsdir avoids Windows drive-letter escaping in filter strings
            fonts.mkdir(exist_ok=True)
            for f in font_dir.glob("*.ttf"):
                if not (fonts / f.name).exists():
                    shutil.copy(f, fonts / f.name)
            fc.append(f"{vlabel}ass=subs.ass:fontsdir=fonts:shaping=complex[vsub]")
            vlabel = "[vsub]"
            cwd = work

    if vlabel == "[0:v]":
        fc.append("[0:v]null[vfinal]")
        vlabel = "[vfinal]"

    out = spec.out.resolve()
    cmd = [*args, "-filter_complex", ";".join(fc), "-map", vlabel, "-map", "[aout]",
           "-c:v", "libx264", "-preset", spec.preset, "-crf", str(spec.crf), "-pix_fmt", "yuv420p", "-r", str(fps),
           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", f"{total:.3f}", str(out)]
    old = os.getcwd()
    try:
        if cwd:
            os.chdir(cwd)
        ffmpeg.run(cmd)
    finally:
        os.chdir(old)
    return validate(out, w, h, total)


def validate(path: Path, w: int, h: int, expected_s: float) -> dict:
    info = ffmpeg.probe(path)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    dur = float(info["format"]["duration"])
    problems = []
    if not v:
        problems.append("no video stream")
    elif (v["width"], v["height"]) != (w, h):
        problems.append(f"size {v['width']}x{v['height']} != {w}x{h}")
    if not a:
        problems.append("no audio stream")
    if abs(dur - expected_s) > 0.6:
        problems.append(f"duration {dur:.2f}s != expected {expected_s:.2f}s")
    return {"path": str(path), "duration_s": round(dur, 2), "width": v and v["width"], "height": v and v["height"],
            "video_codec": v and v["codec_name"], "audio_codec": a and a["codec_name"],
            "size_mb": round(int(info["format"].get("size", 0)) / 2**20, 2), "ok": not problems, "problems": problems}
