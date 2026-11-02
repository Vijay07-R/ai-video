import json

import pytest

from app import config, languages
from app.providers.base import ProviderError
from app.providers.manager import AllProvidersExhausted, ProviderManager
from app.providers.voice import EspeakVoice, KokoroVoice, PiperVoice
from app.services import preflight
from app.services.pipeline import segment_cues
from app.services.render import write_ass
from app.services.story import build_prompt, normalize_story

from . import fixtures_lion


@pytest.mark.parametrize("lang", ["en", "ta", "te", "hi"])
def test_native_story_passes_validation(lang):
    s = normalize_story(fixtures_lion.story(lang), 60, "lion cub", lang)
    assert s["language"] == lang and len(s["scenes"]) == 12
    assert s["characters"][0]["name"] == "Veeran" and s["characters"][0]["name_native"] == fixtures_lion.NAMES[lang][0]
    # the finished film (after 11 crossfades of 0.5 s) is exactly 60 s
    assert abs(sum(x["duration_s"] for x in s["scenes"]) - 60 - 0.5 * 11) < 0.1


def test_wrong_language_is_rejected():
    with pytest.raises(ProviderError, match="not in Tamil"):
        normalize_story(fixtures_lion.story("en"), 60, "lion", "ta")  # English text but Tamil requested
    with pytest.raises(ProviderError, match="not in Telugu"):
        normalize_story(fixtures_lion.story("ta"), 60, "lion", "te")


def test_subtitle_translation_fields_kept_and_checked():
    s = normalize_story(fixtures_lion.story("ta", "en"), 60, "lion", "ta", "en")
    assert s["scenes"][0]["narration_subtitle"].startswith("The morning sun")
    assert s["scenes"][3]["dialogue"][0]["subtitle"] == "Who are you?"
    bad = fixtures_lion.story("ta", "ta")  # "English" subtitles that are really Tamil
    with pytest.raises(ProviderError, match="subtitles are not in English"):
        normalize_story(bad, 60, "lion", "ta", "en")


def test_script_share():
    assert languages.script_share("வீரன் காட்டில்", "ta") == 1.0
    assert languages.script_share("Veeran in the forest", "ta") == 0.0
    assert languages.script_share("नमस्ते Veeran", "hi") > 0.4


def test_prompt_contains_language_guidance():
    system, prompt = build_prompt({"animal": "lion", "prompt": "friend", "settings": {"duration_s": 60, "language": "ta", "subtitle_language": "en"}})
    assert "Tamil" in system and "ORIGINALLY in Tamil" in system and "name_native" in system
    assert "narration_subtitle" in prompt


def test_voice_providers_declare_languages(tmp_path):
    s = config.get_settings()
    assert KokoroVoice(s).supports(language="hi") and not KokoroVoice(s).supports(language="ta")
    assert EspeakVoice(s).supports(language="te")
    model = tmp_path / "ta_IN-test.onnx"
    model.write_bytes(b"x")
    s.piper_voices = {"ta": str(model), "te": str(tmp_path / "missing.onnx")}
    pv = PiperVoice(s)
    assert pv.supports(language="ta") and not pv.supports(language="te")


class Dummy(EspeakVoice):
    name = "dummy-en"
    languages = {"en"}

    def check(self):
        return True, "ok"


def test_manager_never_switches_language():
    s = config.get_settings()
    s.voice_order = ["dummy-en"]
    m = ProviderManager([Dummy(s)], s)
    with pytest.raises(AllProvidersExhausted) as e:
        m.call("voice", lambda p: p.synthesize("வணக்கம்", None, None, "ta"), needs={"language": "ta"})
    assert "does not support" in str(e.value)


def test_preflight_blocks_missing_language_voice(test_manager):
    # test_manager's voice double has no language list -> supports everything; replace with an English-only voice
    s = config.get_settings()
    test_manager.providers.pop("fake-voice")
    test_manager.providers["dummy-en"] = Dummy(s)
    s.voice_order = ["dummy-en"]
    r = preflight.run({"language": "ta"})
    assert not r["ok"] and any("No free Tamil voice" in p for p in r["problems"])
    assert preflight.run({"language": "en"})["ok"]


def test_segment_cues_and_ass(tmp_path):
    cues = segment_cues("ஆனால் சின்னுவுக்குச் சிங்கம் என்றாலே பயம். அவன் இலைகளுக்குள் ஒளிந்துகொண்டான்.", 1.0, 4.0)
    assert len(cues) == 2 and cues[0][0] == 1.0 and abs(cues[-1][1] - 5.0) < 0.01
    path = write_ass(tmp_path / "s.ass", [(0.0, 2.0, "வணக்கம் {x}")], 720, 1280, "Noto Sans Tamil")
    text = path.read_text(encoding="utf-8")
    assert "PlayResX: 720" in text and "Noto Sans Tamil" in text and "வணக்கம் (x)" in text


def test_bundled_fonts_exist():
    for code in ("ta", "te", "hi", "en"):
        font, d = languages.subtitle_font(code)
        assert (d / f"{font.replace(' ', '')}-Regular.ttf").exists(), font


def test_language_report_lists_all(test_manager):
    rep = {r["code"]: r for r in preflight.language_report()}
    assert set(rep) == {"en", "ta", "te", "hi"} and rep["ta"]["native"] == "தமிழ்"
    json.dumps(rep, ensure_ascii=False)


def test_cast_every_animal_needs_a_character():
    from app.services.story import missing_cast
    chars = [{"species": "lion", "name": "Raja"}, {"species": "little rabbit", "name": "Chotu"}]
    assert missing_cast(["Lion", "Rabbit"], chars) == []
    assert missing_cast(["Lion", "Rabbit", "Peacock"], chars) == ["Peacock"]
    story = fixtures_lion.story("en")  # cub (lion) + monkey
    normalize_story(story, 60, "Lion cub", "en", None, ["Lion cub", "Monkey"])
    with pytest.raises(ProviderError, match="missing a character for: Dog"):
        normalize_story(story, 60, "Lion cub", "en", None, ["Lion cub", "Monkey", "Dog"])


def test_cast_reaches_the_prompt():
    _, prompt = build_prompt({"animal": "Lion, Rabbit", "prompt": "net", "settings": {"cast": ["Lion", "Rabbit", "German Shepherd"]}})
    assert "EACH of these animals" in prompt and "German Shepherd" in prompt
