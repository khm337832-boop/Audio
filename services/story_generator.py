"""ဇာတ်လမ်း ဖန်တီးခြင်း — စာလုံးရေ ၂၀,၀၀၀–၂၅,၀၀၀ ရှိတဲ့ ဇာတ်လမ်းအပြည့်အစုံ။

အဆင့်:
  1. outline (ခေါင်းစဉ်၊ အမျိုးအစား၊ ဇာတ်ကောင်၊ အခန်းခေါင်းစဉ် ၁၆-၂၀ ခု)
  2. အခန်းတစ်ခန်းစီ (~၁၂၀၀ စာလုံး) ကို အစဉ်လိုက် ရေး — ရှေ့အခန်းရဲ့ အဆုံးကို ဆက်စပ်ပေးတယ်
  3. စာလုံးရေ ပစ်မှတ် မပြည့်မချင်း အခန်း ထပ်ထည့် (အများဆုံး STORY_MAX_CHAPTERS)

ဒီအဆင့်မှာ `story.json` သိမ်းထားတာကြောင့် နောက်ပိုင်း publish workflow က
အနှစ်ချုပ်/အခန်းအချက်အလက်ကို ပြန်မထုတ်ဘဲ တိုက်ရိုက် ယူနိုင်တယ်။
"""

from __future__ import annotations

import logging
import math
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import config
from models.story import STORY_FILE, Chapter, Story
from services import llm
from utils.textkit import clamp_text, normalize_whitespace, slugify

logger = logging.getLogger(__name__)

ProgressFn = Callable[[str], None]

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

# အခန်းခေါင်းစဉ် မလုံလောက်ရင် အစားထိုး သုံးမယ့် ပုံစံများ
_EXTRA_TITLES = [
    "အခန်း {n} — အရိပ်တစ်ခု နောက်ကွယ်မှ",
    "အခန်း {n} — မပြောခဲ့တဲ့ စကား",
    "အခန်း {n} — မိုးမလင်းခင်မှာ",
    "အခန်း {n} — လျှို့ဝှက်ချက် တစ်စိတ်တစ်ပိုင်း",
    "အခန်း {n} — နောက်ဆုံး လမ်းဆုံ",
]


@dataclass
class StoryPlan:
    """ဇာတ်လမ်း မရေးခင် ရေးဆွဲတဲ့ အစီအစဉ်။"""

    title: str
    genre: str
    logline: str = ""
    summary: str = ""
    themes: list[str] = field(default_factory=list)
    characters: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    chapter_titles: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ plan
def _chapter_count(target_chars: int) -> int:
    per = max(600, config.STORY_CHAPTER_CHARS)
    count = math.ceil(target_chars / per)
    return max(4, min(config.STORY_MAX_CHAPTERS, count))


