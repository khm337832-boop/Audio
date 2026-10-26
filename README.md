# 🎬 Audio — မြန်မာ အသံဇာတ်လမ်း → YouTube အလိုအလျောက် Pipeline

Telegram bot မှာ **“🚀 ဇာတ်လမ်းဖန်တီးပြီး YouTube တင်မယ်”** ကို နှိပ်လိုက်ရင်
ဇာတ်လမ်းရေးကနေ YouTube channel ပေါ် တင်တဲ့အထိ အဆင့် ၈ ဆင့် အလိုအလျောက် လုပ်ပေးတယ်။

## Workflow (အဆင့် ၁–၈)

```
① Telegram — “တင်မယ်” ခလုတ်  (bot.py · handlers/start_handler.py)
        ↓
② ဇာတ်လမ်းရေး — စာလုံးရေ ၂၀,၀၀၀–၂၅,၀၀၀  (services/story_generator.py)
        ↓
③ Voice over — မြန်မာ TTS / ElevenLabs Charon (services/tts_service.py)
        ↓
④ ဇာတ်ကွက်အလိုက် ပုံဖန်တီး — scene prompt + image (services/scene_service.py)
        ↓
⑤ Motion video ဖန်တီး (services/video_service.py → ffmpeg)
        ↓
⑥ အသံနဲ့ ပေါင်းစပ် → final.mp4
        ↓
⑦ သင်္ကေတပုံ + SEO ခေါင်းစဉ်/ဖော်ပြချက် (services/thumbnail_service.py · youtube_service.py)
        ↓
⑧ YouTube channel မှာ တင်ခြင်း — ဗီဒီယို + thumbnail (services/youtube_service.py)
```

အားလုံးကို `pipeline.StoryPipeline` က စီစဉ်တယ် — bot နဲ့ CLI နှစ်ခုလုံး အဲဒါကို ခေါ်တယ်။
ဗီဒီယိုပြီးသား (mp4) ရှိရင် **ဖိုင်ကို bot ထဲ ပို့လိုက်ရုံ**နဲ့ အဆင့် ၇-၈ ကို လုပ်ပေးတယ်။

## ဖိုင်ဖွဲ့စည်းပုံ

```
bot.py                       # Telegram: ခလုတ် → pipeline → YouTube
pipeline.py                  # ★ အဆင့် ၂-၈ ကို စီစဉ်တဲ့ StoryPipeline (+ progress)
workflow.py                  # ★ PublishWorkflow (metadata → title → desc → thumbnail → upload)
main.py                      # CLI: produce / publish / auth / title / metadata
check_setup.py               # ဘာတွေ လိုနေလဲ စစ်ဆေးခြင်း
config.py                    # .env + limit/threshold အားလုံး

models/story.py              # Story / Chapter / StoryMetadata (+ story.json)
services/
  story_generator.py         # ② ၂၀,၀၀၀–၂၅,၀၀၀ စာလုံး (outline → အခန်းလိုက်)
  tts_service.py             # ③ local (မြန်မာ) / ElevenLabs (Charon)
  scene_service.py           # ④ ဇာတ်ကွက် prompt + ပုံ (concurrent)
  video_service.py           # ⑤⑥ motion clip + အသံပေါင်းစပ်
  media.py                   # ffmpeg wrapper (PATH → imageio-ffmpeg fallback)
  metadata_service.py        # အနှစ်ချုပ်/အခန်းအချက်အလက်
  thumbnail_service.py       # ⑦ သင်္ကေတပုံ (base → PIL စာသားထပ်)
  youtube_service.py         # ⑦ SEO + ⑧ upload (+thumbnail.set)
  image_service.py, llm.py
utils/
  textrender.py              # မြန်မာ text shaping (raqm → uharfbuzz → basic)
  textkit.py

assets/fonts/                # Padauk (မြန်မာ) — SIL OFL
tests/                       # 30 tests (network/API မလို)
```

