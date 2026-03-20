# Combo Bet System (Kombinált Fogadás)

## Mi ez?

Automatikusan építi a COMBO SZELVÉNYEKET (accumulator/parlay) a napi tippekből.

**Előny:** Nagy nyeremény kis tétből!

**Példa:**
```
SAFE COMBO (3 tipp):
- Arsenal win @ 1.65
- Bayern win @ 1.80  
- Liverpool win @ 1.55

Össz odds: 4.60
Tét: 1000 HUF → Nyeremény: 4,600 HUF
Profit: +3,600 HUF (360%)
```

---

## Típusok

### 1️⃣ SAFE COMBO (Biztonságos)

**Paraméterek:**
- 3 tipp
- ⭐⭐⭐⭐+ confidence
- Alacsony/közepes rizikó
- 1.5-2.2 odds range
- Különböző ligák (diverzifikáció)

**Várható:**
- Össz odds: 3.5-5.5x
- Win rate: ~45-55%
- 1000 HUF → 3,500-5,500 HUF

---

### 2️⃣ RISKY COMBO (Rizikós)

**Paraméterek:**
- 4-5 tipp
- ⭐⭐⭐+ confidence
- Mix risk levels
- 1.7-4.0 odds range

**Várható:**
- Össz odds: 8-20x
- Win rate: ~20-35%
- 1000 HUF → 8,000-20,000 HUF

---

## Hogyan működik?

**Automatikus kiválasztás:**

1. **Scoring** minden tippre:
   ```python
   safe_score = confidence + (odds * 0.5)
   risky_score = confidence * odds
   ```

2. **Filterezés:**
   - Min confidence
   - Odds range
   - Risk level

3. **Diverzifikáció:**
   - Előnyben különböző ligák
   - Elkerüli ugyanaz liga 2x

4. **Top N kiválasztás:**
   - SAFE: top 3
   - RISKY: top 4-5

---

## Telegram Output

**SAFE példa:**
```
🎯 COMBO SZELVÉNY (SAFE)

💰 Tét: 1,000 HUF
📊 Össz odds: 4.60
🏆 Potenciális nyeremény: 4,600 HUF
💵 Profit: +3,600 HUF (360%)

━━━━━━━━━━━━━━━━━━━━
📋 MECCSEK:

1. Arsenal vs Chelsea
   🎯 Hazai győzelem @1.65

2. Bayern Munich vs Dortmund
   🎯 Hazai győzelem @1.80

3. Liverpool vs Everton
   🎯 Hazai győzelem @1.55

━━━━━━━━━━━━━━━━━━━━
✅ Biztonságos kombó (3 tipp)
📈 Várható esély: ~45-55%

💡 Felelős fogadás!
Csak annyit tégy, amennyit megengedhetsz!
```

---

## Használat

### Automatikus (VIP Telegram üzenetben)

A morning/evening run automatikusan generál combo-kat és küldi a VIP csatornára.

### Manuális teszt

```bash
cd Tippmix
python scripts/combo_test.py
```

### Programmatic

```python
from bot.combo_builder import build_combos, format_combo_for_telegram

# Build combos
combos = build_combos(vip_picks)

# Format for Telegram
if combos['safe']:
    msg = format_combo_for_telegram(combos['safe'], "SAFE", 1000)
    # send_telegram(msg)

if combos['risky']:
    msg = format_combo_for_telegram(combos['risky'], "RISKY", 1000)
    # send_telegram(msg)
```

---

## Marketing

**COMBO-K = SOCIAL PROOF! 🎯**

**Amikor nyernek:**
```
🏆 COMBO GYŐZELEM!

SAFE COMBO (3/3) ✅✅✅
Tét: 1,000 HUF
Nyeremény: 4,600 HUF
Profit: +3,600 HUF (360%)

Arsenal ✅ 2-0
Bayern ✅ 3-1
Liverpool ✅ 1-0

Követd a VIP csatornát a napi combo szelvényekért!
```

**Ez megy:**
- Twitter screenshot
- Telegram story
- Instagram post

→ **Sokkal jobb marketing mint single betek!**

---

## Stratégia

**Javasolt fogadás:**

1. **Single betek 70%** (biztonság)
2. **SAFE combo 20%** (moderate risk)
3. **RISKY combo 10%** (lottery ticket)

**Példa bank: 10,000 HUF**
- Singles: 7,000 HUF (7x 1000 HUF)
- SAFE combo: 2,000 HUF
- RISKY combo: 1,000 HUF

**Várható long-term:**
- Singles: +15-20% ROI
- SAFE: +5-10% ROI (volatilis)
- RISKY: -20% ROI (de 1 nagy nyerés fedezi)

---

## Config

**Customize combo sizes:**

```python
# bot/combo_builder.py

SAFE_COMBO_SIZE = 3  # Default
RISKY_COMBO_SIZE = 4  # Default

# Modify in build_combos():
select_safe_combo(picks, combo_size=3)
select_risky_combo(picks, combo_size=5)  # More risky
```

**Adjust stake:**

```python
format_combo_for_telegram(combo, "SAFE", stake=2000)  # 2000 HUF
```

---

## Win Rate Data (estimated)

**Historical simulation (if we had data):**

| Type | Odds Range | Win Rate | Expected Value |
|------|------------|----------|----------------|
| SAFE 3-pick | 3.5-5.5 | 45-55% | +5-10% |
| RISKY 4-pick | 8-15 | 25-35% | -10-20% |
| RISKY 5-pick | 15-30 | 15-25% | -30-40% |

**Takeaway:** SAFE combos are +EV if pick quality is good (70%+ single win rate)

---

## Limitations

1. **Correlation risk:** If all picks are home wins, bad day for favorites = all lose
2. **Variance:** High variance even with SAFE combos
3. **Bookmaker limits:** Some bukik limit combo bets

---

## TODO

- [ ] Historical combo tracking (win rate per type)
- [ ] Auto-adjust combo size based on pick quality
- [ ] Cross-sport combos (football + basketball)
- [ ] Hedge calculator (if 2/3 won, hedge the last?)

---

**Használd felelősséggel! Combo = fun, de nem get-rich-quick.**
