from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class VideoSettings(BaseModel):
    duration_s: int = Field(30, ge=10, le=180)
    aspect_ratio: Literal["16:9", "9:16", "1:1"] = "16:9"
    quality: Literal["720p", "1080p", "4k"] = "720p"
    style: str = Field("cinematic 3D animation, soft volumetric lighting, detailed fur", max_length=300)
    language: Literal["en", "ta", "te", "hi"] = "en"
    voice: str = Field("warm, gentle storyteller", max_length=200)
    subtitles: bool = True
    subtitle_language: Literal["same", "en", "ta", "te", "hi"] = "same"
    # auto = AI video for as many scenes as fit in the time budget, montage for the rest
    motion: Literal["auto", "ai", "montage"] = "auto"
    ai_video_budget_min: float = Field(10, ge=0, le=600)
    approve_storyboard: bool = False
    consistency_mode: Literal["prompt", "img2img"] = "prompt"


class ProjectCreate(BaseModel):
    title: str = Field("", max_length=200)
    animal: str = Field(..., min_length=2, max_length=400)
    # The characters: each entry is one animal; the first is the main character.
    cast: list[str] = Field(default_factory=list, max_length=6)
    prompt: str = Field(..., min_length=5, max_length=4000)
    script: str | None = Field(None, max_length=20000)
    reference_url: str | None = Field(None, max_length=1000)
    settings: VideoSettings = VideoSettings()
    auto_start: bool = True

    @field_validator("cast")
    @classmethod
    def _cast(cls, v):
        out = []
        for a in v:
            a = " ".join(str(a).split())[:60]
            if len(a) >= 2 and a.lower() not in [x.lower() for x in out]:
                out.append(a)
        return out

    @field_validator("reference_url")
    @classmethod
    def _url(cls, v):
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("reference_url must start with http:// or https://")
        return v or None


class ProjectUpdate(BaseModel):
    title: str | None = Field(None, max_length=200)
    prompt: str | None = Field(None, max_length=4000)
    script: str | None = Field(None, max_length=20000)
    settings: VideoSettings | None = None


class SceneUpdate(BaseModel):
    duration_s: float | None = Field(None, ge=1, le=30)
    description: str | None = None
    image_prompt: str | None = None
    video_prompt: str | None = None
    camera_movement: str | None = None
    camera_angle: str | None = None
    lighting: str | None = None
    narration: str | None = None
    sfx: list[str] | None = None
    transition: str | None = None


class RegenerateRequest(BaseModel):
    parts: list[Literal["image", "video", "voice", "sfx"]] = ["image", "video"]


class CharacterUpdate(BaseModel):
    name: str | None = None
    body_shape: str | None = None
    color: str | None = None
    face: str | None = None
    eye_color: str | None = None
    markings: str | None = None
    accessories: str | None = None
    personality: str | None = None
    voice: str | None = None
