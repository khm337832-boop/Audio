"""ဇာတ်လမ်း / အခန်း / publish-metadata data model များ။"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STORY_FILE = "story.json"
METADATA_FILE = "story_metadata.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Chapter:
    index: int
    title: str
    text: str
    duration: float = 0.0          # TTS ပြီးမှ ရမယ့် အသံကြာချိန် (စက္ကန့်)
    audio_path: str | None = None
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Chapter":
        return cls(
            index=int(raw.get("index", 0)),
            title=str(raw.get("title", "")),
            text=str(raw.get("text", "")),
            duration=float(raw.get("duration", 0) or 0),
            audio_path=raw.get("audio_path"),
            summary=str(raw.get("summary", "")),
        )


@dataclass
class Story:
    """ဇာတ်လမ်းထုတ်လုပ်တဲ့အဆင့်မှာ ဖန်တီးပြီး `story.json` အနေနဲ့ သိမ်းထားမယ့် object။"""

    story_id: str
    title: str
    genre: str
    language: str
    full_text: str
    chapters: list[Chapter] = field(default_factory=list)
    summary: str = ""
    logline: str = ""
    themes: list[str] = field(default_factory=list)
    characters: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now)
    target_chars: int = 0
    length_ok: bool = True
    generation_notes: list[str] = field(default_factory=list)

    # ------------------------------------------------------------ helpers
    @property
    def total_chars(self) -> int:
        return len(self.full_text or "")

    @property
    def total_duration(self) -> float:
        return sum(ch.duration for ch in self.chapters)

    def chapter_dicts(self) -> list[dict[str, Any]]:
        return [ch.to_dict() for ch in self.chapters]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["total_chars"] = self.total_chars
        data["total_duration"] = self.total_duration
        return data

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Story":
        return cls(
            story_id=str(raw.get("story_id", "story")),
            title=str(raw.get("title", "")),
            genre=str(raw.get("genre", "")),
            language=str(raw.get("language", "my")),
            full_text=str(raw.get("full_text", "")),
            chapters=[Chapter.from_dict(c) for c in raw.get("chapters", [])],
            summary=str(raw.get("summary", "")),
            logline=str(raw.get("logline", "")),
            themes=list(raw.get("themes", [])),
            characters=list(raw.get("characters", [])),
            keywords=list(raw.get("keywords", [])),
            created_at=str(raw.get("created_at", _now())),
            target_chars=int(raw.get("target_chars", 0) or 0),
            length_ok=bool(raw.get("length_ok", True)),
            generation_notes=list(raw.get("generation_notes", [])),
        )

    # ------------------------------------------------------------ persistence
    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), "utf-8")
        return path

    @classmethod
    def load(cls, path: str | Path) -> "Story":
        raw = json.loads(Path(path).read_text("utf-8"))
        return cls.from_dict(raw)


@dataclass
class StoryMetadata:
    """YouTube publish အတွက် လိုအပ်တဲ့ အနှစ်ချုပ် + အခန်းအချက်အလက် (title/desc/thumbnail အားလုံး ဒီကနေ ဆင်းတယ်)။

    `source` က metadata က ဘယ်လိုလာလဲ ပြတယ်:
      - ``story``     : ဇာတ်လမ်းထုတ်လုပ်တဲ့အဆင့်မှာ သိမ်းထားတာ (အကောင်းဆုံး)
      - ``extracted`` : video ပြီးမှ ဇာတ်လမ်းစာသားကနေ ပြန်ထုတ်ထားတာ
    """

    story_id: str
    title: str
    genre: str
    language: str
    summary: str
    logline: str = ""
    themes: list[str] = field(default_factory=list)
    characters: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    chapters: list[dict[str, Any]] = field(default_factory=list)
    total_chars: int = 0
    total_duration: float = 0.0
    created_at: str = field(default_factory=_now)
    source: str = "story"

    @property
    def has_timestamps(self) -> bool:
        return any(float(c.get("duration") or 0) > 0 for c in self.chapters)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "StoryMetadata":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in raw.items() if k in known})

    @classmethod
    def from_story(cls, story: Story, source: str = "story") -> "StoryMetadata":
        return cls(
            story_id=story.story_id,
            title=story.title,
            genre=story.genre,
            language=story.language,
            summary=story.summary,
            logline=story.logline,
            themes=list(story.themes),
            characters=list(story.characters),
            keywords=list(story.keywords),
            chapters=story.chapter_dicts(),
            total_chars=story.total_chars,
            total_duration=story.total_duration,
            source=source,
        )

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), "utf-8")
        return path

    @classmethod
    def load(cls, path: str | Path) -> "StoryMetadata":
        return cls.from_dict(json.loads(Path(path).read_text("utf-8")))
