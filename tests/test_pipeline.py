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
    # TTS_COMMAND ရှိရင် မြန်မာအတွက် local ကို ဦးစားပေးတယ်
    assert tts_service.resolve_provider("my") == "local"

    # local မရှိတော့ရင် key မလိုတဲ့ provider (edge/gtts) ကို ရွေးရမယ်
    monkeypatch.setattr(config, "TTS_COMMAND", "")
    monkeypatch.setattr(tts_service, "local_available", lambda: False)
    assert tts_service.resolve_provider("my") in {"edge", "gtts"}

    # အင်္ဂလိပ်စာအတွက် ElevenLabs key ရှိရင် အဲဒါကို ဦးစားပေးတယ်
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "key")
    assert tts_service.resolve_provider("en") == "elevenlabs"

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


# ------------------------------------------------------------------ providers (key မလို)
def test_edge_and_gtts_registered(monkeypatch):
    from services import tts_service

    monkeypatch.setattr(config, "TTS_COMMAND", "")
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")
    providers = tts_service.available_providers()
    assert "edge" in providers or "gtts" in providers
    # မြန်မာစာအတွက် ElevenLabs မလိုဘဲ provider တစ်ခု ရွေးနိုင်ရမယ်
    assert tts_service.resolve_provider("my") in {"edge", "gtts", "local"}
    assert tts_service.resolve_provider("en") in {"edge", "gtts", "elevenlabs", "local"}


def test_explicit_provider_choice_wins(monkeypatch):
    from services import tts_service

    monkeypatch.setattr(config, "TTS_PROVIDER", "gtts")
    assert tts_service.resolve_provider("my") == "gtts"
    monkeypatch.setattr(config, "TTS_PROVIDER", "edge")
    assert tts_service.resolve_provider("en") == "edge"


def test_edge_writes_mp3_and_is_default_for_myanmar(monkeypatch, tmp_path):
    """edge provider ကို mock လုပ်ပြီး ဖိုင်ထွက်/ပေါင်းခြင်း အလုပ်လုပ်တာ စစ်တယ်။"""
    from services import tts_service

    monkeypatch.setattr(config, "TTS_PROVIDER", "edge")
    calls = []

    def fake_chunk(text, output_path, voice):
        calls.append((text[:20], voice))
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"ID3\x04\x00\x00")
        return Path(output_path)

    monkeypatch.setattr(tts_service, "_edge_chunk", fake_chunk)
    # ffmpeg concat ကို ချော်ရန် part တစ်ခုတည်း ဖြစ်အောင် စာသားတို ပေး
    out = tts_service.synthesize("မြစ်ကမ်းက မီးရောင်", tmp_path / "a.mp3", language="my")
    assert out.exists() and calls
    assert calls[0][1] == "my-MM-NilarNeural"


def test_edge_voice_selection(monkeypatch):
    from services import tts_service

    monkeypatch.setattr(config, "EDGE_TTS_VOICE", "")
    assert tts_service._edge_voice("my") == "my-MM-NilarNeural"
    assert tts_service._edge_voice("en") == "en-US-AndrewNeural"
    monkeypatch.setattr(config, "EDGE_TTS_VOICE", "my-MM-ThihaNeural")
    assert tts_service._edge_voice("my") == "my-MM-ThihaNeural"


# ------------------------------------------------------------------ setup wizard
def test_env_write_preserves_other_keys(tmp_path):
    from setup_wizard import read_env, write_env

    env = tmp_path / ".env"
    env.write_text(
        "# comment\nBOT_TOKEN=old\nGEMINI_API_KEY=keepme\nTTS_PROVIDER=auto\n", "utf-8"
    )
    write_env({"BOT_TOKEN": "new-token"}, path=env)
    values = read_env(env)
    assert values["BOT_TOKEN"] == "new-token"
    assert values["GEMINI_API_KEY"] == "keepme"
    assert "# comment" in env.read_text("utf-8")


def test_env_write_appends_missing_keys(tmp_path):
    from setup_wizard import read_env, write_env

    env = tmp_path / ".env"
    env.write_text("BOT_TOKEN=x\n", "utf-8")
    write_env({"EDGE_TTS_VOICE": "my-MM-NilarNeural"}, path=env)
    assert read_env(env)["EDGE_TTS_VOICE"] == "my-MM-NilarNeural"


def test_mask_hides_secret():
    from setup_wizard import mask

    hidden = mask("123456789:AAF-abcdefghijklmnop")
    assert "abcdefghijklmnop" not in hidden
    assert hidden.startswith("123456")


def test_validate_bot_token_rejects_bad_format():
    from setup_wizard import validate_bot_token

    ok, detail = validate_bot_token("not-a-token")
    assert ok is False and detail


