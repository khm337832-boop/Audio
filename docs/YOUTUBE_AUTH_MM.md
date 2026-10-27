# YouTube တကယ်တင်နိုင်ရန် — အဆင့်လိုက် လမ်းညွှန် (မြန်မာ)

Bot က သင့် channel မှာ တင်ပေးနိုင်ဖို့ **တစ်ခါသာ** ဒီအဆင့်တွေ လုပ်ရပါမယ်။
ကြာချိန် ~၁၀ မိနစ်။ ကုဒ် မရေးရပါ။

> ✅ လုပ်ပြီးရင် ရမယ့်အရာ: `client_secret.json` (ဖိုင်) + `youtube-oauth2.json` (token)
> နောက်ပိုင်း bot က browser မလိုဘဲ တင်နိုင်မယ်။

---

## အဆင့် ၁ — Google Cloud project ဖန်တီး

1. <https://console.cloud.google.com> ကို သင့် YouTube channel ပိုင်တဲ့ **Gmail** နဲ့ ဝင်ပါ
2. အပေါ်ဘက် project dropdown → **New Project**
3. Project name: `audio-bot` (ဘာမဆို ရ) → **Create** → project အသစ်ကို ရွေးပါ

---

## အဆင့် ၂ — YouTube Data API v3 ကို ဖွင့်

1. ဘယ်ဘက် menu (☰) → **APIs & Services** → **Library**
2. ရှာကွက်မှာ `YouTube Data API v3` ရိုက်ပါ
3. **YouTube Data API v3** ကို နှိပ် → **Enable**

✅ “API Enabled” ပြရင် ရပါပြီ။

---

## အဆင့် ၃ — OAuth consent screen (ခွင့်ပြုချက် မျက်နှာပြင်)

1. **APIs & Services** → **OAuth consent screen**
2. User type: **External** → **Create**
3. ဖြည့်ရမယ့်အချက်များ
   - App name: `Audio Bot`
   - User support email: သင့် Gmail
   - Developer contact email: သင့် Gmail
   - **Save and Continue**
4. **Scopes** မျက်နှာပြင် — ဘာမှ မထည့်ဘဲ **Save and Continue**
5. **Test users** မျက်နှာပြင် — **+ Add users** → သင့် Gmail ကို ထည့် → **Save**

> ⚠️ ဒီအဆင့်ကို မလုပ်ရင် နောက်မှာ “Access blocked / app not verified” ဆိုတဲ့ အမှား ရနိုင်တယ်။
> App ကို “Testing” အခြေအနေမှာ ထားလို့ ရတယ် (publish လုပ်စရာ မလို)။

---

## အဆင့် ၄ — OAuth client (Desktop) ဖန်တီးပြီး ဖိုင် ဒေါင်းလုပ်

> 🆕 UI အသစ် (“Google Auth Platform”) မှာဆိုရင် လမ်းကြောင်းက —
> **Clients → Create client → Application type: Desktop app → Create**
> “OAuth client created” popup မှာ **Download JSON** ကို နှိပ်ပါ။
> ⚠️ အဲဒီ popup ကို ပိတ်လိုက်ရင် secret ကို ပြန်ကြည့်လို့ မရတော့ပါ — ပိတ်ခင် **Download JSON** အရင် နှိပ်ပါ။


1. **APIs & Services** → **Credentials**
2. အပေါ်က **+ Create credentials** → **OAuth client ID**
3. Application type: **Desktop app** ← (ဒါက အရေးကြီး)
4. Name: `audio-bot-desktop` → **Create**
5. Popup မှာ **Download JSON** ကို နှိပ်

ဒေါင်းလုပ်လာတဲ့ ဖိုင်နာမည်က `client_secret_1234…apps.googleusercontent.com.json` ဖြစ်ပါမယ်။
အဲဒါကို **`client_secret.json`** လို့ နာမည်ပြောင်းပြီး **ဒီ project folder ရဲ့ အပေါ်ဆုံး** (bot.py ရှိတဲ့နေရာ) မှာ ထည့်ပါ။

