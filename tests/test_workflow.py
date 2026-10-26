import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config  # noqa: E402


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Test အားလုံး network မခေါ်ရအောင် offline mode မှာ ထားတယ်။"""
    monkeypatch.setattr(config, "FORCE_MOCK", True)
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    yield


@pytest.fixture
def job_dir(tmp_path: Path) -> Path:
    job = tmp_path / "job_test"
    job.mkdir()
    (job / "final.mp4").write_bytes(b"\x00" * 4096)
    return job


@pytest.fixture
def story():
    from services import story_generator

    story = story_generator.generate_full_story()
    # timestamp block စမ်းဖို့ duration ထည့်
    for i, chapter in enumerate(story.chapters):
        chapter.duration = 40.0 + i * 15
    return story


def write_story(story, job_dir: Path) -> None:
    from services import story_generator

    story_generator.save_story(story, job_dir)
    assert (job_dir / "story.json").exists()


def test_story_json_roundtrip(story, job_dir, tmp_path):
    from models.story import Story

    write_story(story, job_dir)
    loaded = Story.load(job_dir / "story.json")
    assert loaded.title == story.title
    assert len(loaded.chapters) == len(story.chapters)
    assert loaded.total_chars > 0
    assert loaded.total_duration == pytest.approx(story.total_duration)


def test_metadata_from_story_file(story, job_dir):
    from services import metadata_service

    write_story(story, job_dir)
    metadata = metadata_service.load_or_extract_metadata(job_dir)
    assert metadata.summary
    assert metadata.chapters and metadata.chapters[0]["title"]
    assert metadata.has_timestamps
    assert (job_dir / "story_metadata.json").exists()


def test_metadata_missing_story_raises(tmp_path):
    from services import metadata_service

    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FileNotFoundError):
        metadata_service.load_or_extract_metadata(empty)


def test_titles_within_youtube_limit(story, job_dir):
    from models.story import StoryMetadata
    from services import youtube_service

    metadata = StoryMetadata.from_story(story)
    titles = youtube_service.generate_youtube_title(metadata, count=3)
    assert len(titles) == 3
    assert all(0 < len(t) <= config.TITLE_MAX_CHARS for t in titles)
    assert youtube_service.pick_title(titles, metadata) in titles


def test_description_contains_chapters_and_hashtags(story, job_dir):
    from models.story import StoryMetadata
    from services import youtube_service

    metadata = StoryMetadata.from_story(story)
    description = youtube_service.generate_youtube_description(metadata, "စမ်းသပ် ခေါင်းစဉ်")
    assert "အခန်းများ" in description
    assert "00:00" in description
    assert "#" in description
    assert len(description) <= config.DESCRIPTION_SAFE_CHARS

    tags = youtube_service.generate_youtube_tags(metadata)
    assert tags and sum(len(t) + 1 for t in tags) <= 500


def test_description_truncates_long_summary(story, job_dir):
    from models.story import StoryMetadata
    from services import youtube_service

    metadata = StoryMetadata.from_story(story)
    metadata.summary = "ရှည်တဲ့ အနှစ်ချုပ်။ " * 1200
    description = youtube_service.generate_youtube_description(metadata, "title")
    assert len(description) <= config.DESCRIPTION_SAFE_CHARS


def test_thumbnail_prompt_and_overlay(story, tmp_path):
    from PIL import Image

    from models.story import StoryMetadata
    from services import image_service, thumbnail_service

    metadata = StoryMetadata.from_story(story)
    prompt = thumbnail_service.generate_thumbnail_prompt(metadata)
    assert "no text" in prompt.lower() or "text" in prompt.lower()

    base = image_service.generate_scene_image(prompt, tmp_path / "base.jpg", width=1280, height=720)
    out = thumbnail_service.compose_thumbnail(
        base, "မြစ်ကမ်းက မီးရောင် — ထိတ်လန့်ဖွယ် စွန့်စားခန်း အခန်းပြည့်", tmp_path / "thumb.jpg",
        subtitle="ညတိုင်း ပေါ်လာတဲ့ မီးရောင်", badge="ဇာတ်လမ်း",
    )
    assert out.exists() and out.stat().st_size <= config.THUMBNAIL_MAX_BYTES
    with Image.open(out) as img:
        assert img.size == config.THUMBNAIL_SIZE
        assert img.format == "JPEG"


def test_thumbnail_long_title_fits(story, tmp_path):
    from PIL import Image

    from services import image_service, thumbnail_service

    base = image_service.generate_scene_image("x", tmp_path / "b.jpg", width=1280, height=720)
    out = thumbnail_service.compose_thumbnail(
        base, "အလွန်ရှည်သော ခေါင်းစဉ်တစ်ခု " * 8, tmp_path / "t.jpg"
    )
    with Image.open(out) as img:
        assert img.size == (1280, 720)


def test_workflow_end_to_end_dry_run(story, job_dir):
    from PIL import Image

    from workflow import PublishOptions, PublishWorkflow

    write_story(story, job_dir)
    workflow = PublishWorkflow(job_dir, options=PublishOptions(dry_run=True))
    artifacts = workflow.run()

    assert artifacts.title
    assert artifacts.title_candidates
    assert artifacts.description
    assert artifacts.thumbnail and artifacts.thumbnail.exists()
    with Image.open(artifacts.thumbnail) as img:
        assert img.size == (1280, 720)

    assert artifacts.upload is not None
    assert artifacts.upload.dry_run is True
    assert artifacts.upload.video_id.startswith("dryrun-")

    stages = {s.name: s.ok for s in artifacts.stages}
    assert all(stages.values())
    assert any("YouTube" in name for name in stages)

    report = json.loads((job_dir / "publish_result.json").read_text("utf-8"))
    assert report["title"] == artifacts.title

    payload = json.loads((job_dir / "youtube_payload.json").read_text("utf-8"))
    assert payload["title"] == artifacts.title
    assert payload["upload"]["dry_run"] is True


def test_workflow_custom_title_and_no_upload(story, job_dir):
    from workflow import PublishOptions, PublishWorkflow

    write_story(story, job_dir)
    artifacts = PublishWorkflow(
        job_dir,
        options=PublishOptions(title="ငါ့ ခေါင်းစဉ်", upload=False, make_thumbnail=False),
    ).run()
    assert artifacts.title == "ငါ့ ခေါင်းစဉ်"
    assert artifacts.thumbnail is None
    assert artifacts.upload is None


def test_workflow_rejects_long_title(story, job_dir):
    from workflow import PublishOptions, PublishWorkflow, StageError

    write_story(story, job_dir)
    with pytest.raises(StageError):
        PublishWorkflow(
            job_dir, options=PublishOptions(title="x" * 150, upload=False)
        ).run()


def test_upload_validates_missing_video(tmp_path):
    from services import youtube_service

    with pytest.raises(youtube_service.YouTubeError):
        youtube_service.upload_video(tmp_path / "nope.mp4", "t", "d", dry_run=True)


def test_timestamp_lines_spacing():
    from utils.textkit import timestamp_lines

    chapters = [
        {"title": "က", "duration": 5},
        {"title": "ခ", "duration": 30},
        {"title": "ဂ", "duration": 10},
    ]
    lines = timestamp_lines(chapters)
    assert lines[0].startswith("00:00")
    assert len(lines) == 2  # 5s အကွာအဝေးက YouTube က လက်မခံ
    assert lines[1].startswith("00:35")


def test_wrap_for_font_handles_unspaced_text():
    from PIL import Image, ImageDraw, ImageFont

    from utils.textkit import wrap_for_font

    img = Image.new("RGB", (400, 200))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=20)
    lines = wrap_for_font(draw, "မြန်မာစာသားရှည်ရှည်တစ်ကြောင်း", font, 120)
    assert lines and all(isinstance(line, str) for line in lines)


def test_text_shaping_backend_renders_myanmar():
    """မြန်မာစာသားကို shaping နဲ့ ရေးတဲ့အခါ glyph အရွယ်အစား သင့်တင့်ရမယ် (basic layout က လေပ်တယ်)။"""
    from PIL import Image

    from utils.textrender import ShapedPainter, make_painter, shaping_available

    text = "မြစ်ကမ်းက မီးရောင်"
    painter = make_painter("assets/fonts/Padauk-Bold.ttf", 64, text)
    if shaping_available():
        assert painter.name in {"shaped", "raqm"}
        mask, _, _ = ShapedPainter("assets/fonts/Padauk-Bold.ttf", 64)._line_mask(text)
        # စာလုံး ၁၇ လုံးအတွက် mask က အနည်းဆုံး 300px ကျယ်ရမယ်
        assert mask.size[0] > 300
        assert mask.size[1] < 140
    else:
        assert painter.name in {"basic", "raqm"}

    img = Image.new("RGB", (900, 160), (0, 0, 0))
    painter.draw(img, 10, 30, text)
    assert img.getbbox() is not None


def test_shaped_painter_lines_do_not_overlap():
    from utils.textrender import make_painter, wrap_text

    painter = make_painter("assets/fonts/Padauk-Bold.ttf", 48, "က" * 20)
    lines = wrap_text("မြန်မာစာသား ရှည်ရှည် တစ်ကြောင်း " * 4, painter.measure, 400)
    assert len(lines) > 1
    assert all(painter.measure(line) <= 400 for line in lines)


def test_publish_after_video_async(story, job_dir):
    import asyncio

    from workflow import publish_after_video

    write_story(story, job_dir)
    artifacts = asyncio.run(
        publish_after_video(job_dir, upload=False, make_thumbnail=False)
    )
    assert artifacts.title
    assert (job_dir / "publish_result.json").exists()


def test_resolve_final_video_picks_newest(tmp_path):
    from workflow import resolve_final_video

    (tmp_path / "clip_0.mp4").write_bytes(b"x")
    (tmp_path / "video_noaudio.mp4").write_bytes(b"x")
    target = tmp_path / "other.mp4"
    target.write_bytes(b"x")
    assert resolve_final_video(tmp_path).name == "other.mp4"
