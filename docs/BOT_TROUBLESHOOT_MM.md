# Bot ရပ်သွားရင် ဘယ်လို ပြန်စရမလဲ (မြန်မာ)

> **အမြန်:** `python main.py bot` ကို run ပါ။
> Token/webhook ကို အရင်စစ်ပြီး၊ error ဖြစ်ရင် အကြောင်းရင်းကို မြန်မာလို ပြပါမယ်။

---

## အဆင့် ၁ — ဘာကြောင့် ရပ်တာလဲ ကြည့်

```bash
python main.py bot --check     # token + webhook စစ် (bot မ runဘူး)
```

ရလဒ် ကောင်းရင် —

```
✅ Token မှန်တယ် — @your_bot (id 123456789)
✅ Webhook မရှိပါ (polling အတွက် ကောင်းတယ်)
```

ရလဒ် မကောင်းရင် အောက်က ဇယားမှာ ရှာပါ။

## အဆင့် ၂ — log ဖတ်

Bot က `temp/bot.log` မှာ log ရေးထားတယ် (2MB × ၃ ဖိုင် ထိ သိမ်း)။

```bash
# Windows
type temp\bot.log

# macOS / Linux — နောက်ဆုံး ၄၀ ကြောင်း
tail -40 temp/bot.log
```

`ERROR` / `Traceback` ပါတဲ့ ကြောင်းတွေက အကြောင်းရင်းပါ။
**ဒီ log ကို ကူးပို့နိုင်တယ်** — token/key မပါပါ (mask လုပ်ထားတယ်)။

## အဆင့် ၃ — ပြန် run

```bash
python main.py bot
```

`python main.py bot` က **auto-restart** ပါဝဲ့ — ကွန်ရက် ပြတ်ရင် ၅/၁၀/၂၀… စက္ကန့် စောင့်ပြီး
အလိုလို ပြန်စပါတယ်။ ရပ်ချင်ရင် **Ctrl+C**။

| Command | လုပ်တာ |
|---|---|
| `python main.py bot` | စစ်ဆေးပြီး run + ရပ်ရင် ပြန်စ |
| `python main.py bot --check` | စစ်ဆေးရုံပဲ |
| `python main.py bot --no-restart` | error ရင် မပြန်စဘဲ ထွက် (အကြောင်းရင်း ရှာရန်) |
| `python main.py bot --log-file my.log` | log နေရာ ပြောင်း |

---

## အကြောင်းရင်း ဇယား

| ပြရင် | အကြောင်းရင်း | ဖြေရှင်းနည်း |
|---|---|---|
| `❌ BOT_TOKEN မရှိပါ` | `.env` မှာ token မ​ထည့်ရသေး (သို့) `.env` ကို bot.py ရှိတဲ့ folder မှာ မထားမိ | `.env` ဖိုင် (ဥပမာ `C:\Users\You\Audio\.env`) ထဲ `BOT_TOKEN=123456789:AAF...` ထည့် |
| `BOT_TOKEN ပုံစံ မမှန်ပါ` | token ကို တစ်ပိုင်းတစ်စ ကူးမိ / ကွက်လပ် ပါ | BotFather → `/mybots` → bot → **API Token** → အတိအကျ copy |
| `❌ Token မှားနေတယ်` | token ကို revoke လုပ်ထား / အဟောင်း | BotFather မှာ **Revoke** လုပ်ပြီး token အသစ်ယူ → `.env` အစားထိုး |
| `❌ အခြား bot instance တစ်ခု run နေတယ်` | တူတူ token နဲ့ ၂ နေရာ run နေ (terminal ၂ ခု / Render / ဖုန်း) | အရင်တစ်ခုကို ပိတ် (Ctrl+C)၊ PC restart၊ Render ဆိုရင် service ကို suspend |
| `❌ Telegram API ကို မချိတ်နိုင်ပါ` | အင်တာနက် မရ / VPN / firewall | အင်တာနက် စစ်၊ VPN ပိတ်ကြည့်၊ ကုမ္ပဏီ/ကျောင်း network ဆိုရင် mobile hotspot စမ်း |
| `⚠️ ကွန်ရက် error … ပြန်ကြိုးစားမယ်` | ခေတ္တ ပြတ် (Wi‑Fi လှုပ်) | ဘာမှ မလုပ်ပါ — အလိုလို ပြန်စမယ် |
| Terminal ပိတ်လိုက်တာ / PC sleep | bot process က သေသွား | `python main.py bot` ပြန် run၊ PC ကို sleep မ​ဖြစ်အောင် ထား |
| `Conflict` + webhook ရှိ | အခြားနေရာက webhook သတ်မှတ်ထား | `python main.py bot` က webhook ကို အလိုလို ဖျက်ပေးတယ် |
| `handler မှာ error ဖြစ်တယ်` | တစ်ချက် command မှာ error — bot က ဆက်အလုပ်လုပ်တယ် | log ထဲက traceback ကို ပို့ပါ |
| Render: `No open ports detected` / `Timed Out` | web service မှာ port မ​ဖွင့်ထား | start command → `python main.py serve` ([DEPLOY_RENDER_MM.md](DEPLOY_RENDER_MM.md)) |
| `404 NOT_FOUND ... model ... no longer available` | Gemini model အဟောင်း | `python main.py models` → `GEMINI_MODEL` အသစ် |
| `python: can't open file 'bot.py'` | folder မှားနေတယ် | `cd` နဲ့ `bot.py` ရှိတဲ့ folder ထဲ ဝင်ပါ |

---

## Bot ကို ၂၄ နာရီ ဆက်အလုပ်လုပ်စေချင်ရင်

PC ပိတ်ရင် bot လည်း ရပ်တယ်။ ဆက်လုပ်စေချင်ရင် —

**ကွန်ပျူတာ (Windows)**
```bat
python main.py bot
```
— ဒီ window ကို ပိတ်မထားပါနဲ့။ (ဒါမှမဟုတ် `pythonw` နဲ့ background run)

**Server (Render / VPS)**
- Start command: `python main.py bot`
- လိုအပ်တဲ့ env: `BOT_TOKEN`, `GEMINI_API_KEY`, `YOUTUBE_TOKEN_JSON` (auth --export-env က output)
- Bot ကို **တစ်နေရာတည်း** မှာပဲ run ပါ (PC နဲ့ server နှစ်ခု တစ်ချိန်တည်း မ​runပါ)

---

## ရှာမတွေ့ရင် ပို့ရန် (secret မပါ)

```bash
python main.py doctor
```

```
bot_token=set gemini_key=set client_secret=set oauth_token=yes ffmpeg=yes ...
```

ဒါနဲ့ `temp/bot.log` ရဲ့ နောက်ဆုံး ၄၀ ကြောင်း ကို ပို့ပါ။
**`BOT_TOKEN` တန်ဖိုး၊ `client_secret`၊ `youtube-oauth2.json` ကို chat မှာ မ​ပို့ပါ။**
