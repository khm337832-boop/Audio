"""အဆင့် ၂–၈ pipeline စမ်းသပ်မှုများ (network/ffmpeg မလို — fake အဆင့်များ ထည့်ထားတယ်)။"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from models.story import Chapter, Story  # noqa: E402
from services import scene_service, story_generator  # noqa: E402


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(config, "FORCE_MOCK", True)
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    yield


# ------------------------------------------------------------------ story length
def _fake_llm(chapter_len: int = 1150, titles: int = 19, chars_per_repeat: int = 12):
    counter = {"n": 0}
    body = "ဒါက စမ်းသပ် ဇာတ်လမ်းရဲ့ စာသားပါ။ "  # ၁၇ စာလုံးခန့်

    def json_fn(prompt, **kwargs):
        return {
            "title": "စမ်းသပ် ဇာတ်လမ်း",
            "genre": "စွန့်စားခန်း",
            "logline": "စမ်းသပ်ရေး",
            "summary": "အနှစ်ချုပ် " * 40,
            "themes": ["မိသားစု"],
            "characters": ["ကိုကို", "မမ"],
            "keywords": ["မြန်မာဇာတ်လမ်း"],
            "chapter_titles": [f"အခန်း {i + 1} — စမ်းသပ်" for i in range(titles)],
        }

    def text_fn(prompt, **kwargs):
        counter["n"] += 1
        repeats = max(1, (chapter_len - 20) // chars_per_repeat)
        return f"အခန်း {counter['n']} အစ " + (body * repeats)

    return text_fn, json_fn


def test_story_reaches_20000_chars(monkeypatch):
    text_fn, json_fn = _fake_llm()
    story = story_generator.generate_full_story(
        use_llm=True, text_fn=text_fn, json_fn=json_fn
    )
    min_chars, max_chars = config.story_target()
    assert story.total_chars >= min_chars
    assert story.total_chars <= max_chars * 1.05
    assert story.length_ok is True
    assert 6 <= len(story.chapters) <= config.STORY_MAX_CHAPTERS
    assert story.target_chars >= min_chars


def test_story_progress_callback():
    messages: list[str] = []
    text_fn, json_fn = _fake_llm()
    story_generator.generate_full_story(
        use_llm=True, text_fn=text_fn, json_fn=json_fn, progress=messages.append
    )
    assert any("စာလုံး" in m for m in messages)


def test_story_falls_back_to_demo_without_llm():
    story = story_generator.generate_full_story(use_llm=False)
    assert story.chapters
    assert story.length_ok is False
    assert story.generation_notes


def test_story_json_keeps_length_fields(tmp_path):
    text_fn, json_fn = _fake_llm(titles=4, chapter_len=1100)
    story = story_generator.generate_full_story(use_llm=True, text_fn=text_fn, json_fn=json_fn,
                                                min_chars=1000, max_chars=6000, target_chars=4000)
    story_generator.save_story(story, tmp_path)
    loaded = Story.load(tmp_path / "story.json")
    assert loaded.target_chars == story.target_chars
    assert loaded.length_ok == story.length_ok


# ------------------------------------------------------------------ scenes
def test_scene_plan_covers_every_chapter():
    story = Story(
        story_id="s", title="t", genre="စွန့်စားခန်း", language="my", full_text="",
        chapters=[
            Chapter(index=i, title=f"အခန်း {i + 1}", text="ဖြစ်ရပ် တစ်ခု ဖြစ်ပွားတယ်။ " * 5)
            for i in range(4)
        ],
    )
    scenes = scene_service.build_scene_plan(story, per_chapter=2)
    assert len(scenes) == 8
    assert {s.chapter_index for s in scenes} == {0, 1, 2, 3}
    assert all("no text" in s.prompt for s in scenes)


def test_render_scene_images_writes_files(tmp_path):
    story = Story(
        story_id="s", title="t", genre="g", language="my", full_text="",
        chapters=[Chapter(index=0, title="အခန်း ၁", text="ဖြစ်ရပ်။ " * 10)],
    )
    scenes = scene_service.build_scene_plan(story, per_chapter=1)

    calls = []

    def fake_gen(prompt, path, **kwargs):
        calls.append(prompt)
        Path(path).write_bytes(b"\xff\xd8\xff\xd9")
        return Path(path)

    rendered = scene_service.render_scene_images(
        scenes, tmp_path, concurrency=2, image_generator=fake_gen
    )
    assert calls and rendered[0].image
    assert Path(rendered[0].image).exists()
    assert (tmp_path / scene_service.SCENES_FILE).exists() is False  # save ကို သီးသန့် ခေါ်တယ်
    scene_service.save_scene_plan(rendered, tmp_path)
    assert (tmp_path / scene_service.SCENES_FILE).exists()


# ------------------------------------------------------------------ pipeline
def _build_story() -> Story:
    text_fn, json_fn = _fake_llm(titles=6, chapter_len=900)
    return story_generator.generate_full_story(
        use_llm=True, text_fn=text_fn, json_fn=json_fn,
        min_chars=4000, max_chars=8000, target_chars=5000,
    )


def test_pipeline_end_to_end(tmp_path):
    from pipeline import PipelineOptions, StoryPipeline

    story = _build_story()
    job = tmp_path / "job"
    job.mkdir()

    def story_fn(*args, **kwargs):
        return story

    def tts_fn(story_obj, provider=None, progress=None, work_dir=None):
        audio = job / "audio.wav"
        audio.write_bytes(b"RIFF")
        info = []
        for chapter in story_obj.chapters:
            chapter.duration = 90.0
            info.append({"path": audio, "duration": 90.0, "title": chapter.title})
        return audio, info

    def render_fn(scenes, work_dir, progress=None, **kwargs):
        for scene in scenes:
            path = Path(work_dir) / "scenes" / f"scene_{scene.index:03d}.jpg"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"\xff\xd8\xff\xd9")
            scene.image = str(path)
        return scenes

    def video_fn(story_obj, scenes, audio_path, work_dir, progress=None):
        final = Path(work_dir) / "final.mp4"
        final.write_bytes(b"\x00" * 4096)
        return final

    pipeline = StoryPipeline(
        job,
        options=PipelineOptions(dry_run=True, scenes_per_chapter=1),
        story_fn=story_fn,
        tts_fn=tts_fn,
        render_fn=render_fn,
        video_fn=video_fn,
    )
    result = pipeline.run()

    assert result.video_path and Path(result.video_path).exists()
    assert result.publish is not None
    assert result.publish.upload is not None
    assert result.publish.upload.dry_run is True
    assert result.publish.thumbnail and Path(result.publish.thumbnail).exists()
    assert len(result.scene_images) == len(story.chapters)

    names = [s.name for s in result.stages]
    assert len(result.stages) == 5
    assert all(s.ok for s in result.stages)
    assert any("YouTube" in n for n in names)

    report = json.loads((job / "pipeline_result.json").read_text("utf-8"))
    assert report["title"] == story.title
    assert report["scenes"] == len(story.chapters)
    assert report["youtube"]["dry_run"] is True
    assert (job / "story.json").exists()
    assert (job / "thumbnail.jpg").exists()


def test_pipeline_no_upload(tmp_path):
    from pipeline import PipelineOptions, StoryPipeline

    story = _build_story()
    job = tmp_path / "job2"
    job.mkdir()

    def video_fn(story_obj, scenes, audio_path, work_dir, progress=None):
        final = Path(work_dir) / "final.mp4"
        final.write_bytes(b"\x00" * 1024)
        return final

    pipeline = StoryPipeline(
        job,
        options=PipelineOptions(upload=False, scenes_per_chapter=1),
        story_fn=lambda *a, **k: story,
        tts_fn=lambda s, **k: (job / "a.wav", []),
        render_fn=lambda scenes, work_dir, **k: [],
        video_fn=video_fn,
    )
    (job / "a.wav").write_bytes(b"RIFF")
    result = pipeline.run()
    assert result.publish is None
    assert result.video_path
    assert [s.name for s in result.stages][-1].startswith("④")


def test_pipeline_stage_failure_is_reported(tmp_path):
    from pipeline import PipelineError, PipelineOptions, StoryPipeline

    def broken_tts(story_obj, **kwargs):
        raise RuntimeError("TTS မရပါ")

    pipeline = StoryPipeline(
        tmp_path / "job3",
        options=PipelineOptions(upload=False),
        story_fn=lambda *a, **k: _build_story(),
        tts_fn=broken_tts,
    )
    with pytest.raises(PipelineError) as excinfo:
        pipeline.run()
    assert "အသံထွက်" in str(excinfo.value)
    stages = pipeline.result.stages
    assert stages and stages[-1].ok is False


# ------------------------------------------------------------------ tts helpers
def test_tts_provider_selection(monkeypatch):
    from services import tts_service

    monkeypatch.setattr(config, "TTS_PROVIDER", "auto")
    monkeypatch.setattr(config, "TTS_COMMAND", "echo {output}")
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")
    assert tts_service.resolve_provider("my") == "local"

    monkeypatch.setattr(config, "TTS_COMMAND", "")
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "key")
    assert tts_service.resolve_provider("en") == "elevenlabs"
    assert tts_service.resolve_provider("my") == "elevenlabs"

    monkeypatch.setattr(config, "TTS_PROVIDER", "local")
    assert tts_service.resolve_provider("en") == "local"


def test_tts_split_text_respects_limit():
    from services import tts_service

    text = "မြန်မာစာကြောင်း တစ်ခု ဖြစ်ပါတယ်။ " * 300
    parts = tts_service.split_text(text, 500)
    assert parts and all(len(p) <= 500 for p in parts)
    assert sum(len(p) for p in parts) < len(text)  # ကွက်လပ် အနည်းငယ် လျော့တယ်


def test_bot_module_imports():
    import bot  # noqa: F401

    assert hasattr(bot, "main")
    assert hasattr(bot, "run_full_pipeline")


def test_custom_target_chars_stops_at_target():
    """`target_chars` ပေးရင် အဲဒီပမာဏ ပြည့်တာနဲ့ ရပ်ရမယ် (အခန်း ထပ်မရေးရ)။"""
    text_fn, json_fn = _fake_llm(titles=10, chapter_len=1000)
    story = story_generator.generate_full_story(
        use_llm=True, text_fn=text_fn, json_fn=json_fn, target_chars=4000
    )
    assert story.target_chars == 4000
    assert story.total_chars >= 4000
    assert len(story.chapters) <= 4  # ၁၀ ခန်း မရေးဘဲ ပစ်မှတ်မှာ ရပ်တယ်