```
Audio/
├── bot.py
├── client_secret.json     ← ဒီမှာ ထည့်
├── .env
└── ...
```

> 🔒 ဒီဖိုင်က လျှို့ဝှက် — ဘယ်သူ့ကိုမှ မပို့ပါ၊ GitHub မတင်ပါ (`.gitignore` မှာ ပါပြီးသား)။

---

## ⚠️ ရှိပြီးသား client_secret.json က “Web application” ဖြစ်နေရင်

`client_secret.json` ထဲမှာ `"web"` လို့ ပါရင် (Desktop app မဟုတ်ဘဲ Web app ဖြစ်နေရင်)
အောက်က တစ်နည်းကို ရွေးပါ —

**နည်း ၁ — (အကြံပြု) Desktop client အသစ် ဖန်တီး** — အဆင့် ၄ အတိုင်း
`Application type: Desktop app` နဲ့ အသစ်ဖန်တီးပြီး `client_secret.json` ကို အစားထိုးပါ။
ဒါဆိုရင် ဘာမှ ထပ်ပြင်စရာ မလို။

**နည်း ၂ — ရှိပြီးသား Web client ကို ဆက်​သုံး**
1. Google Cloud → **Credentials** → သင့် OAuth client ကို နှိပ်
2. **Authorized redirect URIs** → **+ ADD URI** → `http://localhost:8085/` ထည့် → **Save**
3. Terminal မှာ `python main.py auth --manual` (သို့ `--redirect-uri http://localhost:8085/`)
4. `python main.py auth --status` နဲ့ အမျိုးအစား/redirect ကို စစ်နိုင်တယ်

> Web client မှာ redirect URI မထည့်ထားရင် `redirect_uri_mismatch` ဆိုတဲ့ အမှား ရမယ်။
> ဒီ bot က browser မလိုတဲ့ server ပေါ်မှာ run ရင် Desktop client + `--manual` က အလွယ်ဆုံးပါ။

---

## အဆင့် ၅ — token ယူ (terminal မှာ တစ်ခါ)

```bash
python main.py auth
```

ဖြစ်ပေါ်လာမယ့် အခြေအနေ —

**ကိစ္စ ၁ — browser အလိုအလျောက် ပွင့်တယ်**

1. Google account ရွေး (YouTube channel ပိုင်တဲ့ account)
2. “Google hasn’t verified this app” → **Advanced** → **Go to Audio Bot (unsafe)**
3. **Continue / Allow**
4. Terminal မှာ `✅ ချိတ်ဆက်ပြီး — channel: <သင့် channel>` ပြရင် ပြီးပါပြီ

**ကိစ္စ ၂ — browser မပွင့်ဘူး / server ပေါ်မှာ run နေတယ်**

```bash
python main.py auth --manual
```

- Terminal က link တစ်ခု ပြပါမယ် → အဲဒါကို ကိုယ့် browser (ဖုန်းလည်း ရ) မှာ ဖွင့်
- ခွင့်ပြုပြီးရင် `http://localhost:8085/?code=…` လိပ်စာနဲ့ page ပြပါမယ်
  (page မပေါ်ရင် address bar က **URL တစ်ခုလုံး** ကို copy)
- Terminal မှာ paste လုပ်ပြီး Enter

✅ အောင်မြင်ရင် `youtube-oauth2.json` ဖိုင် ဖြစ်လာပါမယ် — အဲဒါကို ထိန်းထားပါ၊ နောက်တစ်ခါ ပြန်လုပ်စရာ မလို။

---

## ဖုန်းပဲ ရှိတယ် / bot က server (Render, VPS) ပေါ်မှာ run နေတယ်

ဒီအခြေအနေမှာ `localhost` ကို bot ရှိတဲ့စက်က ပဲ မြင်နိုင်တာမို့ **paste-code နည်း** ကို သုံးပါ။

1. bot run နေတဲ့ စက် (သို့) သင့်ကွန်ပျူတာမှာ —

```bash
python main.py auth --manual
```

