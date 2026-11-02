"""Prompt analysis + story + character profiles + storyboard in ONE LLM call.

Doing everything in a single structured request keeps a 60 s video to 1-2
Gemini requests, which matters on the small free-tier daily quota.
"""
from __future__ import annotations

import json
import re
import math

from .. import languages
from ..providers.base import ProviderError

SYSTEM = """You are the head writer, character designer and storyboard artist of an animal film studio.
You turn a short idea into a complete, ORIGINAL short film plan for AI image/video generation.
Rules:
- Return ONLY one JSON object matching the schema. No markdown.
- Animals must be described consistently: every scene's image_prompt must restate the character's
  key visual traits (species, colours, markings, eye colour, size) so images stay consistent.
- Prompts are visual and concrete (subject, action, environment, lighting, lens). No text overlays, no logos.
- Do not copy or reference copyrighted characters, films, songs or brands.
- Narration + dialogue per scene must be speakable within the scene: at most {words} words per 5 seconds in total.
- LANGUAGE: all "narration", dialogue "line" and "name_native" fields are in {lang_name} ({lang_native}) using its
  native script. {guidance}
- Every other field (prompts, descriptions, camera, sfx, music) is in English (it drives the image/video models).
- Characters keep the same name everywhere: "name" in Latin letters, "name_native" the same name written in {lang_name}.
  Use name_native inside narration and dialogue.
- Keep it suitable for all ages unless the user explicitly asks otherwise."""

SCHEMA = {
    "title": "string",
    "logline": "one sentence",
    "analysis": {"genre": "string", "tone": "string", "audience": "string", "themes": ["string"]},
    "visual_style": "one line style description applied to every image",
    "music_theme": "mood/instrumentation for the score, e.g. 'gentle strings, hopeful, warm'",
    "characters": [{
        "key": "short_id", "name": "name in Latin letters", "name_native": "same name in the narration language",
        "role": "protagonist|supporting|narrator",
        "species": "string", "age": "string", "body_shape": "string", "color": "fur/skin colours",
        "face": "facial characteristics", "eye_color": "string", "markings": "distinctive markings",
        "accessories": "clothing/accessories or 'none'", "personality": "string",
        "voice": "voice description (pitch, age, tone)",
    }],
    "scenes": [{
        "number": 1, "duration_s": 5, "description": "what happens",
        "characters": ["short_id"], "environment": "string",
        "image_prompt": "detailed still-frame prompt including character traits",
        "video_prompt": "motion prompt: what moves and how, for image-to-video",
        "camera_movement": "slow push in|pull out|pan left|pan right|tilt up|tilt down|static|tracking",
        "camera_angle": "eye level|low angle|high angle|close-up|wide shot|aerial",
        "lighting": "string", "emotions": "string",
        "dialogue": [{"character": "short_id", "line": "spoken line in the narration language"}],
        "narration": "voice-over text in the narration language (may be empty)",
        "sfx": ["short sound cues e.g. 'wind in grass', 'cub mews'"],
        "music": "music instruction for this scene",
        "transition": "fade|dissolve|wipeleft|slideleft|fadeblack|cut",
    }],
}


def scene_count(duration_s: int) -> int:
    return max(3, min(24, round(duration_s / 5)))


def subtitle_lang(st: dict) -> str | None:
    """Subtitle language when it differs from the narration language, else None."""
    sub = (st.get("subtitle_language") or "same").lower()
    lang = st.get("language", "en")
    return None if sub in ("same", "", lang) else sub


