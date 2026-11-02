"""Real FFmpeg / audio synthesis tests (no mocks)."""
from app import ffmpeg
from app.providers.base import ClipRequest
from app.providers.motion import MotionComicVideo, camera_expr
from app.providers.procedural import ProceduralMusic, ProceduralSfx, detect_mood
from app.services import consistency, reference
from app.services.render import RenderSpec, SceneMedia, output_size, render, scene_starts, total_duration


def test_output_sizes():
    assert output_size("16:9", "1080p") == (1920, 1080)
    assert output_size("9:16", "720p") == (720, 1280)
    assert output_size("1:1", "4k") == (2160, 2160)


def test_timeline_math():
    d, t = [4, 4, 4], ["fade", "fade", "cut"]
    assert scene_starts(d, t, 0.5) == [0.0, 3.5, 7.46]
    assert total_duration(d, t, 0.5) == 11.46


def test_camera_expressions_differ():
    assert camera_expr("pull out", 100) != camera_expr("slow push in", 100) != camera_expr("pan left", 100)


def test_mood_detection():
    assert detect_mood("a lonely lost cub, sad strings") == "sad"
    assert detect_mood("joyful reunion") == "happy"


def test_procedural_music_and_sfx(tmp_path):
    m = ProceduralMusic().compose("hopeful reunion strings", 6, tmp_path / "m.wav", seed=1)
    s = ProceduralSfx().create(["birds", "wind", "lion roar"], 4, tmp_path / "s.wav", seed=2)
    assert abs(ffmpeg.duration(m) - 6) < 0.05 and abs(ffmpeg.duration(s) - 4) < 0.05


def test_motion_comic_clip(tiny_png, tmp_path):
    out = MotionComicVideo().generate(ClipRequest(image=tiny_png, prompt="", duration_s=2, width=640, height=360, camera="pan left"), tmp_path / "c.mp4")
    info = ffmpeg.probe(out)
    v = info["streams"][0]
    assert (v["width"], v["height"]) == (640, 360) and abs(float(info["format"]["duration"]) - 2) < 0.1


def test_full_render_with_transitions_audio_subtitles(tiny_png, tmp_path):
    mc = MotionComicVideo()
    clips = [mc.generate(ClipRequest(image=tiny_png, prompt="", duration_s=2.5, width=640, height=360, camera=c), tmp_path / f"c{i}.mp4")
             for i, c in enumerate(["push in", "pull out", "pan right"])]
    music = ProceduralMusic().compose("calm", 8, tmp_path / "music.wav")
    voice = ProceduralSfx().create(["roar"], 1.5, tmp_path / "v.wav")  # any audio works as a voice track here
    sfx = ProceduralSfx().create(["birds"], 2.5, tmp_path / "s.wav")
    scenes = [SceneMedia(clip=c, duration=3.0, transition=t, voice=voice if i != 1 else None, sfx=sfx, subtitle=f"Line {i}")
              for i, (c, t) in enumerate(zip(clips, ["fade", "dissolve", "cut"]))]
    res = render(RenderSpec(scenes=scenes, out=tmp_path / "final.mp4", width=640, height=360, music=music, subtitles=True, preset="ultrafast"))
    assert res["ok"], res["problems"]
    assert res["audio_codec"] == "aac" and res["video_codec"] == "h264"


def test_reference_analysis_on_generated_video(tiny_png, tmp_path):
    clip = MotionComicVideo().generate(ClipRequest(image=tiny_png, prompt="", duration_s=2, width=320, height=180), tmp_path / "r.mp4")
    a = reference.analyze(clip)
    assert a["type"] == "video" and a["duration_s"] > 1.5 and a["palette"]
    notes = reference.to_style_notes(a)
    assert "lighting" in notes and "single continuous shot" in notes


def test_consistency_similar_vs_different(tmp_path):
    from PIL import Image
    a, b, c = tmp_path / "a.png", tmp_path / "b.png", tmp_path / "c.png"
    Image.new("RGB", (200, 200), (210, 150, 60)).save(a)
    Image.new("RGB", (300, 200), (205, 148, 62)).save(b)
    Image.new("RGB", (300, 200), (40, 90, 200)).save(c)
    assert consistency.check(a, b)[1] is False
    assert consistency.check(a, c)[1] is True