# ------------------------------------------------------------------ youtube auth helpers
def test_describe_auth_status_without_files(tmp_path, monkeypatch):
    from services import youtube_service

    monkeypatch.setattr(config, "YOUTUBE_CLIENT_SECRETS", tmp_path / "nope.json")
    monkeypatch.setattr(config, "YOUTUBE_TOKEN_FILE", tmp_path / "tok.json")
    pytest.importorskip("google.oauth2.credentials", reason="google-auth မထည့်ထားပါ")
    info = youtube_service.describe_auth_status()
    assert info["client_secret"] is False
    assert info["token_file"] is False


def test_upload_without_token_gives_actionable_error(tmp_path, monkeypatch):
    from services import youtube_service

    pytest.importorskip("googleapiclient", reason="google-api-python-client မထည့်ထားပါ")
    pytest.importorskip("google_auth_oauthlib", reason="google-auth-oauthlib မထည့်ထားပါ")

    monkeypatch.setattr(config, "YOUTUBE_CLIENT_SECRETS", tmp_path / "client_secret.json")
    monkeypatch.setattr(config, "YOUTUBE_TOKEN_FILE", tmp_path / "tok.json")
    monkeypatch.setattr(config, "YOUTUBE_INTERACTIVE", False)
    video = tmp_path / "final.mp4"
    video.write_bytes(b"\x00" * 1024)
    with pytest.raises(youtube_service.YouTubeAuthError) as excinfo:
        youtube_service.upload_video(video, "t", "d", dry_run=False)
    assert "main.py auth" in str(excinfo.value)


def test_generate_voice_falls_back_to_next_provider(monkeypatch, tmp_path):
    """edge မရရင် နောက် provider (gtts) ကို အလိုအလျောက် ပြောင်းသုံးရမယ်။"""
    from services import tts_service

    monkeypatch.setattr(config, "TTS_PROVIDER", "edge")
    monkeypatch.setattr(tts_service, "available_providers", lambda: ["edge", "gtts"])
    monkeypatch.setattr(tts_service, "probe_duration", lambda path: 12.0)

    calls: list[str] = []

    def fake_synth(text, output_path, *, language=None, provider=None):
        calls.append(provider)
        if provider == "edge":
            raise tts_service.TTSError("edge မရပါ (စမ်းသပ်)")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"ID3\x04\x00\x00")
        return Path(output_path)

    monkeypatch.setattr(tts_service, "synthesize", fake_synth)
    monkeypatch.setattr(tts_service, "_concat_audio", lambda paths, out: paths[0])

    story = Story(
        story_id="s", title="t", genre="g", language="my", full_text="",
        chapters=[Chapter(index=i, title=f"အခန်း {i + 1}", text="စာသား " * 30) for i in range(2)],
    )
    audio, info = tts_service.generate_voice(story, work_dir=tmp_path)
    assert calls[0] == "edge" and "gtts" in calls
    assert Path(audio).exists()
    assert info[0]["provider"] == "gtts"     # ပြောင်းသုံးတာ မှတ်ထားတယ်
    assert all(chapter.duration == 12.0 for chapter in story.chapters)