## စတင်ခြင်း

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # key များ ထည့်ပါ
python check_setup.py           # ✅ ⚠️ ❌ စစ်ဆေးခြင်း
```

`.env` မှာ အနည်းဆုံး —

| Key | ဘာအတွက် |
|-----|---------|
| `BOT_TOKEN` | Telegram bot |
| `GEMINI_API_KEY` | ၂၀,၀၀၀+ စာလုံး ဇာတ်လမ်း၊ SEO၊ ပုံ prompt |
| `TTS_COMMAND` **သို့** `ELEVENLABS_API_KEY` | voice over (မြန်မာ / deep voice) |
| `client_secret.json` | YouTube တကယ်တင်ရန် |

## YouTube တကယ်တင်ရန် (တစ်ခါသာ ပြင်ဆင်ရမယ်)

1. Google Cloud Console → YouTube Data API v3 ကို enable
2. OAuth client (Desktop) ဖန်တီး → `client_secret.json` ကို repo root မှာ ထည့်
3. **terminal မှာ တစ်ခါ run** —

```bash
python main.py auth
# ✅ ချိတ်ဆက်ပြီး — channel: <သင့် channel> (subscribers: …)
```

token ကို `youtube-oauth2.json` မှာ သိမ်းထားတာမို့ bot က နောက်ပိုင်း browser မလိုဘဲ တင်နိုင်တယ်။
(`YOUTUBE_INTERACTIVE=false` — bot ထဲမှာ browser ဖွင့်တာ မလုပ်ပါ)

## အသုံးပြုပုံ

### Telegram

```bash
python bot.py
```

- **🚀 ဇာတ်လမ်းဖန်တီးပြီး YouTube တင်မယ်** → အကြောင်းအရာ ရိုက်ထည့် (သို့ ကျော်) → အဆင့် ၁-၈
- **🧪 စမ်းသပ် (dry-run)** → YouTube API မခေါ်ဘဲ ဗီဒီယို/thumbnail/SEO payload ထုတ်
- **ဗီဒီယိုဖိုင် ပို့** → “🎬 YouTube တင်မယ်” / “🧪 dry-run” ခလုတ် ပေါ်လာ
- `/cleanup` → temp/job folder များ ဖျက်

### CLI

```bash
python main.py produce --topic "ရှေးခေတ် ရွာတစ်ရွာက လျှို့ဝှက်ချက်"   # တကယ်တင်
python main.py produce --dry-run                                        # စမ်းသပ်
python main.py produce --chars 22000 --scenes 2 --tts elevenlabs
python main.py publish --job-dir temp/job_x --privacy unlisted          # ပြီးသားကနေ တင်
python main.py title   --job-dir temp/job_x                             # ခေါင်းစဉ် ရွေး
```

### Python

```python
import asyncio
from pipeline import produce_and_publish

result = asyncio.run(produce_and_publish(topic="…", dry_run=True))
print(result.story.total_chars, result.video_path, result.video_url)
```

## ရွေးချယ်နိုင်တဲ့ အချက်များ

| `.env` | default | ဖော်ပြချက် |
|--------|---------|-----------|
| `STORY_MIN_CHARS` / `STORY_MAX_CHARS` | 20000 / 25000 | ဇာတ်လမ်း အရှည် |
| `STORY_CHAPTER_CHARS` | 1200 | အခန်းတစ်ခန်း ပျမ်းမျှ |
| `TTS_PROVIDER` | auto | `local` (မြန်မာ) / `elevenlabs` (Charon) |
| `SCENES_PER_CHAPTER` | 2 | ဇာတ်ကွက် ပုံ အရေအတွက် |
| `IMAGE_CONCURRENCY` | 3 | ပုံ ဖန်တီးမှု တစ်ပြိုင်နက် |
| `YOUTUBE_PRIVACY_STATUS` | private | `public` / `unlisted` / `private` |
| `DRY_RUN` | false | YouTube API မခေါ်ဘဲ စမ်းသပ် |

## မြန်မာစာသား (thumbnail) နဲ့ ပတ်သက်ပြီး

Pillow က မြန်မာစာသားကို shaping မလုပ်ရင် “မြစ်” ကို “မြ စ ်” လို လေပ်နေတတ်တယ်။
ဒါကြောင့် `utils/textrender.py` က — ① raqm (Pillow+HarfBuzz) → ② uharfbuzz+freetype-py →
③ basic (သတိပေးချက်) ဆိုပြီး အလိုအလျောက် ရွေးတယ်။ မြန်မာ font `Padauk-Bold` ကို
`assets/fonts/` မှာ ပါထည့်ထားတယ် (OFL)။

## Job folder ရလဒ်များ

```
temp/job_20260101_120000/
  story.json              # ဇာတ်လမ်း + အခန်း (၂၀,၀၀၀+ စာလုံး)
  audio/                  # အခန်းလိုက် အသံ + full.wav/mp3
  scenes.json             # ဇာတ်ကွက် prompt/caption
  scenes/                 # ဇာတ်ကွက် ပုံများ
  clips/                  # motion clips
  final.mp4               # ⑥ ပြီးစီး ဗီဒီယို
  thumbnail.jpg           # ⑦ သင်္ကေတပုံ
  youtube_payload.json    # ⑧ တင်မယ့် title/description/tags
  pipeline_result.json    # အဆင့်တိုင်း အခြေအနေ + YouTube ရလဒ်
```

## Test

```bash
pytest -q          # 30 tests (network/API/ffmpeg မလို — fake အဆင့်များ)
python check_setup.py
```
