"""ဇာတ်လမ်း ဖန်တီးခြင်း — ဒီအဆင့်မှာ `story.json` ကို သိမ်းထားတာကြောင့်
နောက်ပိုင်း publish workflow က အနှစ်ချုပ်ကို ပြန်မထုတ်ဘဲ တိုက်ရိုက်ယူနိုင်တယ်။
"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path

from models.story import STORY_FILE, Chapter, Story
from services import llm
from utils.textkit import clamp_text, slugify

logger = logging.getLogger(__name__)

DEMO_CHAPTERS = [
    (
        "အခန်း ၁ — မြစ်ကမ်းက မီးရောင်",
        "ရွာငယ်လေးရဲ့ မြစ်ကမ်းမှာ ညတိုင်း မီးတစ်တောက် လွင့်နေတယ်လို့ ပြောကြပါတယ်။ "
        "ကျွန်တော့်အဘိုးက အဲဒီမီးကို မကြည့်ဖို့ တားမြစ်ခဲ့ပါတယ်။ ဒါပေမယ့် အဲဒီညမှာ မီးရောင်က "
        "ကျွန်တော့်နာမည်ကို ခေါ်သံ ထွက်လာပါတယ်။",
    ),
    (
        "အခန်း ၂ — တောအုပ်ထဲက လမ်း",
        "မီးရောင်နောက်ကို လိုက်သွားတဲ့အခါ တောအုပ်ထဲမှာ ဘယ်တုန်းကမှ မမြင်ဖူးတဲ့ လမ်းတစ်ခု ပေါ်လာပါတယ်။ "
        "လမ်းတစ်လျှောက် သစ်ပင်တွေပေါ်မှာ ရှေးခေတ် စာလုံးတွေ ရေးထားပြီး၊ လေက သူတို့ကို ဖတ်ပြသလို "
        "တိုးတိုးလေး ညည်းသံ ထွက်နေပါတယ်။",
    ),
    (
        "အခန်း ၃ — ပြန်လာတဲ့ အလင်း",
        "လမ်းအဆုံးမှာ ရွာရဲ့ ရှေးခေတ် စေတီတော် တစ်ဆူ ပေါ်လာပါတယ်။ ကျွန်တော့်အဘိုးက အဲဒီမှာ စောင့်နေပါတယ်။ "
        "သူက ပြုံးပြီး 'မီးရောင်က မင်းကို လမ်းပြခဲ့တာ၊ မင်း အိမ်ပြန်လာတာကို စောင့်နေတာ' လို့ ဆိုပါတယ်။ "
        "အဲဒီအချိန်မှာ ကျွန်တော် နိုးလာပြီး မြစ်ကမ်းမှာ မီးရောင် မရှိတော့ဘူးဆိုတာ သိလိုက်ရပါတယ်။",
    ),
]

DEMO_TITLE = "မြစ်ကမ်းက မီးရောင်"
DEMO_SUMMARY = (
    "ရွာငယ်လေးတစ်ခုရဲ့ မြစ်ကမ်းမှာ ညတိုင်း ပေါ်လာတဲ့ ထူးဆန်းတဲ့ မီးရောင်နောက်ကို လိုက်ရင်း "
    "ကျွန်တော်ဟာ ရှေးခေတ် စေတီတော်တစ်ဆူနဲ့ အဘိုးရဲ့ လျှို့ဝှက်ချက်ကို ရှာတွေ့ခဲ့ပါတယ်။ "
    "မိသားစု၊ အမှတ်တရနဲ့ အိမ်ပြန်လာခြင်းအကြောင်း နူးညံ့တဲ့ ဇာတ်လမ်းတစ်ပုဒ်ပါ။"
)


def _demo_story(topic: str | None) -> Story:
    title = DEMO_TITLE if not topic else clamp_text(topic, 60)
    chapters = [
        Chapter(index=i, title=t, text=body)
        for i, (t, body) in enumerate(DEMO_CHAPTERS)
    ]
    return Story(
        story_id=slugify(title) + "-" + uuid.uuid4().hex[:6],
        title=title,
        genre="ထိတ်လန့်ဖွယ် စွန့်စားခန်း",
        language="my",
        full_text="\n\n".join(f"{c.title}\n{c.text}" for c in chapters),
        chapters=chapters,
        summary=DEMO_SUMMARY,
        logline="ညတိုင်း ပေါ်လာတဲ့ မီးရောင်နောက်ကို လိုက်ရင်း ရှာတွေ့ခဲ့တဲ့ မိသားစု လျှို့ဝှက်ချက်",
        themes=["မိသားစု", "အမှတ်တရ", "အိမ်ပြန်လာခြင်း"],
        characters=["ကျွန်တော်", "အဘိုး"],
        keywords=["မြန်မာဇာတ်လမ်း", "ထိတ်လန့်ဇာတ်လမ်း", "အသံဇာတ်လမ်း", "ရွာဇာတ်လမ်း"],
    )


def _llm_story(topic: str | None, chapter_count: int, language: str) -> Story | None:
    prompt = f"""မြန်မာဘာသာနဲ့ မူရင်း ဇာတ်လမ်းတို တစ်ပုဒ် ရေးပါ (မည်သည့် ရှိပြီးသား ဇာတ်လမ်း/ကာတွန်း/ရုပ်ရှင် ကို မတုပပါနဲ့)။
{("အကြောင်းအရာ: " + topic) if topic else ""}
အခန်း {chapter_count} ခန်း ခွဲပါ။ အခန်းတစ်ခန်းကို စာလုံး 120-200 ။

