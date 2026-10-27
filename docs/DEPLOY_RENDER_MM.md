# Render မှာ ဘယ်လို တင်မလဲ (မြန်မာ)

> **Deploy failed / Timed Out / “no open ports detected”** ဆိုတာ —
> Render က **web service** မှာ port တစ်ခု ဖွင့်ထားဖို့ လိုတယ်။
> `python bot.py` (polling ပဲ) က port မ​ဖွင့်လို့ deploy ကျတယ်။
> **ဖြေရှင်း:** Start command ကို **`python main.py serve`** ပြောင်းပါ။

---

## နည်း ၁ — Web Service (အခမဲ့ plan ရတယ်) ✅ အကြံပြု

1. Render → **New** → **Web Service** → သင့် repo ရွေး
2. **Build Command:** `pip install -r requirements.txt`
3. **Start Command:** `python main.py serve`
4. **Health Check Path:** `/healthz`
5. **Environment** မှာ ဒါတွေ ထည့် —

| Key | တန်ဖိုး |
|---|---|
| `BOT_TOKEN` | BotFather က token |
| `GEMINI_API_KEY` | Google AI Studio key |
| `GEMINI_MODEL` | `gemini-3.8-flash` (မရရင် `python main.py models` နဲ့ စစ်) |
| `TTS_PROVIDER` | `edge` (အခမဲ့) |
| `YOUTUBE_TOKEN_JSON` | ကွန်ပျူတာမှာ `python main.py auth --export-env` က output |
| `YOUTUBE_CHANNEL_HANDLE` | (optional) `airecapp` — channel မှန်/မမှန် စစ်ရန် |

6. Deploy ပြီးရင် log မှာ ဒီလို ပေါ်ရမယ် —

```
🌐 HTTP ဖွင့်ပြီး: 0.0.0.0:10000 (health: /healthz)
Bot @your_bot စတင်ပြီး (polling)
```

7. `https://<service>.onrender.com/healthz` → `ok` ပြ = deploy အောင်

> 📦 `render.yaml` ကို repo ထဲ ထည့်ထားတယ် — Render မှာ **Blueprint** နဲ့ ဆိုရင်
> တစ်ခါတည်း အလိုအလျောက် သတ်မှတ်ပြီးသား ဖြစ်မယ် (secret တွေ ကိုယ်တိုင် ဖြည့်ရုံ)။

### ⚠️ အခမဲ့ plan ရဲ့ ကန့်သတ်ချက်
- ၁၅ မိနစ်လောက် အလုပ်မရှိရင် **sleep** ဖြစ်တယ် (နောက် request က ၅၀ စက္ကန့်လောက် ကြာနိုင်)
- Bot polling က အလုပ်ရှိနေတာမို့ များသောအားဖြင့် နိုးနေတယ်၊ ဒါပေမယ့် အာမမခံနိုင်
- ၂၄ နာရီ သေချာလိုရင် — **Starter plan** ယူပါ (သို့) cron-job.org နဲ့ ၁၀ မိနစ်တစ်ခါ
  `https://<service>.onrender.com/healthz` ကို ping လုပ်ပါ
- **Disk က ယာယီ** — restart ရင် `temp/` ပျက်တယ် (ဗီဒီယို ပြီးတာနဲ့ YouTube တင်လို့ ပြဿနာ မရှိ)

---

## နည်း ၂ — Background Worker (Disk မလို၊ port မလို)

- **Start Command:** `python main.py bot`
- plan က paid ဖြစ်နိုင်တယ်; worker က port မ​လိုပါ
- log က Render dashboard → Logs မှာ ကြည့်

---

## Deploy မအောင်ရင် ဖတ်ရန်

| Log မှာ ပြရင် | အကြောင်းရင်း | ဖြေရှင်း |
|---|---|---|
| `No open ports detected` / `Port scan timeout` | port မ​ဖွင့်ထား | Start command → `python main.py serve` |
| `Timed Out` (၁၅ မိနစ်ကျော်) | health check မ​ဖြေဘူး | Health check path = `/healthz` |
| `ModuleNotFoundError` | requirements မပြည့် | Build command စစ် (`pip install -r requirements.txt`) |
| `Instance restarted` ထပ်ခါ | crash → restart loop | Logs ထဲက traceback ကြည့် (`Config` / token) |
| `404 NOT_FOUND ... model ... no longer available` | Gemini model အဟောင်း | `GEMINI_MODEL=gemini-3.8-flash` (သို့) `python main.py models` |
| `Conflict` | အခြားနေရာ (ကွန်ပျူတာ) မှာ bot run နေတယ် | ကွန်ပျူတာက bot ကို ပိတ်ပါ — တစ်နေရာတည်း run ပါ |
| story က ၇၀၀ စာလုံးလောက်ပဲ | Gemini မခေါ်နိုင်လို့ offline fallback | key/model စစ် → `python main.py models` |

---

## Secret တွေ ဘယ်လို ထည့်မလဲ

- **Render → Environment → Add Environment Variable**
- `client_secret.json` / `youtube-oauth2.json` ကို **repo ထဲ မ​တင်ပါ**
- cloud အတွက် token ကို env နဲ့ —
  1. ကွန်ပျူတာမှာ `python main.py auth` (တစ်ခါ)
  2. `python main.py auth --export-env` → `YOUTUBE_TOKEN_JSON=...` လိုင်း ရမယ်
  3. အဲဒီလိုင်းကို Render env မှာ ထည့် (ကွန်ပျူတာကို format ချ/ဖျက်လည်း token မပျောက်)
- `client_secret.json` ရဲ့ အခြေအနေကို `python main.py doctor` နဲ့ စစ်နိုင်တယ် (secret မ​ပါ)

---

## Bot က local မှာလည်း run ချင်ရင်

```bash
python main.py bot          # polling (port မလို)
python main.py serve        # local web + bot (http://localhost:8080/healthz)
```

⚠️ **တစ်ချိန်တည်း ၂ နေရာ မ​runပါ** — Render မှာ run နေရင် ကွန်ပျူတာက bot ကို ပိတ်ထားပါ
(မဟုတ်ရင် `Conflict` ဖြစ်ပြီး တစ်ဖက်က ရပ်သွားမယ်)။