def build_prompt(project: dict, reference_notes: str | None = None) -> tuple[str, str]:
    st = project.get("settings", {})
    duration = int(st.get("duration_s", 30))
    n = scene_count(duration)
    lang = st.get("language", "en")
    L = languages.get(lang)
    words = max(6, int(L.words_per_s * 5 * 0.85))
    schema = json.loads(json.dumps(SCHEMA))
    sub = subtitle_lang(st)
    if sub:
        S = languages.get(sub)
        schema["scenes"][0]["narration_subtitle"] = f"the narration translated naturally into {S.name}"
        schema["scenes"][0]["dialogue"][0]["subtitle"] = f"the line translated naturally into {S.name}"
    cast = st.get("cast") or [project["animal"]]
    cast_line = (f"Main character animal: {cast[0]}" if len(cast) == 1 else
                 "Characters (create exactly one named character for EACH of these animals; the first is the main character): "
                 + ", ".join(cast))
    lines = [
        cast_line,
        f"Idea: {project['prompt']}",
        f"Total duration: {duration} seconds, exactly {n} scenes (about {duration / n:.1f} s each).",
        f"Visual style: {st.get('style', 'cinematic 3D animation, Pixar-like lighting, highly detailed fur')}",
        f"Aspect ratio: {st.get('aspect_ratio', '16:9')}",
        f"Narration language: {L.name} ({L.native}). Write narration and dialogue in {L.name}; prompts in English.",
        f"Voice preference: {st.get('voice', 'warm storyteller narrator')}",
    ]
    if project.get("script"):
        lines.append("The user supplied this script. Follow it faithfully and split it into the scenes:\n" + project["script"])
    if project.get("reference_url"):
        lines.append(f"The user mentioned a reference link ({project['reference_url']}); create an ORIGINAL story, do not copy it.")
    if reference_notes:
        lines.append("Style notes measured from the user's reference media (use as inspiration only): " + reference_notes)
    if sub:
        lines.append(f"Subtitles will be shown in {languages.get(sub).name}: fill narration_subtitle and each dialogue subtitle.")
    lines.append("JSON schema (follow exactly):\n" + json.dumps(schema, indent=1, ensure_ascii=False))
    system = (SYSTEM.replace("{words}", str(words)).replace("{lang_name}", L.name)
              .replace("{lang_native}", L.native).replace("{guidance}", L.guidance))
    return system, "\n".join(lines)


CAMERA_DEFAULT = "slow push in"
TRANSITION_S = 0.5  # must match RenderSpec.transition_s
TRANSITIONS = {"fade", "dissolve", "wipeleft", "wiperight", "slideleft", "slideright", "fadeblack", "cut", "circleopen", "smoothleft"}


def _s(v, default="") -> str:
    if v is None:
        return default
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v)
    return str(v).strip() or default


def _stem(word: str) -> str:
    w = word.lower().strip()
    for suf in ("es", "s"):
        if w.endswith(suf) and len(w) > 4:
            return w[: -len(suf)]
    return w


def missing_cast(cast: list[str], characters: list[dict]) -> list[str]:
    """Animals the user picked that have no matching character (by species/name words)."""
    text = " ".join(f"{c.get('species', '')} {c.get('name', '')} {c.get('role', '')}" for c in characters).lower()
    words = {_stem(w) for w in re.findall(r"[a-z]+", text)}
    out = []
    for a in cast:
        keys = [_stem(w) for w in re.findall(r"[a-z]+", a.lower()) if w not in ("baby", "little", "pet", "wild", "farm", "the")]
        if keys and not any(k in words or any(k in w or w in k for w in words if len(w) > 3) for k in keys):
            out.append(a)
    return out