JSON တစ်ခုတည်းသာ ပြန်ပါ:
{{
  "title": "ဇာတ်လမ်းခေါင်းစဉ်",
  "genre": "အမျိုးအစား",
  "logline": "တစ်ကြောင်း ဆွဲဆောင်ချက်",
  "summary": "အနှစ်ချုပ် ၄-၆ ကြောင်း",
  "themes": ["...", "..."],
  "characters": ["...", "..."],
  "keywords": ["...", "..."],
  "chapters": [{{"title": "အခန်း ၁ — ...", "text": "..."}}]
}}"""
    try:
        data = llm.generate_json(prompt, temperature=0.95, max_output_tokens=4096)
    except llm.LLMUnavailable as exc:
        logger.info("LLM မရပါ — demo ဇာတ်လမ်း သုံးမယ်: %s", exc)
        return None
    if not isinstance(data, dict) or not data.get("chapters"):
        return None

    chapters: list[Chapter] = []
    for i, raw in enumerate(data["chapters"]):
        if isinstance(raw, str):
            raw = {"title": f"အခန်း {i + 1}", "text": raw}
        text = str(raw.get("text", "")).strip()
        if not text:
            continue
        chapters.append(Chapter(index=len(chapters), title=str(raw.get("title", f"အခန်း {i + 1}")), text=text))
    if not chapters:
        return None

    title = clamp_text(str(data.get("title") or (topic or DEMO_TITLE)), 80)
    return Story(
        story_id=slugify(title) + "-" + uuid.uuid4().hex[:6],
        title=title,
        genre=str(data.get("genre") or "ဇာတ်လမ်း"),
        language=language,
        full_text="\n\n".join(f"{c.title}\n{c.text}" for c in chapters),
        chapters=chapters,
        summary=str(data.get("summary") or ""),
        logline=str(data.get("logline") or ""),
        themes=[str(t) for t in data.get("themes", [])][:8],
        characters=[str(c) for c in data.get("characters", [])][:10],
        keywords=[str(k) for k in data.get("keywords", [])][:10],
    )


def generate_full_story(
    topic: str | None = None,
    *,
    chapter_count: int = 4,
    language: str = "my",
    use_llm: bool | None = None,
) -> Story:
    """ဇာတ်လမ်းအပြည့်အစုံ (အခန်းများ + အနှစ်ချုပ် + keyword) ကို ဖန်တီးတယ်။"""
    if use_llm is None:
        use_llm = llm.available()
    story = _llm_story(topic, chapter_count, language) if use_llm else None
    if story is None:
        story = _demo_story(topic)
    if not story.summary:
        story.summary = DEMO_SUMMARY if story.title == DEMO_TITLE else ""
    story.full_text = story.full_text or "\n\n".join(f"{c.title}\n{c.text}" for c in story.chapters)
    return story


def save_story(story: Story, job_dir: str | Path) -> Path:
    """`story.json` ကို သိမ်း — publish workflow က ဒီဖိုင်ကနေ metadata ယူမယ်။"""
    return story.save(Path(job_dir) / STORY_FILE)


def load_story(job_dir: str | Path) -> Story | None:
    path = Path(job_dir) / STORY_FILE
    return Story.load(path) if path.exists() else None


def split_into_chapters(text: str, chapter_count: int = 4) -> list[Chapter]:
    """စာသားတစ်ခုတည်းကို အခန်းများအဖြစ် အကြမ်းဖျင်း ခွဲတယ် (TTS အပိုင်းခွဲရန်)။"""
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    chapter_count = max(1, chapter_count)
    size = max(1, len(text) // chapter_count)
    chunks, cursor = [], 0
    for _ in range(chapter_count - 1):
        end = min(len(text), cursor + size)
        boundary = text.find("။", end)
        end = boundary + 1 if boundary != -1 and boundary + 1 - cursor <= size * 1.5 else end
        chunks.append(text[cursor:end].strip())
        cursor = end
    chunks.append(text[cursor:].strip())
    return [
        Chapter(index=i, title=f"အခန်း {i + 1}", text=chunk)
        for i, chunk in enumerate(chunks) if chunk
    ]
