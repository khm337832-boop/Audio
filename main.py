"""Command line —

    python main.py produce  --topic "ရှေးခေတ် ရွာ"          # အဆင့် ၁-၇ အားလုံး + YouTube တင်
    python main.py produce  --dry-run                       # YouTube API မခေါ်ဘဲ စမ်းသပ်
    python main.py publish  --job-dir temp/job_x            # ဗီဒီယိုပြီးသားကနေ တင်
    python main.py title    --job-dir temp/job_x            # ခေါင်းစဉ်များ ကြည့်
    python main.py metadata --job-dir temp/job_x            # အနှစ်ချုပ် ကြည့်
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import config

from pipeline import PipelineOptions, StoryPipeline
from services import metadata_service
from workflow import PublishOptions, PublishWorkflow, StageError

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cli")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="ဗီဒီယိုပေါင်းစည်းပြီး → metadata → title → description → thumbnail → YouTube",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    publish = sub.add_parser("publish", help="အဆင့်အားလုံး လုပ်ပြီး YouTube တင်မယ်")
    publish.add_argument("--job-dir", required=True, help="ဗီဒီယိုနဲ့ story.json ရှိတဲ့ folder")
    publish.add_argument("--video", help="ဗီဒီယိုဖိုင် (default: <job-dir>/final.mp4)")
    publish.add_argument("--title", help="ခေါင်းစဉ်ကို ကိုယ်တိုင် သတ်မှတ်မယ်")
    publish.add_argument("--privacy", choices=["private", "unlisted", "public"])
    publish.add_argument("--publish-at", help="ISO 8601 schedule (ဥပမာ 2026-11-01T09:00:00Z)")
    publish.add_argument("--dry-run", action="store_true", help="YouTube API မခေါ်ဘဲ စမ်းသပ်")
    publish.add_argument("--no-upload", action="store_true", help="payload ပဲ ပြင်ဆင်မယ်")
    publish.add_argument("--no-thumbnail", action="store_true", help="thumbnail မလုပ်ပါ")
    publish.add_argument("--title-count", type=int, default=3)

    produce = sub.add_parser("produce", help="ဇာတ်လမ်းရေးကနေ YouTube တင်တဲ့အထိ (အဆင့် ၁-၇)")
    produce.add_argument("--topic", help="ဇာတ်လမ်း အကြောင်းအရာ")
    produce.add_argument("--job-dir", help="ထွက်ရလဒ် သိမ်းမယ့် folder (default: temp/job_<time>)")
    produce.add_argument("--chars", type=int, help="ပစ်မှတ် စာလုံးရေ (default: .env က ၂၀,၀၀၀–၂၅,၀၀၀)")
    produce.add_argument("--min-chars", type=int)
    produce.add_argument("--max-chars", type=int)
    produce.add_argument("--scenes", type=int, help="အခန်းတစ်ခန်း ဇာတ်ကွက် ပုံ အရေအတွက်")
    produce.add_argument("--tts", choices=["auto", "local", "elevenlabs"], default=None)
    produce.add_argument("--privacy", choices=["private", "unlisted", "public"])
    produce.add_argument("--publish-at", help="ISO 8601 schedule")
    produce.add_argument("--dry-run", action="store_true", help="YouTube API မခေါ်ဘဲ စမ်းသပ်")
    produce.add_argument("--no-upload", action="store_true", help="ဗီဒီယို ထုတ်ပြီး မတင်ပါ")

    title = sub.add_parser("title", help="ခေါင်းစဉ် ကိုယ်စားလှယ်များ ပြမယ်")
    title.add_argument("--job-dir", required=True)
    title.add_argument("--count", type=int, default=3)

    auth = sub.add_parser("auth", help="YouTube OAuth တစ်ခါ ခွင့်ပြုချက်ယူပြီး token သိမ်းမယ်")
    auth.add_argument("--manual", action="store_true",
                      help="browser မဖွင့်နိုင်ရင် — link ကို copy လုပ်ပြီး code paste လုပ်တဲ့ နည်း")
    auth.add_argument("--port", type=int, help=f"localhost port (default {config.YOUTUBE_OAUTH_PORT})")
    auth.add_argument("--client-secret", help="client_secret.json ဖိုင်လမ်းကြောင်း")
    auth.add_argument("--import-file", metavar="PATH",
                      help="Google က ဒေါင်းလုပ်ပေးထားတဲ့ JSON ကို client_secret.json အဖြစ် ထည့်မယ်")
    auth.add_argument("--paste-secret", action="store_true",
                      help="JSON စာသားကို terminal မှာ paste လုပ်ပြီး client_secret.json ဖန်တီးမယ်")
    auth.add_argument("--redirect-uri",
                      help="redirect URI (Web client ဖြစ်ရင် — ဥပမာ http://localhost:8085/)")
    auth.add_argument("--status", action="store_true", help="လက်ရှိ token အခြေအနေ ကြည့်")
    auth.add_argument("--export-env", action="store_true",
                      help="cloud (Render/VPS) အတွက် YOUTUBE_TOKEN_JSON=… လိုင်း ထုတ်ပေးမယ်")

    sub.add_parser("setup", help="BOT_TOKEN / GEMINI_API_KEY ကို စစ်ပြီး .env ထဲ သိမ်းမယ်")
    sub.add_parser("doctor", help="အဆင်သင့်ဖြစ်မှု အကျဉ်းချုပ် (secrets မပါ — ကူးပို့နိုင်တယ်)")
    sub.add_parser("channel", help="ချိတ်ထားတဲ့ YouTube channel ကို စစ်ဆေးမယ်")

    bot_cmd = sub.add_parser("bot", help="Telegram bot ကို run (token/webhook စစ်ပြီး၊ ရပ်ရင် ပြန်စ)")
    bot_cmd.add_argument("--check", action="store_true",
                         help="Token + webhook ကို စစ်ပြီး ပြန်ထွက် (bot မ​runဘူး)")
    bot_cmd.add_argument("--no-restart", action="store_true",
                         help="Error ဖြစ်ရင် ပြန်မ​ကြိုးစားဘဲ ထွက်")
    bot_cmd.add_argument("--log-file", default=None,
                         help="log ဖိုင် (default: temp/bot.log)")

    serve_cmd = sub.add_parser(
        "serve", help="Render/web service အတွက် — bot + HTTP health server တွဲ run"
    )
    serve_cmd.add_argument("--port", type=int, default=None,
                           help="port (default: $PORT သို့ 8080)")

    sub.add_parser("models", help="Gemini မှာ ရနိုင်တဲ့ model စာရင်း (404 ဖြေရှင်းရန်)")

    meta = sub.add_parser("metadata", help="ဇာတ်လမ်းအနှစ်ချုပ်နဲ့ အခန်းအချက်အလက် ပြမယ်")
    meta.add_argument("--job-dir", required=True)

    return parser


def cmd_publish(args: argparse.Namespace) -> int:
    options = PublishOptions(
        title=args.title,
        privacy_status=args.privacy,
        publish_at=args.publish_at,
        dry_run=True if args.dry_run else None,
        upload=not args.no_upload,
        make_thumbnail=not args.no_thumbnail,
        title_candidates=args.title_count,
    )
    workflow = PublishWorkflow(args.job_dir, args.video, options=options)
    try:
        artifacts = workflow.run()
    except StageError as exc:
        logger.error("မအောင်မြင်ပါ: %s", exc)
        return 1

    print("\n".join(artifacts.stage_report))
    print("\n===== ခေါင်းစဉ် =====")
    for i, candidate in enumerate(artifacts.title_candidates, 1):
        marker = "★" if candidate == artifacts.title else " "
        print(f"{marker} {i}. {candidate}")
    print("\n===== ဖော်ပြချက် =====")
    print(artifacts.description)
    if artifacts.thumbnail:
        print(f"\n🖼️ thumbnail: {artifacts.thumbnail}")
    if artifacts.upload:
        if artifacts.upload.dry_run:
            print(f"\n🧪 DRY-RUN — video id: {artifacts.upload.video_id}")
        else:
            print(f"\n🎬 {artifacts.upload.url} ({artifacts.upload.privacy_status})")
    print(f"\n📁 report: {workflow.job_dir / 'publish_result.json'}")
    return 0


def cmd_produce(args: argparse.Namespace) -> int:
    def progress(message: str) -> None:
        print(f"  {message}", flush=True)

    options = PipelineOptions(
        topic=args.topic,
        target_chars=args.chars,
        min_chars=args.min_chars,
        max_chars=args.max_chars,
        scenes_per_chapter=args.scenes,
        tts_provider=args.tts,
        privacy_status=args.privacy,
        publish_at=args.publish_at,
        dry_run=True if args.dry_run else None,
        upload=not args.no_upload,
    )
    pipeline = StoryPipeline(args.job_dir, options=options, progress=progress)
    try:
        result = pipeline.run()
    except Exception as exc:  # noqa: BLE001
        logger.error("မအောင်မြင်ပါ: %s", exc)
        if pipeline.result:
            print("\n".join(pipeline.result.stage_report()))
        return 1

    print("\n" + "\n".join(result.stage_report()))
    print(f"\n📖 {result.story.title} — {result.story_chars:,} စာလုံး, "
          f"{len(result.story.chapters)} အခန်း, {result.duration_seconds / 60:.1f} မိနစ်")
    if result.warnings:
        for warning in result.warnings:
            print(f"⚠️ {warning}")
    print(f"🎬 video: {result.video_path}")
    if result.publish:
        if result.publish.thumbnail:
            print(f"🖼️ thumbnail: {result.publish.thumbnail}")
        upload = result.publish.upload
        if upload and upload.dry_run:
            print(f"🧪 DRY-RUN — video id: {upload.video_id}")
        elif upload:
            print(f"🎉 {upload.url} ({upload.privacy_status})")
    print(f"📁 report: {result.job_dir / 'pipeline_result.json'}")
    return 0


def cmd_title(args: argparse.Namespace) -> int:
    from services import youtube_service

    metadata = metadata_service.load_or_extract_metadata(args.job_dir, persist=False)
    for i, candidate in enumerate(
        youtube_service.generate_youtube_title(metadata, count=args.count), 1
    ):
        print(f"{i}. {candidate}")
    recommended = youtube_service.pick_title(
        youtube_service.generate_youtube_title(metadata, count=args.count), metadata
    )
    print(f"\n★ အကြံပြုချက်: {recommended}")
    return 0


def _print_auth_help() -> None:
    print(
        """