2. Terminal က ပြမယ့် **link ကို ဖုန်း browser မှာ ဖွင့်** → Google account ရွေး → Allow
3. ပြီးရင် `http://localhost:8085/?code=4/0A…` ဆိုတဲ့ page ကို “ဒီ site ကို မရောက်နိုင်ပါ” လို့ ပြပါမယ် —
   **စိတ်မပူပါ**၊ အဲဒီ page ရဲ့ **address bar က URL တစ်ခုလုံး** ကို copy လုပ်ပါ
4. Terminal မှာ paste → Enter → `✅ ချိတ်ဆက်ပြီး — channel: …`

> ကွန်ပျူတာမှာ `python main.py auth` (browser အလိုအလျောက်) run ပြီး ဖြစ်လာတဲ့
> `youtube-oauth2.json` ဖိုင်ကို server ဆီ copy လုပ်တာလည်း ရပါတယ်။

### ☁️ Cloud (Render/Railway/VPS) မှာ token မပျောက်အောင်

Server တွေမှာ ဖိုင် ပျက်တတ်တာမို့ token ကို **environment variable** အနေနဲ့ ထည့်ပါ:

```bash
python main.py auth --export-env
# 👇 ဒီလိုင်းကို hosting ရဲ့ Environment Variables မှာ ထည့်ပါ:
# YOUTUBE_TOKEN_JSON=eyJ0b2tlbiI6…
```

`YOUTUBE_TOKEN_JSON` ရှိရင် ဖိုင် မရှိလည်း bot က အဲဒီက token ကို သုံးတယ် (`--status` မှာ `token_source=env` ပြမယ်)။

## အဆင့် ၆ — စမ်းသပ်

```bash
python main.py auth --status        # token အခြေအနေ ကြည့်

# ဗီဒီယိုပြီးသားနဲ့ စမ်း (private နဲ့ တင်မယ်)
python main.py publish --job-dir temp/real_test --privacy private
```

YouTube Studio → **Content** မှာ ဗီဒီယို ပေါ်လာရင် အောင်မြင်ပါပြီ 🎉

---

## ပြဿနာ ဖြစ်ရင်

| အမှားစာသား | အကြောင်းရင်း / ဖြေရှင်းနည်း |
|---|---|
| `Access blocked: Authorization Error` | အဆင့် ၃.၅ (Test users) မှာ သင့် Gmail မထည့်ရသေး |
| `invalid_grant` / `Token has been expired or revoked` | `youtube-oauth2.json` ဖျက်ပြီး `python main.py auth` ပြန် run |
| `The request cannot be completed because you have exceeded your quota` | တစ်ရက် 10,000 units — upload ~1,600 units၊ ~၆ ခု/ရက်။ မနက်ဖန် ပြန်စမ်းပါ |
| `channel not found` | YouTube channel မရှိသေးလို့ — youtube.com → သင့်ပုံ → **Create a channel** |
| `client_secret.json မတွေ့ပါ` | ဖိုင်နာမည်/နေရာ မှန်၊ `.json` အတု မဖြစ်ရ (Edit → Save As → All files) |
| `redirect_uri_mismatch` | `client_secret.json` က Web client ဖြစ်နေတယ် — Google Console → Credentials → Authorized redirect URIs မှာ `http://localhost:8085/` ထည့်ပါ (သို့) Desktop client အသစ် ဖန်တီးပါ |
| အသံထွက် (အဆင့် ③) မရ | `pip install edge-tts` (အခမဲ့၊ key မလို) သို့ ElevenLabs key |

## လုံခြုံရေး

- `client_secret.json` နဲ့ `youtube-oauth2.json` ကို **မည်သူ့ကိုမှ မပို့ပါ**၊ GitHub မတင်ပါ
- Token ကို ရုပ်သိမ်းချင်ရင်: <https://myaccount.google.com/permissions> → Audio Bot → Remove access
- Quota/ခွင့်ပြုချက် စစ်ရန်: Google Cloud → **IAM & Admin** → **Quotas**
