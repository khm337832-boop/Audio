"""စာသား ကိုင်တွယ်တဲ့ helper များ (wrapping, limit, timestamp, hashtag)။"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Sequence

_WHITESPACE = re.compile(r"[ \t\u00a0]+")
_NEWLINES = re.compile(r"\n{3,}")


def normalize_whitespace(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = _WHITESPACE.sub(" ", text)
    text = _NEWLINES.sub("\n\n", text)
    return text.strip()


def clamp_text(text: str, limit: int, ellipsis: str = "…") -> str:
    """`limit` စာလုံးအတွင်း ဖြတ်မယ် (ellipsis ပါ ထည့်တွက်တယ်)။"""
    text = normalize_whitespace(text)
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit <= len(ellipsis):
        return text[:limit]
    cut = text[: limit - len(ellipsis)].rstrip()
    # စကားလုံး အလယ်မှာ မဖြတ်ချင်ရင် နောက်ဆုံး space မှာ ဖြတ်
    if " " in cut and len(cut) > limit * 0.6:
        cut = cut.rsplit(" ", 1)[0]
    return cut + ellipsis


def first_sentences(text: str, count: int = 2, max_chars: int | None = None) -> str:
    text = normalize_whitespace(text)
    if not text:
        return ""
    parts = re.split(r"(?<=[။.!?])\s+", text)
    picked = " ".join(parts[:count]).strip()
    if max_chars:
        picked = clamp_text(picked, max_chars)
    return picked


def mmss(seconds: float) -> str:
    """YouTube chapter timestamp အတွက် mm:ss / h:mm:ss။"""
    seconds = max(0, int(round(seconds)))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _field(obj, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def timestamp_lines(chapters: Sequence, start: float = 0.0) -> list[str]:
    """(timestamp, title) စာကြောင်းများ — YouTube က အနည်းဆုံး 10s ခြားရမယ်။"""
    lines: list[str] = []
    cursor = float(start)
    last_emitted = -10.0
    for ch in chapters:
        if (cursor - last_emitted) >= 10:
            title = (_field(ch, "title") or "").strip()
            lines.append(f"{mmss(cursor)} {title}".strip())
            last_emitted = cursor
        cursor += float(_field(ch, "duration", 0) or 0)
    return lines


def hashtags(keywords: Iterable[str], limit: int = 8) -> str:
    seen: list[str] = []
    for raw in keywords:
        for word in re.split(r"[,;/|]+", str(raw)):
            tag = _slug_tag(word)
            if tag and tag not in seen:
                seen.append(tag)
        if len(seen) >= limit:
            break
    return " ".join(f"#{t}" for t in seen[:limit])


def _slug_tag(word: str) -> str:
    word = unicodedata.normalize("NFC", word).strip()
    if not word:
        return ""
    cleaned = re.sub(r"[^\w\u1000-\u109F\uAA60-\uAA7F]+", "", word, flags=re.UNICODE)
    return cleaned[:32]


def slugify(text: str, fallback: str = "story") -> str:
    text = unicodedata.normalize("NFKD", (text or "").strip().lower())
    ascii_only = text.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")
    return slug[:60] or fallback


def wrap_for_font(draw, text: str, font, max_width: int) -> list[str]:
    """Space မပါတဲ့ ဘာသာစကား (မြန်မာ/ဂျပန်) ကိုပါ ဖြတ်နိုင်တဲ့ word wrap။"""
    lines: list[str] = []
    for paragraph in (text or "").split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        current = ""
        for word in paragraph.split(" "):
            candidate = f"{current} {word}".strip()
            if draw.textlength(candidate, font=font) <= max_width or not current:
                # word တစ်လုံးတည်းက အကျယ်လွန်နေရင် char အလိုက် ဖြတ်
                if draw.textlength(candidate, font=font) > max_width and not current:
                    lines.extend(_break_long_word(draw, word, font, max_width))
                    current = ""
                else:
                    current = candidate
            else:
                lines.append(current)
                if draw.textlength(word, font=font) > max_width:
                    broken = _break_long_word(draw, word, font, max_width)
                    lines.extend(broken[:-1])
                    current = broken[-1] if broken else ""
                else:
                    current = word
        if current:
            lines.append(current)
    return lines


def _break_long_word(draw, word: str, font, max_width: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for ch in word:
        candidate = current + ch
        if draw.textlength(candidate, font=font) <= max_width or not current:
            current = candidate
        else:
            chunks.append(current)
            current = ch
    if current:
        chunks.append(current)
    return chunks or [word]
