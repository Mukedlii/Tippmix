# ⚙️ GitHub Secrets Beállítás

## Áttekintés

A bot futásához GitHub Secrets-ben kell tárolni az API kulcsokat.

## Kötelező Secrets

### 1. Telegram Bot Token

**Secret neve:** `TELEGRAM_BOT_TOKEN`

**Érték:** Bot token BotFather-től (pl. `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`)

**Megszerzés:**
1. Telegram → keress: @BotFather
2. `/newbot`
3. Bot név megadása
4. Másold ki a tokent

---

### 2. Telegram Chat ID-k

**Secret neve:** `TELEGRAM_PUBLIC_CHAT_ID`

**Érték:** FREE csatorna/csoport ID (pl. `-1001234567890`)

**Secret neve:** `TELEGRAM_VIP_CHAT_ID`

**Érték:** VIP csatorna/csoport ID

**Megszerzés:**
1. Add hozzá a botot a csatornához (admin joggal)
2. Küldj egy üzenetet a csatornába
3. Látogass el: `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. Keresd meg: `"chat":{"id":-1001234567890}`

---

### 3. TheOddsAPI Key (Odds lekéréshez)

**Secret neve:** `ODDS_API_KEY`

**Érték:** `<your_odds_api_key>`

**Megszerzés:**
1. https://the-odds-api.com/
2. Sign up (ingyen 500 req/hó)
3. API key másolása

**Fontos:** Free tier = 500 request/hó → ~25 request/nap

---

### 4. OpenAI API Key (Opcionális - AI tippekhez)

**Secret neve:** `OPENAI_API_KEY`

**Érték:** OpenAI API kulcs (`sk-...` kezdetű, NEM `sk-proj-...`)

**Megszerzés:**
1. https://platform.openai.com/api-keys
2. Create new secret key
3. **Service account** fül (NEM project key)
4. Top up credits ($5-10)

**Alternatíva:** Poisson engine (nincs AI, matematikai/statisztikai)

---

## Secrets Beállítása

### GitHub UI-n keresztül:

1. Menj: `https://github.com/Mukedlii/Tippmix/settings/secrets/actions`
2. Kattints: **"New repository secret"**
3. Name: `TELEGRAM_BOT_TOKEN`
4. Secret: `<másold be a token-t>`
5. **Add secret**

Ismételd meg minden secret-tel (TELEGRAM_PUBLIC_CHAT_ID, TELEGRAM_VIP_CHAT_ID, ODDS_API_KEY, OPENAI_API_KEY).

---

### GitHub CLI-vel (gyorsabb):

```bash
gh secret set TELEGRAM_BOT_TOKEN --body "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
gh secret set TELEGRAM_PUBLIC_CHAT_ID --body "-1001234567890"
gh secret set TELEGRAM_VIP_CHAT_ID --body "-1009876543210"
gh secret set ODDS_API_KEY --body "<your_odds_api_key>"
gh secret set OPENAI_API_KEY --body "sk-..."
```

---

## Secrets Ellenőrzése

GitHub Secrets nem olvashatóak vissza, de ellenőrizheted hogy be vannak-e állítva:

```bash
gh secret list
```

Expected output:
```
ODDS_API_KEY           Updated 2026-03-19
OPENAI_API_KEY         Updated 2026-03-19
TELEGRAM_BOT_TOKEN     Updated 2026-03-19
TELEGRAM_PUBLIC_CHAT_ID Updated 2026-03-19
TELEGRAM_VIP_CHAT_ID    Updated 2026-03-19
```

---

## Tesztelés

Manuális workflow futtatás:

1. GitHub repo → **Actions** tab
2. Kattints: **Tippmix Morning Full-Day Picks**
3. **Run workflow** dropdown
4. Válassz branch: `main`
5. **Run workflow** gomb

Várj 2-3 percet, majd check a Telegram csatornát → üzenetnek kell érkeznie.

---

## Troubleshooting

### "No secrets found" error

→ Secrets csak akkor látszanak, ha be vannak állítva. Ellenőrizd:
https://github.com/Mukedlii/Tippmix/settings/secrets/actions

### "Insufficient quota" (OpenAI)

→ Top up OpenAI credits: https://platform.openai.com/settings/organization/billing/overview

Minimum $5 ajánlott.

### "Telegram error: Unauthorized"

→ Rossz `TELEGRAM_BOT_TOKEN`. Generálj új bot-ot BotFather-rel, vagy check hogy jól másoltad-e.

### "Chat not found"

→ Rossz `TELEGRAM_PUBLIC_CHAT_ID` vagy `TELEGRAM_VIP_CHAT_ID`. Ellenőrizd:
- Bot admin-e a csatornában?
- Chat ID `-` jellel kezdődik? (csoportok/csatornák negatív ID-t kapnak)

---

## Költségek

| Service | Free Tier | Költség utána |
|---------|-----------|---------------|
| Telegram | Ingyenes ✅ | $0 |
| GitHub Actions | 2000 perc/hó ✅ | $0.008/perc |
| TheOddsAPI | 500 req/hó ✅ | $0.01/req |
| OpenAI (GPT-4o-mini) | - | ~$0.15/1M token |
| Poisson engine | Ingyenes ✅ | $0 |

**Ajánlott:** Poisson engine (ingyenes) + TheOddsAPI (500 req/hó ingyen)

**Költség:** $0/hó (GitHub Actions free tier elég)

---

**Frissítve:** 2026-03-19
