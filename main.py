"""Command line — ဗီဒီယိုပြီးသားကနေ YouTube တင်တဲ့အထိ။

ဥပမာ:
    python main.py publish --job-dir temp/job_20260101_120000
    python main.py publish --job-dir temp/job_x --video final.mp4 --dry-run
    python main.py title --job-dir temp/job_x
    python main.py metadata --job-dir temp/job_x
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

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

    title = sub.add_parser("title", help="ခေါင်းစဉ် ကိုယ်စားလှယ်များ ပြမယ်")
    title.add_argument("--job-dir", required=True)
    title.add_argument("--count", type=int, default=3)

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


def cmd_metadata(args: argparse.Namespace) -> int:
    metadata = metadata_service.load_or_extract_metadata(args.job_dir, persist=True)
    print(json.dumps(metadata.to_dict(), ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    Path(args.job_dir).mkdir(parents=True, exist_ok=True)
    handlers = {"publish": cmd_publish, "title": cmd_title, "metadata": cmd_metadata}
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
