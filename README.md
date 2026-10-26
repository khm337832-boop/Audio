# 🎬 Audio — မြန်မာ အသံဇာတ်လမ်း → YouTube အလိုအလျောက် Pipeline

ဗီဒီယိုပေါင်းစည်းပြီးသားကနေ **YouTube ပေါ် တင်တဲ့အထိ** အဆင့်လိုက် workflow ကို
`workflow.py` ထဲမှာ စုစည်းထားပါတယ်။ ဇာတ်လမ်း + အနှစ်ချုပ်ကို `story.json`
အနေနဲ့ ဇာတ်လမ်းထုတ်လုပ်တဲ့အဆင့်မှာ သိမ်းထားတာကြောင့် နောက်ပိုင်း အနှစ်ချုပ်ကို
ပြန်မထုတ်ရပါဘူး။

## Workflow

```
ဗီဒီယိုပေါင်းစည်းခြင်း ပြီးစီး  (final.mp4)
        ↓
ဇာတ်လမ်းအနှစ်ချုပ်နှင့် အခန်းအချက်အလက်များ ထုတ်ယူခြင်း   ← story.json (ဇာတ်လမ်းအဆင့်မှာ သိမ်းထား)
        ↓
generate_youtube_title()        → ခေါင်းစဉ် ကိုယ်စားလှယ် ၃ ခု + ★ အကြံပြုချက်
        ↓
generate_youtube_description()  → SEO ဖော်ပြချက် (chapter timestamp / tag / hashtag)
        ↓
generate_thumbnail_prompt() + generate_scene_image()  → thumbnail base ပုံ
        ↓
PIL ဖြင့် စာသားထပ်ဆင့်ခြင်း     ← မြန်မာ text shaping (raqm/uharfbuzz)
        ↓
YouTube API တင်ခြင်း             → ခေါင်းစဉ် + ဖော်ပြချက် + ဗီဒီယို + thumbnail
```

## ဖိုင်ဖွဲ့စည်းပုံ

```
config.py                    # .env ဖတ်ခြင်း၊ limit/threshold အားလုံး
workflow.py                  # ★ PublishWorkflow — အဆင့် ၁-၇ ကို စီစဉ်တဲ့ နေရာ
main.py                      # CLI: publish / title / metadata
bot.py                       # Telegram bot (ဇာတ်လမ်း → ဗီဒီယို → publish)

models/story.py              # Story, Chapter, StoryMetadata (+ story.json save/load)

services/
  story_generator.py         # ဇာတ်လမ်းရေး + story.json သိမ်း
  metadata_service.py        # အနှစ်ချုပ်/အခန်းအချက်အလက် ထုတ်ယူ (LLM → heuristic fallback)
  youtube_service.py         # title / description / tags / upload (+thumbnail.set)
  thumbnail_service.py       # prompt → base ပုံ → PIL စာသားထပ်ခြင်း
  image_service.py           # Imagen/Gemini → မရရင် procedural ပုံ
  tts_service.py             # အခန်းလိုက် အသံထွက် + ပေါင်းခြင်း
  video_service.py           # clip / concat / mux (ffmpeg) — final.mp4 ထုတ်
  media.py                   # ffmpeg wrapper
  llm.py                     # Gemini wrapper (key မရှိရင် LLMUnavailable)

utils/
  textrender.py              # ★ မြန်မာ/အာရဗီ text shaping painter (raqm → uharfbuzz → basic)
  textkit.py                 # wrap/clamp/timestamp/hashtag

assets/fonts/                # Padauk (မြန်မာ) — OFL
tests/test_workflow.py       # 18 tests (network မလိုပဲ အလုပ်လုပ်တယ်)
```

## အမြန် စတင်ခြင်း

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
sudo apt install ffmpeg          # ဗီဒီယို အဆင့်အတွက်
cp .env.example .env             # API key များ ထည့်ပါ
```

## အသုံးပြုပုံ

### ① CLI — ဗီဒီယိုပြီးသားကနေ တင်တဲ့အထိ

```bash
# job folder ထဲမှာ final.mp4 + story.json ရှိရမယ်
python main.py metadata --job-dir temp/job_20260101_120000   # အနှစ်ချုပ် စစ်ကြည့်
python main.py title    --job-dir temp/job_20260101_120000   # ခေါင်းစဉ် ကိုယ်စားလှယ်များ
python main.py publish  --job-dir temp/job_20260101_120000 --dry-run
```

`--dry-run` က YouTube API မခေါ်ဘဲ `youtube_payload.json`, `thumbnail.jpg`,
`publish_result.json` ကို ထုတ်ပေးတယ် (စမ်းသပ်ရန်)။

တကယ်တင်ရင်:

```bash
python main.py publish --job-dir temp/job_x --privacy private
python main.py publish --job-dir temp/job_x --publish-at 2026-11-01T09:00:00Z   # schedule
python main.py publish --job-dir temp/job_x --title "ငါ့ ခေါင်းစဉ်"             # ကိုယ်တိုင်ရွေး
```

### ② Python ထဲကနေ

```python
import asyncio
from workflow import publish_after_video

artifacts = asyncio.run(publish_after_video("temp/job_x", dry_run=True))
print(artifacts.title, artifacts.thumbnail, artifacts.upload.url)
```

အဆင့်တစ်ခုချင်း ခေါ်ချင်ရင်:

```python
from workflow import PublishOptions, PublishWorkflow

