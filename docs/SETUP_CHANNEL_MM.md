# client_secret.json ထည့်ခြင်း → Channel ချိတ်ဆက်ခြင်း (အဆင့်ဆင့်)

သင်က `.env` မှာ `BOT_TOKEN` နဲ့ `GEMINI_API_KEY` ထည့်ပြီးသား ဖြစ်တယ်။ ကျန်တာ —
**YouTube ချိတ်ဆက်ခြင်း** တစ်ခုတည်း။ ဒီစာရွက်စာတမ်းက အဲဒါကို အဆင့် ၇ ဆင့်နဲ့
အဆုံးထိ လုပ်နိုင်အောင် ရေးထားတယ်။ မိနစ် ~၁၀ ကြာမယ်။

> လိုအပ်တာ: ကွန်ပျူတာ (သို့) ဖုန်း + သင့် YouTube channel ပိုင်တဲ့ Gmail

---

> 🚫 **Search Console (Insights) နဲ့ မချိတ်ပါ** — အဲဒါက Google Search မှာ သင့် Page/ဗီဒီယို
> ဘယ်လောက် ပေါ်လဲ ကြည့်တဲ့ နေရာပါ။ ဗီဒီယို တင်ဖို့ လိုတာက **OAuth client JSON** တစ်ခုတည်း။
> Search Console ကို ch ချိတ်စရာ မလိုပါ (ချိတ်ထားလည်း ဘာမှ ထပ်မလုပ်ရပါ)။

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

## အဆင့် ၃ — JSON ကို နေရာချ (နည်း ၃ မျိုး — တစ်ခု ရွေးပါ)

ဒေါင်းလုပ်လုပ်ထားတဲ့ ဖိုင်နာမည်က ရှည်တယ် —
`client_secret_449998066874_16u8bic572b21ek1acu8gdht8hsecfqa_apps.json`

ဒါကို **`client_secret.json`** နာမည်နဲ့ **`bot.py` ရှိတဲ့ folder ထဲ** ထည့်ရမယ်။
အောက်က နည်း ၃ မျိုးထဲက သင့်အခြေအနေနဲ့ ကိုက်တာကို ရွေးပါ။

### 🟢 နည်း A — command တစ်ကြောင်းတည်း (အကြံပြု)

**Windows (Command Prompt / PowerShell)**

```bat
cd %USERPROFILE%\Audio
python main.py auth --import-file "%USERPROFILE%\Downloads\client_secret_449998066874_16u8bic572b21ek1acu8gdht8hsecfqa_apps.json"
```

**macOS / Linux**

```bash
cd ~/Audio
python main.py auth --import-file ~/Downloads/client_secret_449998066874_16u8bic572b21ek1acu8gdht8hsecfqa_apps.json
```

> 💡 ဖိုင်လမ်းကြောင်း မသေချာရင် — `Downloads` folder ထဲမှာ ဖိုင်ကို နှိပ်ပြီး
> “Copy path / လမ်းကြောင်း ကူးယူ” ကို သုံးပါ။ Windows မှာ `Shift + Right click` → “Copy as path”
> က လမ်းကြောင်းကို `"…"` အုပ်ပြီး ကူးပေးတယ်။

အောင်ရင် —

```
✅ ထည့်ပြီး: …/Audio/client_secret.json
   အမျိုးအစား: installed | project: myyoutubebot-512616
👉 နောက်တစ်ဆင့်: python main.py auth
```

### 🔵 နည်း B — JSON စာသားကို paste (ဖိုင် ရှာမတွေ့ရင်)

1. Downloads ထဲက အဲဒီ `.json` ဖိုင်ကို **Notepad / VS Code / TextEdit** နဲ့ ဖွင့်
2. စာသားအားလုံး ကို select all → copy (`{` နဲ့ စပြီး `}` နဲ့ ဆုံးတယ်)
3. Terminal မှာ —

```bash
python main.py auth --paste-secret
```

