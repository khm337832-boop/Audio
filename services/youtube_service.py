"""YouTube: ခေါင်းစဉ် → ဖော်ပြချက် (SEO) → tag → API တင်ခြင်း (thumbnail အပါ)။"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import config
from models.story import StoryMetadata
from services import llm
from utils.textkit import clamp_text, hashtags, normalize_whitespace, timestamp_lines

logger = logging.getLogger(__name__)

SCOPES = (
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
)
CHUNK_SIZE = 8 * 1024 * 1024
RETRIABLE_STATUS = {500, 502, 503, 504}
RETRIABLE_EXCEPTIONS = ("httplib2.error.ServerNotFoundError", "socket.timeout", "ConnectionResetError")

BASE_TAGS = ["မြန်မာဇာတ်လမ်း", "myanmar story", "audio story", "မြန်မာ audiobook", "story time"]


class YouTubeError(RuntimeError):
    """YouTube ပိုင်း အမှား အားလုံးရဲ့ base class။"""


class YouTubeAuthError(YouTubeError):
    pass


class YouTubeUploadError(YouTubeError):
    pass


@dataclass
class UploadResult:
    video_id: str
    url: str
    title: str
    privacy_status: str
    dry_run: bool = False
    thumbnail_set: bool = False
    scheduled_at: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ===================================================================== ① titles
def _short_title(metadata: StoryMetadata, limit: int = 55) -> str:
    return clamp_text(metadata.title or "ဇာတ်လမ်း", limit)


def _template_titles(metadata: StoryMetadata) -> list[str]:
    short = _short_title(metadata)
    genre = metadata.genre or "ဇာတ်လမ်း"
    logline = clamp_text(metadata.logline or metadata.summary, 60)
    chapters = len(metadata.chapters)
    templates = [
        f"{short} | {genre} ဇာတ်လမ်း အခန်းပြည့်",
        f"{short} — {logline}",
        f"နားထောင်ကြည့်ပါ… {short} | မြန်မာ အသံဇာတ်လမ်း",
        f"{short} | အခန်း {chapters} ခန်း အပြည့်အစုံ" if chapters else f"{short} | အပြည့်အစုံ",
        f"{short} | {genre} ဇာတ်လမ်းတွဲ (Full Story)",
    ]
    return [clamp_text(t, config.TITLE_MAX_CHARS) for t in templates]


def generate_youtube_title(
    metadata: StoryMetadata,
    count: int = 3,
    *,
    extra_hint: str | None = None,
) -> list[str]:
    """SEO အတွက် ခေါင်းစဉ် ကိုယ်စားလှယ် (count) ခု ထုတ်ပေးတယ်။ ပထမတစ်ခုက အကြံပြုချက်။"""
    count = max(1, int(count))
    candidates: list[str] = []

    if llm.available():
        chapter_titles = ", ".join(str(c.get("title", "")) for c in metadata.chapters[:6])
        prompt = f"""YouTube ဗီဒီယိုအတွက် မြန်မာလို ခေါင်းစဉ် {count} ခု ရေးပါ။
ဇာတ်လမ်း: {metadata.title}
အမျိုးအစား: {metadata.genre}
အနှစ်ချုပ်: {clamp_text(metadata.summary, 500)}
အခန်းများ: {chapter_titles}
{("ထပ်ဆောင်း အချက်: " + extra_hint) if extra_hint else ""}

စည်းကမ်း:
- တစ်ခုကို စာလုံး 90 အောက်
- လိမ်ညာမှုမပါ၊ clickbait မလွန်ကဲ
- ရှာဖွေရေးစကားလုံး (ဇာတ်လမ်း၊ အသံဇာတ်လမ်း၊ အမျိုးအစား) ထည့်
- မြန်မာစာသား၊ လိုအပ်ရင် အင်္ဂလိပ်စကားလုံး အနည်းငယ်