wf = PublishWorkflow("temp/job_x", options=PublishOptions(dry_run=True))
metadata = wf.load_metadata()          # ② အနှစ်ချုပ် + အခန်းအချက်အလက်
print(metadata.summary, [c["title"] for c in metadata.chapters])
```

### ③ Telegram bot

```bash
python bot.py
```

`/start` → “🎬 ဇာတ်လမ်း ဖန်တီး” နှိပ်ရင် ဇာတ်လမ်း → အသံ → ပုံ → ဗီဒီယို →
ခေါင်းစဉ်/ဖော်ပြချက်/thumbnail → YouTube အထိ တစ်ခါတည်း လုပ်ပေးတယ်။

## Workflow အဆင့်တစ်ခုချင်း (API)

| အဆင့် | Function | ရလဒ် |
|------|----------|-------|
| ② metadata | `metadata_service.load_or_extract_metadata(job_dir)` | `StoryMetadata` (summary, logline, themes, characters, keywords, chapter durations) |
| ③ title | `youtube_service.generate_youtube_title(metadata, count=3)` | `list[str]` (100 စာလုံး limit အတွင်း) |
| ③+ | `youtube_service.pick_title(candidates, metadata)` | ★ အကြံပြု ခေါင်းစဉ် |
| ④ description | `youtube_service.generate_youtube_description(metadata, title)` | SEO description + `mm:ss` chapters + hashtags |
| ⑤ prompt | `thumbnail_service.generate_thumbnail_prompt(metadata)` | ပုံဖန်တီးရေး prompt |
| ⑤ image | `image_service.generate_scene_image(prompt, path)` | 1280×720 base ပုံ |
| ⑥ overlay | `thumbnail_service.compose_thumbnail(base, title, out, subtitle=…, badge=…)` | စာသားပါ thumbnail (JPEG ≤ 2MB) |
| ⑦ upload | `youtube_service.upload_video(video, title, desc, thumb, …)` | `UploadResult` (video_id, url, privacy) |

`upload_video()` က ဗီဒီယိုတင်ပြီးတာနဲ့ `thumbnails().set` ကို ခေါ်ပြီး
thumbnail ကို တွဲတင်ပေးတယ်။ 500/502/503/504 ဆိုရင် exponential backoff နဲ့ ပြန်ကြိုးစားတယ်။

## မြန်မာစာသား (thumbnail) နဲ့ ပတ်သက်ပြီး အရေးကြီး

Pillow က မြန်မာစာသားကို **shaping** မလုပ်ရင် ဗျည်း/သရ/ဗျည်းတွဲတွေ ကွဲထွက်ပြီး
“မြစ်” ကို “မြ စ ်” လို လေပ်နေတတ်တယ်။ ဒါကြောင့် `utils/textrender.py` က —

1. **raqm** (Pillow + HarfBuzz) ရှိရင် → `RaqmPainter`
2. မရှိရင် **uharfbuzz + freetype-py** → `ShapedPainter` (wheel နှစ်ခုသာ လိုတယ်)
3. နှစ်ခုလုံး မရှိရင် → `BasicPainter` + သတိပေးချက် log

မြန်မာ font ကို `assets/fonts/Padauk-Bold.ttf` မှာ ပါထည့်ထားပါတယ် (SIL OFL)။
တခြား font သုံးချင်ရင် `.env` မှာ `THUMBNAIL_FONT=assets/fonts/YourFont.ttf`။

## .env

| Key | ဖော်ပြချက် |
|-----|-----------|
| `BOT_TOKEN` | Telegram bot token |
| `GEMINI_API_KEY` | ဇာတ်လမ်း/title/description/prompt အတွက် (မရှိရင် template/mock သုံးတယ်) |
| `TTS_COMMAND` | TTS command template: `{text_file}`, `{output}` |
| `YOUTUBE_PRIVACY_STATUS` | `private` / `unlisted` / `public` |
| `YOUTUBE_CATEGORY_ID` | default `24` (Entertainment) |
| `THUMBNAIL_FONT` | မြန်မာ font ဖိုင်လမ်းကြောင်း |
| `DRY_RUN` / `FORCE_MOCK` | API မခေါ်ဘဲ စမ်းသပ်ရန် |
| `TEMP_DIR` | job folder များ သိမ်းမယ့်နေရာ |

OAuth အတွက် Google Cloud Console ကနေ OAuth client (Desktop) ဖန်တီးပြီး
`client_secret.json` ကို repo root မှာ ထည့်ပါ။ ပထမဆုံး run မှာ browser ဖွင့်ပြီး
consent ပေးရမယ်၊ token ကို `youtube-oauth2.json` မှာ cache လုပ်တယ်
(နှစ်ဖိုင်လုံး `.gitignore` ထဲမှာ ပါပြီးသား).

## Job folder ရလဒ်များ

```
temp/job_x/
  story.json              # ဇာတ်လမ်း + အခန်း (ဇာတ်လမ်းအဆင့်က သိမ်း)
  story_metadata.json     # ② အနှစ်ချုပ်/အခန်း အချက်အလက်
  thumbnail_base.jpg      # ⑤ base ပုံ
  thumbnail.jpg           # ⑥ စာသားထပ်ပြီး (YouTube အတွက်)
  youtube_payload.json    # တင်မယ့် title/description/tags
  publish_result.json     # အဆင့်တိုင်း အောင်မြင်/မအောင်မြင် + upload ရလဒ်
  final.mp4               # ① ဗီဒီယို
```

## Test

```bash
pytest -q        # network/API မလိုပါ (offline mode မှာ run တယ်)
```