def _plan_story(
    topic: str | None,
    target_chars: int,
    language: str,
    *,
    json_fn: Callable[..., object] = llm.generate_json,
) -> StoryPlan | None:
    count = _chapter_count(target_chars)
    prompt = f"""မြန်မာဘာသာနဲ့ မူရင်း ဇာတ်လမ်းတစ်ပုဒ် ရေးဖို့ အစီအစဉ် ဆွဲပါ။
(မည်သည့် ရှိပြီးသား ဇာတ်လမ်း/ရုပ်ရှင်/ကာတွန်း/ဂိမ်း ကို မတုပပါနဲ့။ မူရင်း ဖြစ်ရမယ်။)
{("အကြောင်းအရာ/အခြေအနေ: " + topic) if topic else "အကြောင်းအရာ: စွန့်စားခန်း သို့ လူစိတ်ဝင်စားစရာ ဇာတ်လမ်း"}

လိုအပ်ချက်:
- အခန်း {count} ခန်း၊ အခန်းတစ်ခန်းက စာလုံးရေ ၁၀၀၀ မှ ၁၃၀၀ အတွင်း (စုစုပေါင်း {target_chars} ခန့်)
- ဇာတ်ကောင် ၃-၆ ဦး၊ ဇာတ်ကွက် ရှင်းရှင်း၊ အခန်းတစ်ခန်းစီ အဆုံးမှာ ဆက်ဖတ်ချင်စရာ
- အခန်းခေါင်းစဉ်တွေက အတိုအထွာ၊ ဆွဲဆောင်မှုရှိ

JSON တစ်ခုတည်းသာ ပြန်ပါ:
{{
  "title": "ဇာတ်လမ်းခေါင်းစဉ်",
  "genre": "အမျိုးအစား",
  "logline": "တစ်ကြောင်း ဆွဲဆောင်ချက်",
  "summary": "ဇာတ်လမ်းအနှစ်ချုပ် ၅-၇ ကြောင်း",
  "themes": ["...", "..."],
  "characters": ["...", "..."],
  "keywords": ["...", "..."],
  "chapter_titles": ["အခန်း ၁ — ...", "အခန်း ၂ — ..."]
}}"""
    try:
        data = json_fn(prompt, temperature=0.9, max_output_tokens=4096)
    except llm.LLMUnavailable as exc:
        logger.info("outline LLM မရပါ — offline ဇာတ်လမ်း သုံးမယ်: %s", exc)
        return None
    if not isinstance(data, dict):
        return None

    titles = [str(t) for t in (data.get("chapter_titles") or []) if str(t).strip()]
    while len(titles) < count:
        titles.append(_EXTRA_TITLES[len(titles) % len(_EXTRA_TITLES)].format(n=len(titles) + 1))

    return StoryPlan(
        title=clamp_text(str(data.get("title") or topic or DEMO_TITLE), 80),
        genre=str(data.get("genre") or "စွန့်စားခန်း"),
        logline=str(data.get("logline") or ""),
        summary=str(data.get("summary") or ""),
        themes=[str(t) for t in data.get("themes", [])][:8],
        characters=[str(c) for c in data.get("characters", [])][:10],
        keywords=[str(k) for k in data.get("keywords", [])][:10],
        chapter_titles=titles,
    )


# ------------------------------------------------------------------ chapter
_CHAPTER_PROMPT = """မြန်မာဘာသာနဲ့ ဇာတ်လမ်းရဲ့ အခန်းတစ်ခန်းကို ဆက်ရေးပါ။

ဇာတ်လမ်း: {title} ({genre})
ဇာတ်ကောင်များ: {characters}
သိထားရမယ့် အနှစ်ချုပ်: {summary}

{previous}

ယခု ရေးရမယ့် အခန်း: {chapter_title}
လိုအပ်ချက်:
- စာလုံးရေ {chars} ခန့် (မနည်းရင် မဖြစ်ပါ၊ ၉၀၀ အောက် မလျှော့ပါနဲ့)
- ဇာတ်ကွက် တိုးတက်မှုရှိရမယ်၊ အခန်းအဆုံးမှာ စိတ်ဝင်စားစရာ ချန်ထားပါ
- ရှေ့အခန်းကို ပြန်မချဲ့ပါနဲ့၊ အသစ်ဖြစ်ရမယ်
- ခေါင်းစဉ် ထပ်မရေးပါနဲ့၊ ဇာတ်လမ်းစာသားသာ ပြန်ပါ
- စကားပြောတွေမှာ ဇာတ်ကောင် အသံကွဲအောင် ရေးပါ"""


def _previous_context(chapters: list[Chapter], max_chars: int = 1200) -> str:
    if not chapters:
        return "ဒါက ပထမအခန်း ဖြစ်တယ် — ဇာတ်လမ်းကို ဖွင့်ပြပါ။"
    tail = chapters[-1].text[-max_chars:]
    return f"ရှေ့အခန်း ({chapters[-1].title}) အဆုံးပိုင်း:\n…{tail}"


def _write_chapter(
    plan: StoryPlan,
    chapters: list[Chapter],
    chapter_title: str,
    chars: int,
    *,
    text_fn: Callable[..., str] = llm.generate_text,
    attempt: int = 0,
) -> str:
    nudge = ""
    if attempt > 0:
        nudge = (
            f"\n(ယခင်အကြိမ်က စာလုံးရေ မလုံလောက်ပါ သို့မဟုတ် အကြောင်းအရာ ထပ်နေပါတယ်။ "
            f"အခန်းအသစ်အနေနဲ့ {chars} စာလုံးခန့် ပိုရှည်အောင်၊ ဖြစ်ရပ်အသစ်တွေ ထည့်ပြီး ရေးပါ။)"
        )
    prompt = _CHAPTER_PROMPT.format(
        title=plan.title,
        genre=plan.genre,
        characters=", ".join(plan.characters[:6]) or "—",
        summary=clamp_text(plan.summary or plan.logline, 500),
        previous=_previous_context(chapters),
        chapter_title=chapter_title,
        chars=chars,
    ) + nudge
    raw = text_fn(prompt, temperature=0.95, max_output_tokens=4096)
    return _clean_chapter_text(raw, chapter_title)