def normalize_story(story: dict, duration_s: int, animal: str, language: str = "en", sub_language: str | None = None,
                    cast: list[str] | None = None) -> dict:
    """Validate the LLM output and fix structure (never invents story content)."""
    if not isinstance(story, dict):
        raise ProviderError("story is not a JSON object")
    scenes = story.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ProviderError("story has no scenes")
    chars = story.get("characters") or []
    if not isinstance(chars, list) or not chars:
        raise ProviderError("story has no characters")

    clean_chars, keys = [], set()
    for i, c in enumerate(chars):
        if not isinstance(c, dict):
            continue
        key = "".join(ch for ch in _s(c.get("key"), f"char{i + 1}").lower().replace(" ", "_") if ch.isalnum() or ch == "_")[:40] or f"char{i + 1}"
        while key in keys:
            key += "_2"
        keys.add(key)
        clean_chars.append({
            "key": key, "name": _s(c.get("name"), key.title()), "name_native": _s(c.get("name_native"), _s(c.get("name"), key.title())),
            "role": _s(c.get("role"), "supporting"),
            "species": _s(c.get("species"), animal), "age": _s(c.get("age")), "body_shape": _s(c.get("body_shape")),
            "color": _s(c.get("color")), "face": _s(c.get("face")), "eye_color": _s(c.get("eye_color")),
            "markings": _s(c.get("markings")), "accessories": _s(c.get("accessories"), "none"),
            "personality": _s(c.get("personality")), "voice": _s(c.get("voice")),
        })

    if cast and len(cast) > 1:
        missing = missing_cast(cast, clean_chars)
        if missing:
            raise ProviderError(f"story is missing a character for: {', '.join(missing)}")

    clean_scenes = []
    for i, sc in enumerate(sorted((s for s in scenes if isinstance(s, dict)), key=lambda s: s.get("number", 0) or 0)):
        img = _s(sc.get("image_prompt")) or _s(sc.get("description"))
        if not img:
            raise ProviderError(f"scene {i + 1} has no prompt or description")
        dlg = [d for d in (sc.get("dialogue") or []) if isinstance(d, dict) and _s(d.get("line"))]
        trans = _s(sc.get("transition"), "dissolve").lower()
        clean_scenes.append({
            "number": i + 1,
            "duration_s": float(sc.get("duration_s") or 5),
            "description": _s(sc.get("description"), img),
            "characters": [k for k in (sc.get("characters") or []) if k in keys] or [clean_chars[0]["key"]],
            "environment": _s(sc.get("environment")),
            "image_prompt": img,
            "video_prompt": _s(sc.get("video_prompt"), _s(sc.get("description"), img)),
            "camera_movement": _s(sc.get("camera_movement"), CAMERA_DEFAULT),
            "camera_angle": _s(sc.get("camera_angle"), "eye level"),
            "lighting": _s(sc.get("lighting")),
            "emotions": _s(sc.get("emotions")),
            "dialogue": [{"character": _s(d.get("character")), "line": _s(d.get("line")),
                          **({"subtitle": _s(d.get("subtitle"))} if sub_language else {})} for d in dlg],
            "narration": _s(sc.get("narration")),
            **({"narration_subtitle": _s(sc.get("narration_subtitle"))} if sub_language else {}),
            "sfx": [str(x) for x in (sc.get("sfx") or []) if str(x).strip()][:6],
            "music": _s(sc.get("music")),
            "transition": trans if trans in TRANSITIONS else "dissolve",
        })

    # The spoken text must really be in the requested language / script.
    spoken = " ".join([s["narration"] for s in clean_scenes] + [d["line"] for s in clean_scenes for d in s["dialogue"]])
    if not spoken.strip():
        raise ProviderError("story has no narration or dialogue")
    share = languages.script_share(spoken, language)
    if share < 0.6:
        L = languages.get(language)
        raise ProviderError(f"narration is not in {L.name} ({L.script} script): only {share:.0%} of letters match")
    if sub_language:
        subs = " ".join([s.get("narration_subtitle", "") for s in clean_scenes] + [d.get("subtitle", "") for s in clean_scenes for d in s["dialogue"]])
        if subs.strip() and languages.script_share(subs, sub_language) < 0.6:
            raise ProviderError(f"subtitles are not in {languages.get(sub_language).name}")

    # Scale durations so the FINISHED film matches the requested length: each crossfade
    # overlaps two scenes by TRANSITION_S, so the scenes together must be that much longer.
    total = sum(s["duration_s"] for s in clean_scenes) or 1
    want = duration_s + TRANSITION_S * (len(clean_scenes) - 1)
    for s in clean_scenes:
        s["duration_s"] = round(max(2.0, s["duration_s"] * want / total), 2)

    return {
        "title": _s(story.get("title"), f"The {animal.title()}"),
        "logline": _s(story.get("logline")),
        "analysis": story.get("analysis") if isinstance(story.get("analysis"), dict) else {},
        "visual_style": _s(story.get("visual_style"), "cinematic 3D animation"),
        "music_theme": _s(story.get("music_theme"), "cinematic orchestral, emotional"),
        "language": language,
        "subtitle_language": sub_language or language,
        "characters": clean_chars,
        "scenes": clean_scenes,
    }


def identity_prompt(c: dict) -> str:
    parts = [f"{c['name']}, a {c['age'] + ' ' if c.get('age') else ''}{c['species']}"]
    for label, k in (("", "body_shape"), ("", "color"), ("", "face"), ("eyes: ", "eye_color"), ("markings: ", "markings")):
        if c.get(k):
            parts.append(f"{label}{c[k]}")
    if c.get("accessories") and c["accessories"].lower() != "none":
        parts.append(f"wearing {c['accessories']}")
    return ", ".join(parts)


def words_per_second(language: str) -> float:
    return languages.get(language).words_per_s


def estimate_speech_s(text: str, language: str = "en") -> float:
    return math.ceil(len(text.split()) / words_per_second(language) * 10) / 10
