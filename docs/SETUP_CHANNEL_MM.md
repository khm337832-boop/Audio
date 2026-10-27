# client_secret.json ထည့်ခြင်း → Channel ချိတ်ဆက်ခြင်း (အဆင့်ဆင့်)

သင်က `.env` မှာ `BOT_TOKEN` နဲ့ `GEMINI_API_KEY` ထည့်ပြီးသား ဖြစ်တယ်။ ကျန်တာ —
**YouTube ချိတ်ဆက်ခြင်း** တစ်ခုတည်း။ ဒီစာရွက်စာတမ်းက အဲဒါကို အဆင့် ၇ ဆင့်နဲ့
အဆုံးထိ လုပ်နိုင်အောင် ရေးထားတယ်။ မိနစ် ~၁၀ ကြာမယ်။

> လိုအပ်တာ: ကွန်ပျူတာ (သို့) ဖုန်း + သင့် YouTube channel ပိုင်တဲ့ Gmail

---

## အဆင့် ၀ — ဖိုင်တွေ နေရာမှန် ရှိမရှိ စစ်

Terminal ကို `Audio` folder ထဲ ဖွင့်ပြီး —

```bash
python main.py doctor
```

ဒီလို ပြရမယ် (`set` / `present` ဖြစ်နေရမယ်):

```
bot_token=set
gemini_key=set
client_secret=missing        ← ဒါကို ဖြည့်ရမယ်
oauth_token=no               ← ပြီးရင် yes ဖြစ်ရမယ်
tts_providers=edge,gtts
ffmpeg=yes
```

`bot_token=missing` ဆိုရင် `.env` ဖိုင် `bot.py` နဲ့ **folder တူတူ** ထဲ ရှိမရှိ စစ်ပါ။

---

## အဆင့် ၁ — OAuth client JSON ကို ဒေါင်းလုပ်

သင့် screenshot မှာ “OAuth client created” popup ပေါ်နေတယ်။

1. အဲဒီ popup မှာ **⬇ Download JSON** ကို နှိပ်
   *(popup ပိတ်သွားပြီးသားဆိုရင် — Google Auth Platform → **Clients** → သင့် client ကို နှိပ် →
   `Download JSON` ရနိုင်တယ်။ မရတော့ရင် client အသစ် ဖန်တီး: **Create client → Desktop app**)*
2. ဒေါင်းလုပ်လာတဲ့ ဖိုင်နာမည်က `client_secret_1234…apps.googleusercontent.com.json` ဖြစ်မယ်

---

## အဆင့် ၂ — Test users ထည့် (မဖြစ်မနေ)

screenshot မှာ “OAuth access is restricted to the test users” လို့ ပြတယ်။

1. Google Auth Platform → **Audience** (သို့ OAuth consent screen)
2. **Test users** → **+ Add users** → သင့် Gmail ရိုက်ထည့် → **Save**
3. App status က **Testing** ဖြစ်နေတာ ကောင်းတယ် (publish လုပ်စရာ မလို)

> ဒီအဆင့် မ​လုပ်ရင် → `Access blocked: Authorization Error` ဆိုတဲ့ အမှား ရမယ်။

---

## အဆင့် ၃ — ဖိုင်ကို နေရာချ (rename မလိုဘဲ)

```bash
python main.py auth --import-file "C:\Users\You\Downloads\client_secret_1234....json"
# macOS/Linux: python main.py auth --import-file ~/Downloads/client_secret_1234....json
```

ဒီ command က ဖိုင်ကို စစ်ပြီး `client_secret.json` အဖြစ် **အလိုအလျောက် ကူးထည့်**ပေးတယ်။

```
✅ ထည့်ပြီး: /…/Audio/client_secret.json
   အမျိုးအစား: installed | project: myyoutubebot-512616

👉 နောက်တစ်ဆင့်: python main.py auth
```

**`အမျိုးအစား`** က —
- `installed` ✅ = Desktop app (အကောင်းဆုံး)
- `web` ⚠️ = Web app → `http://localhost:8085/` ကို Google Console ရဲ့
  **Authorized redirect URIs** မှာ ထည့်ရမယ်

```bash
python main.py auth --status     # စစ်ချင်ရင်
```

---

## အဆင့် ၄ — Google ခွင့်ပြုချက် ယူ (token)

**ကိစ္စ A — ကွန်ပျူတာမှာ run (browser ပါ)**

```bash
python main.py auth
```