def _clean_chapter_text(raw: str, chapter_title: str) -> str:
    text = (raw or "").replace("```", "").strip()
    # "အခန်း ၁ — ..." လို ခေါင်းစဉ်ကို ဖြုတ်
    first_line, _, rest = text.partition("\n")
    if rest and (first_line.strip().startswith("အခန်း") or len(first_line) < 60):
        text = rest.strip()
    text = re.sub(r"^\s*(ခေါင်းစဉ်|Chapter)\s*[:：].*\n", "", text)
    return normalize_whitespace(text)


def _is_duplicate(text: str, chapters: list[Chapter]) -> bool:
    head = text[:160]
    for chapter in chapters:
        if head and head in chapter.text:
            return True
        if len(text) > 120 and text[:120] == chapter.text[:120]:
            return True
    return False


# ------------------------------------------------------------------ demo (offline)
def _demo_story(topic: str | None) -> Story:
    title = DEMO_TITLE if not topic else clamp_text(topic, 60)
    chapters = [
        Chapter(index=i, title=t, text=body) for i, (t, body) in enumerate(DEMO_CHAPTERS)
    ]
    story = Story(
        story_id=slugify(title) + "-" + uuid.uuid4().hex[:6],
        title=title,
        genre="ထိတ်လန့်ဖွယ် စွန့်စားခန်း",
        language=config.STORY_LANGUAGE,
        full_text="\n\n".join(f"{c.title}\n{c.text}" for c in chapters),
        chapters=chapters,
        summary=DEMO_SUMMARY,
        logline="ညတိုင်း ပေါ်လာတဲ့ မီးရောင်နောက်ကို လိုက်ရင်း ရှာတွေ့ခဲ့တဲ့ မိသားစု လျှို့ဝှက်ချက်",
        themes=["မိသားစု", "အမှတ်တရ", "အိမ်ပြန်လာခြင်း"],
        characters=["ကျွန်တော်", "အဘိုး"],
        keywords=["မြန်မာဇာတ်လမ်း", "ထိတ်လန့်ဇာတ်လမ်း", "အသံဇာတ်လမ်း", "ရွာဇာတ်လမ်း"],
    )
    story.generation_notes = [
        "GEMINI_API_KEY မရှိပါ — offline demo ဇာတ်လမ်း (စာလုံးရေ နည်းတယ်)",
    ]
    return story