📋 YouTube OAuth အတွက် ကြိုတင်ပြင်ဆင်ရန် (တစ်ခါသာ)
────────────────────────────────────────────
၁။ https://console.cloud.google.com → project အသစ် ဖန်တီး
၂။ APIs & Services → Library → “YouTube Data API v3” → Enable
၃။ OAuth consent screen → External → app name/email ဖြည့်
    → Test users မှာ သင့် Gmail ကို ထည့် (မဖြစ်မနေ)
၄။ Credentials → Create credentials → OAuth client ID
    → Application type: “Desktop app” → Create → Download JSON
၅။ ဒေါင်းလုပ်ထားတဲ့ ဖိုင်ကို client_secret.json နာမည်ပြောင်းပြီး
    ဒီ folder (repo root) ထဲ ထည့်ပါ
၆။ ပြီးရင် — python main.py auth
────────────────────────────────────────────
အဆင့်လိုက် ရုပ်ပုံလို လမ်းညွှန်: docs/YOUTUBE_AUTH_MM.md
""".strip()
    )


def cmd_setup(args: argparse.Namespace) -> int:
    from setup_wizard import run_wizard

    return run_wizard()


def _explain_youtube_error(message: str) -> None:
    """YouTube API အမှားကို နားလည်လွယ်တဲ့ ဖြေရှင်းနည်းအဖြစ် ပြောင်းပြီး ပြတယ်။"""
    from services import youtube_service as ys

    text = (message or "").lower()
    project = (ys.client_secret_info().get("project_id") or "").strip()
    url = f"https://console.cloud.google.com/apis/library/youtube.googleapis.com?project={project}"
    if "accessnotconfigured" in text or "has not been used in project" in text or "disabled" in text:
        print("\n👉 YouTube Data API v3 ကို project မှာ ဖွင့်မထားပါ")
        print(f"   {url}")
        print("   → “Enable” နှိပ်ပြီး ၂-၅ မိနစ် စောင့်ပါ၊ ပြီးရင် ဒီ command ကို ပြန် run")
    elif "quota" in text:
        print("\n👉 quota ကုန်သွားပါ (တစ်ရက် 10,000 units ≈ upload ၆ ခု) — မနက်ဖန် ပြန်စမ်းပါ")
    elif "insufficient" in text or "scope" in text:
        print("\n👉 ခွင့်ပြုချက် scope မလုံလောက်ပါ — youtube-oauth2.json ဖျက်ပြီး `python main.py auth` ပြန် run")
    elif "unauthorized" in text or "invalid_grant" in text or "401" in text:
        print("\n👉 token သက်တမ်းကုန်/ပျက်နေတယ် — `python main.py auth` ကို ပြန် run")


def cmd_channel(args: argparse.Namespace) -> int:
    """token က ဘယ် channel ကို ချိတ်ထားလဲ + တင်ခွင့် ရှိမရှိ စစ်တယ်။"""
    from services import youtube_service as ys

    try:
        youtube = ys.get_authenticated_service(interactive=False)
        response = youtube.channels().list(
            part="snippet,statistics,contentDetails", mine=True
        ).execute()
    except ys.YouTubeError as exc:
        print(f"❌ {exc}")
        if "token" in str(exc).lower():
            print("\n👉 ဖြေရှင်းနည်း: python main.py auth")
        else:
            _explain_youtube_error(str(exc))
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"❌ YouTube ကို မခေါ်နိုင်ပါ: {exc}")
        _explain_youtube_error(str(exc))
        return 1

    items = response.get("items", [])
    if not items:
        print("⚠️ token ရှိပေမယ့် YouTube channel မတွေ့ပါ")
        print("   ① youtube.com → သင့်ပုံ → “Create a channel”")
        print("   ② ပြီးရင် python main.py auth ကို ပြန် run (channel အသစ် ရွေး)")
        return 1

    channel = items[0]
    snippet = channel.get("snippet", {})
    stats = channel.get("statistics", {})
    handle = snippet.get("customUrl") or ""
    print("✅ Channel ချိတ်ဆက်ပြီး")
    print(f"   နာမည်: {snippet.get('title')}" + (f"  ({handle})" if handle else ""))
    print(f"   Channel ID: {channel.get('id')}")
    print(f"   Subscribers: {stats.get('subscriberCount', '?')} | "
          f"Videos: {stats.get('videoCount', '?')}")
    if snippet.get("country"):
        print(f"   နိုင်ငံ: {snippet.get('country')}")
    print(f"\n   တင်မယ့် privacy: {config.YOUTUBE_PRIVACY_STATUS} "
          f"({config.YOUTUBE_CATEGORY_ID} = {config.YOUTUBE_CATEGORY_ID and 'Entertainment'})")
    expected = os.getenv("YOUTUBE_CHANNEL_HANDLE", "").strip().lstrip("@").lower()
    if expected and handle.lstrip("@").lower() != expected:
        print(f"\n   ⚠️ မျှော်လင့်ထားတာ @{expected} ဖြစ်ပေမယ့် @{handle.lstrip('@')} ကို ချိတ်မိတယ်")
        print("      → youtube-oauth2.json ဖျက်ပြီး `python main.py auth` မှာ channel မှန်တာကို ရွေးပါ")
    print("\n   ဒီ channel မှန်ရင် — python main.py publish --job-dir temp/verify --privacy private")
    print("   channel မှားနေရင် — youtube-oauth2.json ဖျက်ပြီး python main.py auth ကို ပြန် run")
    if len(items) > 1:
        print(f"\n   ℹ️ account မှာ channel {len(items)} ခု ရှိတယ် (ပထမတစ်ခုကို သုံးမယ်)")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from check_setup import compact_report

    print(compact_report())
    return 0


def cmd_auth(args: argparse.Namespace) -> int:
    """`python main.py auth` — Google ခွင့်ပြုချက် ယူပြီး token သိမ်းတယ်။"""
    from services import youtube_service as ys

    secret_path = Path(args.client_secret) if args.client_secret else Path(config.YOUTUBE_CLIENT_SECRETS)
    client = ys.client_secret_info(secret_path)

    if args.paste_secret:
        print("📋 JSON စာသားတစ်ခုလုံးကို ဒီမှာ paste လုပ်ပါ")
        print("   (Notepad/browser က ဖိုင်ထဲက စာသားအားလုံး — { နဲ့ စပြီး } နဲ့ ဆုံးတယ်)")
        print("   paste ပြီးရင် — Enter နှိပ်၊ ပြီးရင် Ctrl+D (Windows: Ctrl+Z ပြီး Enter)")
        try:
            raw = sys.stdin.read()
        except KeyboardInterrupt:
            print("\nပယ်ဖျက်လိုက်တယ်")
            return 1
        raw = (raw or "").strip()
        if not raw:
            print("❌ စာသား မရပါ — ဘာမှ မ​ထည့်ဘဲ ထွက်သွားတယ်")
            return 1
        try:
            data = json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            print(f"❌ JSON ဖတ်မရပါ: {exc}")
            print("   ဖိုင်တစ်ခုလုံးကို copy လုပ်ပါ (တစ်စိတ်တစ်ပိုင်း မဖြစ်ရ)")
            return 1
        if not any(k in data for k in ("installed", "web")):
            print("❌ ဒါ OAuth client JSON မဟုတ်ပါ (installed/web key မတွေ့)")
            return 1
        target = Path(args.client_secret) if args.client_secret else Path(config.YOUTUBE_CLIENT_SECRETS)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2), "utf-8")
        try:
            target.chmod(0o600)
        except Exception:  # Windows မှာ မရနိုင်
            pass
        info = ys.client_secret_info(target)
        print(f"\n✅ သိမ်းပြီး: {target}")
        print(f"   အမျိုးအစား: {info.get('type')} | project: {info.get('project_id')}")
        if info.get("type") == "web":
            print("   ⚠️ Web client — redirect ထည့်ဖို့ လိုနိုင် (python main.py auth --status)")
        print("\n👉 နောက်တစ်ဆင့်: python main.py auth")
        return 0

    if args.import_file:
        import shutil

        src = Path(args.import_file).expanduser()
        if not src.is_file():
            print(f"❌ ဖိုင် မတွေ့ပါ: {src}")
            return 1
        try:
            json.loads(src.read_text("utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"❌ JSON ဖတ်မရပါ: {exc}")
            return 1
        target = Path(args.client_secret) if args.client_secret else Path(config.YOUTUBE_CLIENT_SECRETS)
        shutil.copyfile(src, target)
        info = ys.client_secret_info(target)
        print(f"✅ ထည့်ပြီး: {target}")
        print(f"   အမျိုးအစား: {info.get('type')} | project: {info.get('project_id')}")
        if info.get("type") == "web":
            print("   ⚠️ Web client — redirect ထည့်ဖို့ လိုနိုင်တယ် (python main.py auth --status)")
        print("\n👉 နောက်တစ်ဆင့်: python main.py auth")
        return 0

    if args.export_env:
        try:
            print("\n👇 ဒီလိုင်းကို hosting (Render/Railway/VPS) ရဲ့ Environment Variables မှာ ထည့်ပါ:")
            print(ys.export_token_env())
            print("\n(ဒီတန်ဖိုးက သင့် channel ကို တင်ခွင့်ပေးထားတဲ့ token — လျှို့ဝှက်ပါ)")
        except Exception as exc:  # noqa: BLE001
            logger.error("ထုတ်မရပါ: %s", exc)
            return 1
        return 0

    if args.status:
        print(f"client_secret.json: {'✅ ရှိ' if client['exists'] else '❌ မရှိ'}  ({secret_path})")
        if client["exists"]:
            print(f"  အမျိုးအစား: {client.get('type')}  project: {client.get('project_id')}")
            if client.get("redirect_uris"):
                print(f"  redirect URIs: {', '.join(client['redirect_uris'])}")
            if client.get("error"):
                print(f"  ⚠️ {client['error']}")
            if client.get("type") == "web":
                chosen = ys.pick_redirect_uri(client, port=args.port)
                print(f"  ⚠️ Web client — ဒီ redirect ကို Google Console မှာ ထည့်ထားဖို့ လိုတယ်: {chosen}")
        try:
            info = ys.describe_auth_status()
        except Exception as exc:  # noqa: BLE001
            logger.error("စစ်မရပါ: %s", exc)
            return 1
        source = info.get("token_source")
        print(f"youtube-oauth2.json: {'✅ ရှိ' if info['token_file'] else '❌ မရှိ'}")
        print(f"YOUTUBE_TOKEN_JSON (env): {'✅ ရှိ' if info.get('token_env') else '— မရှိ'}")
        if source:
            print(f"  အသုံးပြုမယ့် token: {source} | သက်တမ်းကုန်: {info['expired']} | "
                  f"refresh token: {info['has_refresh']}")
        if not info["token_file"]:
            _print_auth_help()
        return 0

    client_secret = Path(args.client_secret) if args.client_secret else None
    if client_secret:
        config.YOUTUBE_CLIENT_SECRETS = client_secret
    if not secret_path.exists():
        print(f"❌ client_secret.json မတွေ့ပါ: {secret_path}")
        _print_auth_help()
        return 1

    if client.get("type") == "web":
        target = ys.pick_redirect_uri(client, port=args.port, redirect_uri=args.redirect_uri)
        print("⚠️ ဒီ client_secret.json က “Web application” အမျိုးအစား ဖြစ်တယ်")
        print(f"   (Desktop app က ပိုလွယ်တယ်)။ သုံးမယ့် redirect: {target}")
        print("   Google Cloud → Credentials → သင့် OAuth client → Authorized redirect URIs")
        print(f"   မှာ {target} ကို ထည့်ထားဖို့ လိုတယ် (မထည့်ရင် redirect_uri_mismatch ဖြစ်မယ်)")
        print("")
    elif client.get("error"):
        print(f"⚠️ {client['error']}")

    print("🔐 Google ခွင့်ပြုချက် ယူနေတယ်…")
    try:
        youtube = ys.get_authenticated_service(
            client_secret_file=secret_path,
            interactive="manual" if args.manual else True,
            force_manual=args.manual,
            port=args.port,
            redirect_uri=args.redirect_uri,
        )
        response = youtube.channels().list(part="snippet,statistics", mine=True).execute()
        items = response.get("items", [])
        if items:
            channel = items[0]["snippet"]["title"]
            subs = items[0].get("statistics", {}).get("subscriberCount", "?")
            print(f"✅ ချိတ်ဆက်ပြီး — channel: {channel} (subscribers: {subs})")
        else:
            print("⚠️ token သိမ်းပြီး ဒါပေမယ့် channel မတွေ့ပါ —")
            print("   YouTube channel တစ်ခု ဖန်တီးထားဖို့ လိုတယ် (youtube.com → Create channel)")
        print(f"🔑 token: {config.YOUTUBE_TOKEN_FILE}")
        print("\n👉 စမ်းသပ်ရန်: python main.py publish --job-dir temp/real_test --privacy private")
        print("☁️ cloud မှာ run မယ်ဆိုရင်: python main.py auth --export-env")
        print("   (quota: တစ်ရက် 10,000 units — upload တစ်ခု ~1,600 units ≈ ၆ ခု/ရက်)")
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.error("OAuth မအောင်မြင်ပါ: %s", exc)
        return 1


def cmd_bot(args: argparse.Namespace) -> int:
    """`python main.py bot` — preflight စစ်ပြီး bot ကို run (ရပ်ရင် ပြန်စ)။"""
    import bot as bot_module

    return bot_module.run_bot(
        restart=not args.no_restart,
        check_only=args.check,
        log_file=Path(args.log_file) if args.log_file else None,
    )


def cmd_serve(args: argparse.Namespace) -> int:
    """`python main.py serve` — Render web service အတွက် (port bind + bot)။"""
    import serve

    return serve.run(args.port)


def cmd_models(args: argparse.Namespace) -> int:
    """`python main.py models` — key နဲ့ ရနိုင်တဲ့ Gemini model စာရင်း ပြတယ်။"""
    if not config.GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY မရှိပါ — .env မှာ ထည့်ပါ (သို့) python main.py setup")
        return 1
    print(f"🔎 သတ်မှတ်ထားတဲ့ model: {config.GEMINI_MODEL}")
    print(f"   fallback: {', '.join(config.gemini_model_candidates()[1:])}")
    print(f"   ပုံ model: {', '.join(config.gemini_image_candidates())}")
    try:
        from google import genai

        client = genai.Client(api_key=config.GEMINI_API_KEY)
        names = []
        for model in client.models.list():
            name = getattr(model, "name", "") or ""
            name = name.removeprefix("models/")
            if name:
                names.append(name)
    except Exception as exc:  # noqa: BLE001
        print(f"❌ model စာရင်း ယူမရပါ: {exc}")
        print("   → အင်တာနက်/key စစ်ပါ၊ (သို့) GEMINI_MODEL ကို ကိုယ်တိုင် ပြောင်းစမ်းပါ")
        return 1
    if not names:
        print("⚠️ model မတွေ့ပါ")
        return 1
    text_models = sorted(n for n in names if "image" not in n and "embed" not in n)
    image_models = sorted(n for n in names if "image" in n)
    print(f"\n✅ ရနိုင်တဲ့ text model {len(text_models)} ခု:")
    for name in text_models:
        mark = " ← သတ်မှတ်ထား" if name == config.GEMINI_MODEL else ""
        print(f"   - {name}{mark}")
    if image_models:
        print(f"\n🖼️ ရနိုင်တဲ့ image model {len(image_models)} ခု:")
        for name in image_models:
            print(f"   - {name}")
    print("\n👉 သင့် model မပါရင် .env မှာ ဥပမာ: GEMINI_MODEL="
          f"{text_models[0] if text_models else 'gemini-3.8-flash'}")
    return 0


def cmd_metadata(args: argparse.Namespace) -> int:
    metadata = metadata_service.load_or_extract_metadata(args.job_dir, persist=True)
    print(json.dumps(metadata.to_dict(), ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    job_dir = getattr(args, "job_dir", None)
    if job_dir:
        Path(job_dir).mkdir(parents=True, exist_ok=True)
    handlers = {
        "produce": cmd_produce,
        "setup": cmd_setup,
        "doctor": cmd_doctor,
        "channel": cmd_channel,
        "bot": cmd_bot,
        "serve": cmd_serve,
        "models": cmd_models,
        "auth": cmd_auth,
        "publish": cmd_publish,
        "title": cmd_title,
        "metadata": cmd_metadata,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
