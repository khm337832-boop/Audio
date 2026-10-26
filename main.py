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

    sub.add_parser("auth", help="YouTube OAuth တစ်ခါ ခွင့်ပြုချက်ယူပြီး token သိမ်းမယ်")

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


def cmd_auth(args: argparse.Namespace) -> int:
    """`python main.py auth` — browser မှာ Google ခွင့်ပြုချက် ယူပြီး token သိမ်းတယ်။"""
    from services import youtube_service

    try:
        youtube = youtube_service.get_authenticated_service(interactive=True)
        response = youtube.channels().list(part="snippet,statistics", mine=True).execute()
        items = response.get("items", [])
        if items:
            channel = items[0]["snippet"]["title"]
            subs = items[0].get("statistics", {}).get("subscriberCount", "?")
            print(f"✅ ချိတ်ဆက်ပြီး — channel: {channel} (subscribers: {subs})")
        else:
            print("✅ token သိမ်းပြီး (channel မတွေ့ပါ — YouTube channel ရှိမရှိ စစ်ပါ)")
        print(f"🔑 token: {config.YOUTUBE_TOKEN_FILE}")
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.error("OAuth မအောင်မြင်ပါ: %s", exc)
        return 1


def cmd_metadata(args: argparse.Namespace) -> int:
    metadata = metadata_service.load_or_extract_metadata(args.job_dir, persist=True)
    print(json.dumps(metadata.to_dict(), ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    Path(args.job_dir).mkdir(parents=True, exist_ok=True)
    handlers = {
        "produce": cmd_produce,
        "auth": cmd_auth,
        "publish": cmd_publish,
        "title": cmd_title,
        "metadata": cmd_metadata,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