# ------------------------------------------------------------------ main
def generate_full_story(
    topic: str | None = None,
    *,
    target_chars: int | None = None,
    min_chars: int | None = None,
    max_chars: int | None = None,
    language: str | None = None,
    use_llm: bool | None = None,
    progress: ProgressFn | None = None,
    text_fn: Callable[..., str] = llm.generate_text,
    json_fn: Callable[..., object] = llm.generate_json,
) -> Story:
    """ဇာတ်လမ်းအပြည့်အစုံ (အခန်းများ + အနှစ်ချုပ် + keyword) ဖန်တီးတယ်။

    `min_chars`/`max_chars` ကို မပေးရင် `.env` ရဲ့ STORY_MIN_CHARS/STORY_MAX_CHARS
    (default 20,000–25,000) ကို သုံးတယ်။
    """
    default_min, default_max = config.story_target()
    if target_chars and min_chars is None and max_chars is None:
        # `--chars 5000` လို ကိုယ်တိုင် သတ်မှတ်ရင် အပေါ်အောက် ၁၀% အတွင်း ထားမယ်
        min_chars = int(target_chars * 0.9)
        max_chars = int(target_chars * 1.1)
    min_chars = min_chars or default_min
    max_chars = max_chars or default_max
    target = target_chars or int((min_chars + max_chars) / 2)
    language = language or config.STORY_LANGUAGE
    if use_llm is None:
        use_llm = llm.available()

    if not use_llm:
        story = _demo_story(topic)
        story.target_chars = target
        story.length_ok = min_chars <= story.total_chars <= max_chars
        return story

    def report(message: str) -> None:
        logger.info(message)
        if progress:
            try:
                progress(message)
            except Exception:  # progress callback က pipeline ကို မရပ်စေရ
                logger.debug("progress callback မအောင်မြင်ပါ", exc_info=True)

    report("🧭 ဇာတ်လမ်း အစီအစဉ် ရေးဆွဲနေတယ်...")
    plan = _plan_story(topic, target, language, json_fn=json_fn)
    if plan is None:
        story = _demo_story(topic)
        story.target_chars = target
        story.length_ok = False
        return story

    chapters: list[Chapter] = []
    total = 0
    per_chapter = max(600, config.STORY_CHAPTER_CHARS)
    title_pool = list(plan.chapter_titles)
    max_chapters = config.STORY_MAX_CHAPTERS

    target = max(min_chars, min(target, max_chars))
    index = 0
    while index < max_chapters and total < target and total < max_chars:
        if index >= len(title_pool):
            title_pool.append(
                _EXTRA_TITLES[index % len(_EXTRA_TITLES)].format(n=index + 1)
            )
        chapter_title = title_pool[index]
        remaining = max_chars - total
        want = min(per_chapter, max(500, remaining))

        text = ""
        for attempt in range(2):
            try:
                candidate = _write_chapter(
                    plan, chapters, chapter_title, want, text_fn=text_fn, attempt=attempt
                )
            except llm.LLMUnavailable as exc:
                logger.warning("အခန်း ရေးမရပါ: %s", exc)
                break

            if len(candidate) < 250 or _is_duplicate(candidate, chapters):
                logger.info(
                    "အခန်း %s ပြန်ရေးမယ် (စာလုံး %s, duplicate=%s)",
                    index + 1, len(candidate), _is_duplicate(candidate, chapters),
                )
                text = candidate if len(candidate) > len(text) else text
                continue
            text = candidate
            break

        if not text:
            report(f"⚠️ အခန်း {index + 1} ကို ချန်လိုက်တယ် (LLM မဖြေပါ)")
            index += 1
            continue

        chapters.append(Chapter(index=len(chapters), title=chapter_title, text=text))
        total += len(text)
        index += 1
        report(
            f"✍️ အခန်း {len(chapters)}/{_chapter_count(target)} — "
            f"{total:,} / {target:,} စာလုံး"
        )

        # ပစ်မှတ် ပြည့်ပြီ — ဇာတ်လမ်း အဆုံးသတ်လို့ရပြီ
        if total >= target:
            break
        # ခေါင်းစဉ် အားလုံး ကုန်ပြီး အနည်းဆုံးချည်း ပြည့်ပြီဆိုရင် ရပ်မယ်
        if total >= min_chars and index >= len(plan.chapter_titles):
            break

    if not chapters:
        story = _demo_story(topic)
        story.target_chars = target
        story.length_ok = False
        return story

    story = Story(
        story_id=slugify(plan.title) + "-" + uuid.uuid4().hex[:6],
        title=plan.title,
        genre=plan.genre,
        language=language,
        full_text="\n\n".join(f"{c.title}\n{c.text}" for c in chapters),
        chapters=chapters,
        summary=plan.summary,
        logline=plan.logline,
        themes=plan.themes,
        characters=plan.characters,
        keywords=plan.keywords,
    )
    story.target_chars = target
    # အခန်းတစ်ခန်း တိုးလိုက်တဲ့ overshoot ကို ၅% အထိ လက်ခံ
    story.length_ok = min_chars <= story.total_chars <= max_chars * 1.05
    if not story.summary:
        story.summary = " ".join(c.text[:180] for c in chapters[:4])
    if not story.length_ok:
        story.generation_notes.append(
            f"စာလုံးရေ {story.total_chars:,} — ပစ်မှတ် {min_chars:,}–{max_chars:,} မကိုက်ပါ"
        )
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