4. JSON ကို paste လုပ် → Enter → **Ctrl+D** (`Windows: Ctrl+Z ပြီး Enter`)

```
✅ သိမ်းပြီး: …/Audio/client_secret.json
   အမျိုးအစား: installed
```

### 🟡 နည်း C — File Manager နဲ့ ကိုယ်တိုင်

1. `Downloads` ထဲမှာ ဖိုင်ကို ရှာ → **Rename** → `client_secret.json`
   *(Windows မှာ “file name extensions” ပြထားဖို့ လိုတယ် — မဟုတ်ရင် `client_secret.json.txt` ဖြစ်သွားနိုင်)*
2. **Copy** → `Audio` folder (bot.py ရှိတဲ့နေရာ) ထဲ **Paste**
3. စစ် —

```bash
python main.py auth --status
```

### ✅ စစ်ဆေး (ဘယ်နည်းနဲ့ ထည့်ထည့်)

```bash
python main.py auth --status
```

```
client_secret.json: ✅ ရှိ  (C:\Users\You\Audio\client_secret.json)
  အမျိုးအစား: installed  project: myyoutubebot-512616
  redirect URIs: http://localhost
youtube-oauth2.json: ❌ မရှိ          ← ဒါက အဆင့် ၄ မှာ ဖြစ်လာမယ်
```

| ပြရင် | ဘာလုပ်မလဲ |
|---|---|
| `installed` | ✅ အကောင်းဆုံး — အဆင့် ၄ ဆက်သွား |
| `web` | ⚠️ `http://localhost:8085/` ကို Console → Authorized redirect URIs မှာ ထည့် (သို့) Desktop client အသစ် |
| `❌ မရှိ` | နေရာ/နာမည် မှန်း​ကြောင်း ပြန်စစ် (`client_secret.json.txt` ဖြစ်နေလား) |

> 🔒 ဒီဖိုင်က လျှို့ဝှက် — chat မှာ မ​ပို့ပါ၊ GitHub မ​တင်ပါ (`.gitignore` မှာ ပါပြီးသား)။

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
   နာမည်: သင့် Channel  (@airecapp)
   Channel ID: UCxxxxxxxxxxxxxxxxxxxxxx
   Subscribers: 1,234 | Videos: 56
   တင်မယ့် privacy: private (24 = Entertainment)
```

`(@handle)` ကို ကြည့်ပြီး **သင့် channel ဟုတ်မဟုတ်** အတည်ပြုပါ။
handle တိတိကျကျ စစ်ချင်ရင် `.env` မှာ ဒါကို ထည့်ထားနိုင်တယ် —

```
YOUTUBE_CHANNEL_HANDLE=airecapp
```

မှားတဲ့ channel ဆိုရင် ⚠️ သတိပေးပြီး ဘာလုပ်ရမလဲ ပြပါမယ်။

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
python main.py bot
```

`python main.py bot` က token/webhook ကို အရင်စစ်ပြီး၊ ကွန်ရက် ပြတ်ရင် အလိုလို ပြန်စပါတယ်။
Bot ရပ်သွားရင် → [`BOT_TROUBLESHOOT_MM.md`](BOT_TROUBLESHOOT_MM.md) (log: `temp/bot.log`)
Render/cloud မှာ တင်ရင် → [`DEPLOY_RENDER_MM.md`](DEPLOY_RENDER_MM.md) (`python main.py serve`)

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
| `accessNotConfigured` / `YouTube Data API has not been used` | Google Cloud → project ရွေး → APIs & Services → Library → **YouTube Data API v3** → **Enable** → ၂-၅ မိနစ် စောင့် |
| token ကို server ကို ပို့ချင်တယ် | `python main.py auth --export-env` → hosting ရဲ့ env မှာ `YOUTUBE_TOKEN_JSON` ထည့် |

တစ်ချက်ချင်း စစ်ချင်ရင် — `python main.py doctor` (secrets မပါဘဲ အခြေအနေ ပြ)။