1. Browser အလိုအလျောက် ပွင့်လာမယ်
2. **အကောင့် ရွေး** ← ဒါ အရေးကြီး
   - သင့် channel က **Brand Account** (channel နာမည်နဲ့ အကောင့်) ဆိုရင်
     account chooser မှာ **အဲဒီ channel နာမည်နဲ့ အကောင့်** ကို ရွေးပါ
     (ကိုယ်ပိုင် Gmail ကို ရွေးရင် ဗီဒီယိုက ကိုယ်ပိုင် channel ဆီ ရောက်မယ်)
3. “Google hasn’t verified this app” → **Advanced** → **Go to … (unsafe)**
4. **Continue / Allow**
5. Terminal မှာ —

```
✅ ချိတ်ဆက်ပြီး — channel: သင့် Channel နာမည် (subscribers: …)
🔑 token: /…/Audio/youtube-oauth2.json
```

**ကိစ္စ B — ဖုန်းပဲ ရှိတယ် / server ပေါ်မှာ run**

```bash
python main.py auth --manual
```

1. Terminal က **link** ကို ဖုန်း browser မှာ ဖွင့် → အကောင့်ရွေး → Allow
2. `http://localhost:8085/?code=4/0A…` page က “site မရောက်နိုင်ပါ” လို့ ပြတာက **ပုံမှန်**
3. အဲဒီ page ရဲ့ **address bar က URL တစ်ခုလုံး** ကို copy
4. Terminal မှာ paste → Enter

> ဒီ token (`youtube-oauth2.json`) ကို **မည်သူ့ကိုမှ မ​ပို့ပါ**။

---

## အဆင့် ၅ — Channel မှန်/မမှန် စစ်

```bash
python main.py channel
```

```
✅ Channel ချိတ်ဆက်ပြီး
   နာမည်: သင့် Channel
   Channel ID: UCxxxxxxxxxxxxxxxxxxxxxx
   Subscribers: 1,234 | Videos: 56
   တင်မယ့် privacy: private (24 = Entertainment)
```

- **နာမည် မှားနေရင်** → `youtube-oauth2.json` ဖျက်ပြီး `python main.py auth` ကို ပြန် run
  (အဆင့် ၄ က အကောင့်ရွေးတာမှာ channel မှန်တာကို ရွေး)
- **channel မတွေ့ပါ** ဆိုရင် → youtube.com → သင့်ပုံ → **Create a channel** → ပြီးရင် `auth` ပြန် run

---

## အဆင့် ၆ — စမ်းတင် (private)

```bash
python main.py publish --job-dir temp/verify --privacy private
```

- YouTube Studio → **Content** မှာ ဗီဒီယို ပေါ်လာရင် ✅ (thumbnail ပါ တင်ပြီးသား)
- ဖျက်ချင်ရင် Studio ထဲကနေ Delete လုပ်နိုင်တယ်
- quota: တစ်ရက် 10,000 units — upload တစ်ခု ~1,600 units ≈ **၆ ခု/ရက်**

---

## အဆင့် ၇ — Bot စတင်

```bash
python bot.py
```

Telegram မှာ `/start` → **🚀 ဇာတ်လမ်းဖန်တီးပြီး YouTube တင်မယ်** →
အကြောင်းအရာ ရိုက်ထည့် (သို့ ကျော်) → အဆင့် ①–⑧ အလိုအလျောက် လုပ်ပြီး **link ပြန်ပို့**မယ်။

---

## အမှား ဖြစ်ရင် ဘယ်လို ဖြေရှင်းမလဲ

| အမှားစာသား | ဖြေရှင်းနည်း |
|---|---|
| `client_secret.json မတွေ့ပါ` | အဆင့် ၃ (`--import-file`) ကို ပြန် run |
| `Access blocked: Authorization Error` | အဆင့် ၂ — Test users မှာ သင့် Gmail ထည့် |
| `redirect_uri_mismatch` | client က Web ဖြစ်နေတယ် → `http://localhost:8085/` ထည့် (သို့) Desktop client အသစ် |
| `invalid_grant` / `Token has been expired or revoked` | `youtube-oauth2.json` ဖျက် → `python main.py auth` ပြန် |
| `quota exceeded` | မနက်ဖန် ပြန်စမ်း (တစ်ရက် ~၆ ခု) |
| `channel not found` | youtube.com → Create a channel → `auth` ပြန် run |
| Browser မ​ပွင့်ဘူး | `python main.py auth --manual` |
| token ကို server ကို ပို့ချင်တယ် | `python main.py auth --export-env` → hosting ရဲ့ env မှာ `YOUTUBE_TOKEN_JSON` ထည့် |

တစ်ချက်ချင်း စစ်ချင်ရင် — `python main.py doctor` (secrets မပါဘဲ အခြေအနေ ပြ)။
