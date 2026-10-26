"""ဇာတ်လမ်းအနှစ်ချုပ် + အခန်းအချက်အလက် ထုတ်ယူခြင်း (publish workflow ရဲ့ အဆင့် ၂)။

ဇာတ်လမ်းထုတ်လုပ်တဲ့အဆင့်မှာ `story.json` သိမ်းထားရင် အဲဒီကနေ တိုက်ရိုက်ယူမယ်။
မရှိရင် ဇာတ်လမ်းစာသားကနေ အနှစ်ချုပ်ကို ပြန်ထုတ်မယ် (LLM ရှိရင် LLM၊ မရှိရင် heuristic)။
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from models.story import METADATA_FILE, STORY_FILE, Story, StoryMetadata
from services import llm
from utils.textkit import clamp_text, first_sentences, normalize_whitespace

logger = logging.getLogger(__name__)

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "have", "will",
    "ပြီး", "တယ်", "ပါ", "ကို", "က", "မှာ", "နဲ့", "တဲ့", "သော", "သည်", "များ",
}


def _derive_keywords(story: Story, limit: int = 8) -> list[str]:
    words: list[str] = []
    words.extend(story.keywords)
    words.extend(story.characters)
    words.extend(story.themes)
    words.append(story.genre)

    if len(words) < limit:
        tokens = re.findall(r"[\w\u1000-\u109F]{3,}", story.full_text or "")
        freq: dict[str, int] = {}
        for token in tokens:
            low = token.lower()
            if low in _STOPWORDS:
                continue
            freq[low] = freq.get(low, 0) + 1
        for token, _ in sorted(freq.items(), key=lambda kv: kv[1], reverse=True):
            words.append(token)
            if len(words) >= limit * 2:
                break

    deduped: list[str] = []
    for word in words:
        word = normalize_whitespace(str(word))
        if word and word not in deduped:
            deduped.append(word)
    return deduped[:limit]


def _heuristic_summary(story: Story, max_chars: int = 700) -> str:
    if story.summary:
        return clamp_text(story.summary, max_chars)

    parts: list[str] = []
    for chapter in story.chapters:
        piece = chapter.summary or first_sentences(chapter.text, count=2, max_chars=220)
        if piece:
            parts.append(f"{chapter.title}: {piece}" if chapter.title else piece)
        if sum(len(p) for p in parts) >= max_chars:
            break
    if not parts:
        parts = [first_sentences(story.full_text, count=4, max_chars=max_chars)]
    return clamp_text(" ".join(parts), max_chars)


def _llm_summary(story: Story) -> dict | None:
    chapter_block = "\n".join(
        f"{i + 1}. {ch.title}: {clamp_text(ch.text, 600)}" for i, ch in enumerate(story.chapters[:20])
    )
    prompt = f"""အောက်ပါ မြန်မာဇာတ်လမ်းအတွက် YouTube ဖော်ပြချက်အတွက် metadata ထုတ်ပေးပါ။
ဇာတ်လမ်းခေါင်းစဉ်: {story.title}
အမျိုးအစား: {story.genre}

အခန်းများ:
{chapter_block}

JSON တစ်ခုတည်းသာ ပြန်ပါ (မြန်မာလို) —
{{
  "summary": "ဇာတ်လမ်းအနှစ်ချုပ် (၄-၆ ကြောင်း)",
  "logline": "တစ်ကြောင်းတည်း ဆွဲဆောင်မှုရှိတဲ့ စာကြောင်း",
  "themes": ["အဓိကအကြောင်းအရာ", "..."],
  "characters": ["ဇာတ်ကောင်", "..."],
  "keywords": ["ရှာဖွေရေးစကားလုံး", "..."],
  "chapter_summaries": ["အခန်း ၁ အနှစ်ချုပ်", "..."]
}}"""
    try:
        data = llm.generate_json(prompt, temperature=0.6)
    except llm.LLMUnavailable as exc:
        logger.info("LLM summary မရပါ၊ heuristic သုံးမယ်: %s", exc)
        return None
    return data if isinstance(data, dict) else None


def extract_story_metadata(story: Story, *, use_llm: bool | None = None) -> StoryMetadata:
    """Story → StoryMetadata (အနှစ်ချုပ်၊ အခန်းအချက်အလက်၊ keyword)။"""
    use_llm = llm.available() if use_llm is None else use_llm

    if use_llm:
        data = _llm_summary(story)
        if data:
            chapter_summaries = data.get("chapter_summaries") or []
            for i, chapter in enumerate(story.chapters):
                if i < len(chapter_summaries) and not chapter.summary:
                    chapter.summary = str(chapter_summaries[i])
            story.summary = str(data.get("summary") or story.summary)
            story.logline = str(data.get("logline") or story.logline)
            if data.get("themes"):
                story.themes = [str(t) for t in data["themes"]][:8]
            if data.get("characters"):
                story.characters = [str(c) for c in data["characters"]][:10]
            if data.get("keywords"):
                story.keywords = [str(k) for k in data["keywords"]][:10]

    story.summary = _heuristic_summary(story) if not story.summary else clamp_text(story.summary, 900)
    if not story.logline:
        story.logline = first_sentences(story.summary or story.full_text, count=1, max_chars=160)
    story.keywords = story.keywords or _derive_keywords(story)

    metadata = StoryMetadata.from_story(story, source="extracted")
    metadata.summary = clamp_text(metadata.summary, 900)
    return metadata


def load_or_extract_metadata(
    job_dir: str | Path,
    *,
    story: Story | None = None,
    persist: bool = True,
) -> StoryMetadata:
    """job folder ထဲက metadata ကို ယူမယ်၊ မရှိရင် ဇာတ်လမ်းကနေ ထုတ်မယ်။"""
    job_dir = Path(job_dir)
    metadata_path = job_dir / METADATA_FILE
    story_path = job_dir / STORY_FILE

    if metadata_path.exists():
        logger.info("metadata ကို %s ကနေ ဖတ်တယ်", metadata_path)
        metadata = StoryMetadata.load(metadata_path)
        if metadata.summary:
            return metadata

    if story is None and story_path.exists():
        story = Story.load(story_path)
    if story is None:
        raise FileNotFoundError(
            f"ဇာတ်လမ်းအချက်အလက် မတွေ့ပါ ({story_path}) — pipeline မှာ story.json သိမ်းထားဖို့ လိုတယ်"
        )

    metadata = extract_story_metadata(story)
    if persist:
        story.save(story_path)
        metadata.save(metadata_path)
    return metadata