# ------------------------------------------------------------------ client_secret handling
def _write_client_secret(path: Path, kind: str, redirect_uris=None) -> Path:
    block = {
        "client_id": "abc.apps.googleusercontent.com",
        "client_secret": "GOCSPX-fake",
        "project_id": "demo",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    if redirect_uris is not None:
        block["redirect_uris"] = redirect_uris
    path.write_text(json.dumps({kind: block}), "utf-8")
    return path


def test_client_secret_info_installed(tmp_path):
    from services import youtube_service

    path = _write_client_secret(tmp_path / "cs.json", "installed", ["http://localhost"])
    info = youtube_service.client_secret_info(path)
    assert info["type"] == "installed"
    assert info["project_id"] == "demo"


def test_client_secret_info_web_uses_localhost_if_present(tmp_path):
    from services import youtube_service

    path = _write_client_secret(
        tmp_path / "cs.json", "web", ["https://example.com/oauth/cb", "http://localhost:9000/"]
    )
    info = youtube_service.client_secret_info(path)
    assert info["type"] == "web"
    assert youtube_service.pick_redirect_uri(info) == "http://localhost:9000/"


def test_web_client_without_localhost_falls_back_to_default_port(tmp_path, monkeypatch):
    from services import youtube_service

    monkeypatch.setattr(config, "YOUTUBE_OAUTH_PORT", 8085)
    path = _write_client_secret(tmp_path / "cs.json", "web", ["https://render.example.com/cb"])
    info = youtube_service.client_secret_info(path)
    assert youtube_service.pick_redirect_uri(info) == "http://localhost:8085/"


def test_broken_client_secret_reports_error(tmp_path):
    from services import youtube_service

    path = tmp_path / "cs.json"
    path.write_text("{not json", "utf-8")
    info = youtube_service.client_secret_info(path)
    assert info["exists"] is True and info["type"] is None
    assert "JSON" in str(info.get("error"))


# ------------------------------------------------------------------ token env (cloud)
def test_decode_token_payload_raw_and_base64():
    import base64

    from services import youtube_service as ys

    payload = {"token": "a", "refresh_token": "r", "client_id": "c",
               "client_secret": "s", "token_uri": "https://oauth2.googleapis.com/token"}
    raw = json.dumps(payload)
    assert ys.decode_token_payload(raw)["refresh_token"] == "r"
    b64 = base64.b64encode(raw.encode()).decode()
    assert ys.decode_token_payload(b64)["token"] == "a"


def test_export_token_env_roundtrip(tmp_path):
    from services import youtube_service as ys

    token = tmp_path / "tok.json"
    token.write_text(json.dumps({"token": "x", "refresh_token": "y"}))
    line = ys.export_token_env(token)
    assert line.startswith("YOUTUBE_TOKEN_JSON=")
    assert ys.decode_token_payload(line.split("=", 1)[1])["token"] == "x"


def test_export_token_env_rejects_missing_or_bad(tmp_path):
    from services import youtube_service as ys

    with pytest.raises(ys.YouTubeAuthError):
        ys.export_token_env(tmp_path / "nope.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(Exception):
        ys.export_token_env(bad)


def test_env_token_used_when_file_missing(monkeypatch, tmp_path):
    """token ဖိုင် မရှိရင် YOUTUBE_TOKEN_JSON (env) ကို သုံးရမယ်။"""
    import base64

    from services import youtube_service as ys

    payload = {
        "token": "fake", "refresh_token": "r", "client_id": "c", "client_secret": "s",
        "token_uri": "https://oauth2.googleapis.com/token", "scopes": list(ys.SCOPES),
        "expiry": "2030-01-01T00:00:00Z",
    }
    monkeypatch.setattr(config, "YOUTUBE_TOKEN_JSON",
                        base64.b64encode(json.dumps(payload).encode()).decode())
    monkeypatch.setattr(config, "YOUTUBE_TOKEN_FILE", tmp_path / "missing.json")
    monkeypatch.setattr(config, "YOUTUBE_CLIENT_SECRETS", tmp_path / "cs.json")
    pytest.importorskip("google.oauth2.credentials", reason="google-auth မထည့်ထားပါ")
    info = ys.describe_auth_status()
    assert info.get("token_env") is True
    assert info.get("token_source") == "env"


def test_auth_import_file_copies_and_validates(tmp_path, monkeypatch):
    """`main.py auth --import-file` — Google က ဒေါင်းလုပ်ပေးတဲ့ JSON ကို နေရာချပေးရမယ်။"""
    import main as cli

    src = tmp_path / "client_secret_1234.apps.json"
    _write_client_secret(src, "installed", ["http://localhost"])
    target = tmp_path / "client_secret.json"
    monkeypatch.setattr(config, "YOUTUBE_CLIENT_SECRETS", target)

    assert cli.main(["auth", "--import-file", str(src)]) == 0
    assert target.exists()
    assert '"installed"' in target.read_text("utf-8")


def test_auth_import_file_rejects_bad_json(tmp_path, monkeypatch):
    import main as cli

    bad = tmp_path / "bad.json"
    bad.write_text("{not json", "utf-8")
    monkeypatch.setattr(config, "YOUTUBE_CLIENT_SECRETS", tmp_path / "client_secret.json")
    assert cli.main(["auth", "--import-file", str(bad)]) == 1


def test_channel_command_without_token_is_friendly(tmp_path, monkeypatch):
    import main as cli

    monkeypatch.setattr(config, "YOUTUBE_CLIENT_SECRETS", tmp_path / "cs.json")
    monkeypatch.setattr(config, "YOUTUBE_TOKEN_FILE", tmp_path / "none.json")
    monkeypatch.setattr(config, "YOUTUBE_TOKEN_JSON", "")
    pytest.importorskip("google.oauth2.credentials", reason="google-auth မထည့်ထားပါ")
    assert cli.main(["channel"]) == 1


def test_paste_secret_from_stdin(tmp_path, monkeypatch, capsys):
    """`auth --paste-secret` — JSON paste လုပ်ပြီး client_secret.json ဖန်တီးရမယ်။"""
    import io

    import main as cli

    target = tmp_path / "client_secret.json"
    monkeypatch.setattr(config, "YOUTUBE_CLIENT_SECRETS", target)
    payload = json.dumps({
        "installed": {
            "client_id": "1.apps.googleusercontent.com", "project_id": "demo",
            "client_secret": "GOCSPX-x", "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token", "redirect_uris": ["http://localhost"],
        }
    })
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    assert cli.main(["auth", "--paste-secret"]) == 0
    assert target.exists()
    assert '"installed"' in target.read_text("utf-8")


def test_paste_secret_rejects_garbage(tmp_path, monkeypatch):
    import io

    import main as cli

    monkeypatch.setattr(config, "YOUTUBE_CLIENT_SECRETS", tmp_path / "cs.json")
    monkeypatch.setattr("sys.stdin", io.StringIO("hello world"))
    assert cli.main(["auth", "--paste-secret"]) == 1
    assert not (tmp_path / "cs.json").exists()