JSON array အနေနဲ့သာ ပြန်ပါ: ["ခေါင်းစဉ် ၁", "ခေါင်းစဉ် ၂"]"""
        try:
            data = llm.generate_json(prompt, temperature=0.95, max_output_tokens=800)
            if isinstance(data, dict):
                data = data.get("titles") or data.get("title") or []
            if isinstance(data, str):
                data = [data]
            candidates = [normalize_whitespace(str(t)) for t in data if str(t).strip()]
        except llm.LLMUnavailable as exc:
            logger.info("title LLM မရပါ — template သုံးမယ်: %s", exc)

    candidates.extend(_template_titles(metadata))

    unique: list[str] = []
    for candidate in candidates:
        candidate = clamp_text(candidate, config.TITLE_MAX_CHARS)
        if candidate and candidate not in unique:
            unique.append(candidate)
        if len(unique) >= count:
            break
    return unique


def score_title(candidate: str, metadata: StoryMetadata) -> int:
    """ရိုးရှင်းတဲ့ SEO heuristic score (ကြီးရင် ပိုကောင်း)။"""
    score = 0
    length = len(candidate)
    if 35 <= length <= 70:
        score += 30
    elif 25 <= length <= 90:
        score += 15
    if any(ch.isdigit() for ch in candidate):
        score += 8
    if metadata.genre and metadata.genre in candidate:
        score += 6
    if "ဇာတ်လမ်း" in candidate:
        score += 10
    if any(kw and kw in candidate for kw in metadata.keywords[:6]):
        score += 5
    if candidate.count("!") > 2 or candidate.count("?") > 2:
        score -= 5
    if candidate.isupper():
        score -= 10
    return score


def pick_title(candidates: list[str], metadata: StoryMetadata) -> str:
    if not candidates:
        raise YouTubeError("ခေါင်းစဉ် ဗလာ — generate_youtube_title() ကို အရင်ခေါ်ပါ")
    return max(candidates, key=lambda c: score_title(c, metadata))


# ===================================================================== ② description
def _chapter_block(metadata: StoryMetadata) -> str:
    lines = timestamp_lines(metadata.chapters)
    if len(lines) < 2:
        return ""
    return "🎬 အခန်းများ\n" + "\n".join(lines)


def generate_youtube_tags(metadata: StoryMetadata, limit: int = 18) -> list[str]:
    tags: list[str] = []
    for word in (
        metadata.keywords
        + metadata.characters
        + metadata.themes
        + [metadata.genre, metadata.title, "အသံဇာတ်လမ်း", "မြန်မာစာ"]
        + BASE_TAGS
    ):
        word = normalize_whitespace(str(word or ""))
        if word and word not in tags:
            tags.append(word)
        if len(tags) >= limit:
            break
    # YouTube က tag စုစုပေါင်း 500 စာလုံး ပဲ လက်ခံတယ်
    total, kept = 0, []
    for tag in tags:
        if total + len(tag) + 1 > 480:
            break
        kept.append(tag)
        total += len(tag) + 1
    return kept


def _description_template(metadata: StoryMetadata, title: str) -> str:
    hook = metadata.logline or clamp_text(metadata.summary, 150)
    parts: list[str] = [hook, ""]
    parts.append("📖 ဇာတ်လမ်းအနှစ်ချုပ်")
    parts.append(clamp_text(metadata.summary or hook, 1200))

    chapters = _chapter_block(metadata)
    if chapters:
        parts += ["", chapters]

    if metadata.characters:
        parts += ["", "👥 ဇာတ်ကောင်များ: " + ", ".join(metadata.characters[:10])]

    parts += [
        "",
        "👉 နောက်အပိုင်းတွေ မလွတ်ရအောင် Subscribe လုပ်ပေးပါ။",
        "💬 ကြိုက်နှစ်သက်ရင် Like နဲ့ သူငယ်ချင်းတွေကို Share လုပ်ပေးပါ။",
    ]

    if metadata.keywords:
        parts += ["", "🔍 ရှာဖွေရန်: " + ", ".join(metadata.keywords[:10])]

    tag_line = hashtags(
        list(metadata.keywords[:6]) + [metadata.genre, "မြန်မာဇာတ်လမ်း", "audiobook"]
    )
    if tag_line:
        parts += ["", tag_line]

    return "\n".join(parts)


def generate_youtube_description(
    metadata: StoryMetadata,
    title: str,
    *,
    hashtag_limit: int = 8,
) -> str:
    """SEO ပါဝင်တဲ့ ဖော်ပြချက် (YouTube limit အတွင်း သေချာအောင် ဖြတ်ထားတယ်)။"""
    description = ""
    if llm.available():
        chapter_titles = "\n".join(
            f"- {c.get('title', '')}" for c in metadata.chapters[:12]
        )
        prompt = f"""YouTube ဖော်ပြချက် (SEO) ကို မြန်မာလို ရေးပါ။ ခေါင်းစဉ်: {title}
ဇာတ်လမ်း: {metadata.title} | အမျိုးအစား: {metadata.genre}
အနှစ်ချုပ်: {clamp_text(metadata.summary, 800)}
အခန်းများ:
{chapter_titles}
သော့ချက်စကားလုံးများ: {", ".join(metadata.keywords[:10])}

ဖွဲ့စည်းပုံ (ခေါင်းစဉ်တွေပါ ထည့်ပါ):
1) ဆွဲဆောင်တဲ့ နိဒါန်း ၂ ကြောင်း
2) 📖 ဇာတ်လမ်းအနှစ်ချုပ် (၄-၆ ကြောင်း)
3) အခန်းစာရင်း (ကျွန်တော် ပေးတဲ့ timestamp ကို မပြောင်းပါနဲ့)
4) Subscribe/Like ဖိတ်ခေါ်ချက်
5) သော့ချက်စကားလုံး နဲ့ hashtag လိုင်း
စာလုံး 1500 အောက်ထားပါ။ Markdown မသုံးပါနဲ့။"""
        try:
            description = normalize_whitespace(llm.generate_text(prompt, temperature=0.8, max_output_tokens=1600))
        except llm.LLMUnavailable as exc:
            logger.info("description LLM မရပါ — template သုံးမယ်: %s", exc)

    if len(description) < 120:
        description = _description_template(metadata, title)

    description = description.replace("```", "").strip()
    if len(description) > config.DESCRIPTION_SAFE_CHARS:
        description = description[: config.DESCRIPTION_SAFE_CHARS - 1].rstrip() + "…"
    return description


# ===================================================================== ③ upload
def _validate_payload(title: str, description: str, thumbnail_path: Path | None) -> None:
    if not title.strip():
        raise YouTubeError("ခေါင်းစဉ် ဗလာဖြစ်နေတယ်")
    if len(title) > config.TITLE_MAX_CHARS:
        raise YouTubeError(f"ခေါင်းစဉ် ရှည်လွန်းတယ် ({len(title)} > {config.TITLE_MAX_CHARS})")
    if len(description) > config.DESCRIPTION_MAX_CHARS:
        raise YouTubeError(f"ဖော်ပြချက် ရှည်လွန်းတယ် ({len(description)} > {config.DESCRIPTION_MAX_CHARS})")
    if thumbnail_path is not None:
        if not thumbnail_path.is_file():
            raise YouTubeError(f"thumbnail ဖိုင် မတွေ့ပါ: {thumbnail_path}")
        if thumbnail_path.stat().st_size > config.THUMBNAIL_MAX_BYTES:
            raise YouTubeError("thumbnail ဖိုင် 2MB ကျော်နေတယ်")


def get_authenticated_service(
    client_secret_file: str | Path | None = None,
    token_file: str | Path | None = None,
    *,
    interactive: bool = True,
):
    """OAuth2 နဲ့ YouTube client ကို ပြန်ပေးတယ် (token ကို cache လုပ်ထားတယ်)။"""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except Exception as exc:  # pragma: no cover - optional dependency
        raise YouTubeAuthError(f"google-api-python-client မရှိပါ: {exc}") from exc

    client_secret_file = Path(client_secret_file or config.YOUTUBE_CLIENT_SECRETS)
    token_file = Path(token_file or config.YOUTUBE_TOKEN_FILE)

    creds = None
    if token_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_file), list(SCOPES))
        except Exception as exc:  # token ပျက်နေရင် အသစ်ပြန်ယူ
            logger.warning("token ဖတ်မရပါ: %s", exc)
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not client_secret_file.exists():
                raise YouTubeAuthError(
                    f"OAuth client secret မတွေ့ပါ: {client_secret_file} — "
                    "Google Cloud Console ကနေ ဒေါင်းလုပ်ပြီး client_secret.json အနေနဲ့ ထည့်ပါ"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_file), list(SCOPES))
            if not interactive:
                raise YouTubeAuthError("interactive OAuth မဖြစ်နိုင်ပါ — token_file လိုတယ်")
            try:
                creds = flow.run_local_server(port=0, open_browser=False)
            except Exception:
                creds = flow.run_console()

        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(creds.to_json(), encoding="utf-8")
        logger.info("OAuth token သိမ်းပြီး: %s", token_file)

    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload_thumbnail(youtube, video_id: str, thumbnail_path: str | Path) -> bool:
    try:
        from googleapiclient.http import MediaFileUpload
    except Exception as exc:  # pragma: no cover
        raise YouTubeError(f"googleapiclient မရှိပါ: {exc}") from exc

    path = Path(thumbnail_path)
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    youtube.thumbnails().set(
        videoId=video_id, media_body=MediaFileUpload(str(path), mimetype=mime)
    ).execute()
    logger.info("thumbnail တင်ပြီး (video=%s)", video_id)
    return True


def upload_video(
    video_path: str | Path,
    title: str,
    description: str,
    thumbnail_path: str | Path | None = None,
    *,
    tags: list[str] | None = None,
    privacy_status: str | None = None,
    publish_at: str | None = None,
    category_id: str | None = None,
    made_for_kids: bool | None = None,
    language: str | None = None,
    dry_run: bool | None = None,
    client: Any | None = None,
) -> UploadResult:
    """ဗီဒီယိုကို YouTube ပေါ် တင်မယ် (ပြီးရင် thumbnail ထပ်တင်မယ်)။

    `dry_run=None` ဆိုရင်: DRY_RUN=true ဖြစ်နေရင် ဒါမှမဟုတ် OAuth client secret မရှိရင်
    network မခေါ်ဘဲ simulated id ပြန်ပေးတယ် (local test အတွက်)။
    """
    video_path = Path(video_path)
    thumbnail_path = Path(thumbnail_path) if thumbnail_path else None
    if not video_path.is_file() or video_path.stat().st_size == 0:
        raise YouTubeError(f"ဗီဒီယိုဖိုင် မတွေ့ပါ / ဗလာဖြစ်နေတယ်: {video_path}")

    _validate_payload(title, description, thumbnail_path)

    if dry_run is None:
        dry_run = config.DRY_RUN or not Path(config.YOUTUBE_CLIENT_SECRETS).exists()

    privacy = privacy_status or config.YOUTUBE_PRIVACY_STATUS
    if publish_at:
        privacy = "private"  # scheduled publish က private ပဲ ဖြစ်ရမယ်

    if dry_run:
        digest = hashlib.sha256(
            f"{video_path}|{title}|{time.time()}".encode("utf-8")
        ).hexdigest()[:10]
        logger.warning("DRY-RUN: YouTube API မခေါ်ဘဲ upload အတုလုပ်တယ် (title=%s)", title)
        return UploadResult(
            video_id=f"dryrun-{digest}",
            url="",
            title=title,
            privacy_status=privacy,
            dry_run=True,
            thumbnail_set=thumbnail_path is not None,
            scheduled_at=publish_at,
            raw={"note": "dry-run — YouTube API မခေါ်ပါ"},
        )

    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError

    youtube = client or get_authenticated_service()

    body: dict[str, Any] = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": category_id or config.YOUTUBE_CATEGORY_ID,
            "defaultLanguage": language or config.YOUTUBE_LANGUAGE,
            "defaultAudioLanguage": config.YOUTUBE_DEFAULT_AUDIO_LANGUAGE,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": bool(
                config.YOUTUBE_MADE_FOR_KIDS if made_for_kids is None else made_for_kids
            ),
        },
    }
    if publish_at:
        body["status"]["publishAt"] = publish_at

    media = MediaFileUpload(
        str(video_path),
        chunksize=CHUNK_SIZE,
        resumable=True,
        mimetype="video/*",
    )
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response: dict[str, Any] | None = None
    retry = 0
    while response is None:
        try:
            _, response = request.next_chunk()
        except HttpError as exc:
            status = getattr(exc, "status_code", None) or getattr(exc.resp, "status", 0)
            if status in RETRIABLE_STATUS and retry < 6:
                retry += 1
                wait = min(60, 2 ** retry) + random.uniform(0, 1)
                logger.warning("upload %s — %ss စောင့်ပြီး ပြန်ကြိုးစားမယ်", status, round(wait, 1))
                time.sleep(wait)
                continue
            raise YouTubeUploadError(f"YouTube upload မအောင်မြင်ပါ: {exc}") from exc
        except Exception as exc:
            if retry < 6:
                retry += 1
                time.sleep(min(60, 2 ** retry))
                continue
            raise YouTubeUploadError(f"YouTube upload မအောင်မြင်ပါ: {exc}") from exc

    video_id = response.get("id", "")
    thumb_ok = False
    if thumbnail_path is not None and video_id:
        try:
            thumb_ok = upload_thumbnail(youtube, video_id, thumbnail_path)
        except Exception as exc:
            logger.error("thumbnail တင်မရပါ (ဗီဒီယိုတော့ တင်ပြီး): %s", exc)

    return UploadResult(
        video_id=video_id,
        url=f"https://youtu.be/{video_id}" if video_id else "",
        title=title,
        privacy_status=privacy,
        dry_run=False,
        thumbnail_set=thumb_ok,
        scheduled_at=publish_at,
        raw=response or {},
    )


def dump_payload(path: str | Path, **payload: Any) -> Path:
    """တင်မယ့် payload ကို JSON အနေနဲ့ သိမ်း (debug / audit)။"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
    return path
