#!/usr/bin/env python3
"""Compile all Tabelog source files into a single organized reference file."""

import os

OUTPUT = r"C:\Users\Chris Hadley\.skills\skills\guide-creator\references\tabelog-scrape.md"

def write_file():
    sections = []

    # ==================== HEADER ====================
    sections.append("""# Tabelog Restaurant Research — Japan 2026 Family Trip
# Compiled: 2026-03-10

> **Total restaurants**: ~380+ across 17+ locations
> **Enrichment**: 36 Full-tier (3.80+), ~70 Medium-tier (3.70-3.79), remainder Light-tier (3.50-3.69)
> **Removed**: Oryori Tomiyama (Kamakura, permanently closed), Kitsune (Nara, closure undetermined)
> **URL redirect issues**: Toi Inshokuten (Nara), Izumo Soba Dandan (Nara), Osaka Mentetsu (Umeda) — raw entries kept, flagged
> **Guide dedup**: Tempura Kondo, Ramen Jiro Shinjuku Kabukicho Ten flagged as already in HTML guides

---

## Summary Stats by Location

| Location | Type | Restaurants | Top Score | Threshold |
|----------|------|-------------|-----------|-----------|
| Tokyo Shinjuku | Stay 1 (Apr 3-7) | 39 | 4.04 | 3.50+ |
| Tokyo Nezu/Ueno | Stay 2 (Apr 7-10) | 52 | 4.03 | 3.50+ |
| Osaka Dotonbori | Stay 3 (Apr 10-14) | 57 | 3.83 | 3.50+ |
| Kyoto Kawaramachi | Stay 4 (Apr 14-19) | ~45 | 4.46 | 3.50+ |
| Tokyo Shibuya | Activity area | 11 | 4.43 | 3.50+ |
| Tokyo Asakusa | Activity area | 7 | 4.38 | 3.50+ |
| Tokyo Harajuku | Activity area | 10 | 3.85 | 3.50+ |
| Tokyo Akihabara | Activity area | 20 | 3.87 | 3.50+ |
| Tokyo Ginza/Tsukiji | Activity area | 17 | 4.27 | 3.50+ |
| Kyoto Arashiyama | Activity area | 10 | 3.80 | 3.50+ |
| Kyoto Fushimi | Activity area | 12 | 3.72 | 3.50+ |
| Osaka Umeda | Activity area | 13 | 4.09 | 3.50+ |
| Nara | Day trip | ~25 | 3.96 | 3.30+ |
| Himeji | Day trip | ~40 | 3.65 | 3.30+ |
| Kamakura | Day trip | 18 | 3.75 | 3.30+ |
| Yokohama Chinatown | Day trip | 32 | 3.71 | 3.30+ |
| Hakone | Day trip | 21 | 4.39 | 3.30+ |
| Kinkakuji/North Kyoto | Day trip | 33 | 3.70 | 3.30+ |

## Summary Stats by Cuisine

| Cuisine | Count (est.) | Top Score | Best Location |
|---------|-------------|-----------|---------------|
| Ramen / Tsukemen | 90+ | 4.04 | Shinjuku (Raa Menya Shima) |
| Japanese Curry | 40+ | 3.85 | Harajuku (BLOCK HOUSE) |
| Yakiniku (BBQ) | 35+ | 4.28 | Kyoto (Shinya Yakiniku Daichan) |
| Yakitori / Kushikatsu | 20+ | 4.43 | Shibuya (Tori Chataro) |
| Udon / Soba | 35+ | 3.96 | Nara (Gen) |
| Cafe / Kissaten | 30+ | 3.76 | Multiple |
| Tempura | 10+ | 4.10 | Ginza (Tempura Kondo) |
| Tonkatsu | 10+ | 3.95 | Shinjuku (Katsu Pulipo) |
| Chinese | 15+ | 4.38 | Kyoto (Hirosawa) |
| Izakaya | 20+ | 4.28 | Kyoto (Shokudo Ogawa) |
| Okonomiyaki | 5+ | 3.70 | Dotonbori (Fukutarou) |
| Bars | 10+ | 3.96 | Kyoto (El Tesoro) |
| Other (Unagi, Beef, etc.) | 30+ | 4.46 | Kyoto (Niku no Takumi Miyoshi) |

## Coverage Gaps

| Location | Missing Cuisines |
|----------|-----------------|
| Shinjuku | Tempura, Izakaya, Okonomiyaki (none 3.5+) |
| Nezu/Ueno | Okonomiyaki |
| Dotonbori | No major gaps |
| Kyoto Kawaramachi | Tonkatsu, Japanese Curry |
| Arashiyama | Ramen weak (1 entry), no curry/yakiniku |
| Fushimi | No yakiniku, no cafe, no tempura |
| Himeji | Limited high-scoring entries overall |
| Hakone | No yakiniku, no curry specialist |""")

    # ==================== SHINJUKU ====================
    sections.append("""
---
---

# STAY LOCATIONS

---

## 1. Tokyo Shinjuku / Kitashinjuku (Stay 1: Apr 3-7)

### Ramen / Tsukemen

- **Raa Menya Shima** ⭐ 4.04 (2,028 reviews) 💰 Budget [ENRICHED FULL]
  - 📍 Nishi-Shinjuku-Gochome Sta. | 東京都渋谷区本町3-41-12
  - 💴 Lunch ¥1,700-2,500 | Dinner: N/A (closes early afternoon)
  - ⏰ Mon-Fri 8:45-14:30 (timed slots) | Closed Sat, Sun, holidays
  - 🏆 Tabelog Award 2022 & 2026 Bronze; Ramen TOKYO 100 (5 consecutive years); 2020 Ramen Shop of the Year
  - 🍳 **Must-order**: Ue Ramen (Shoyu) ¥1,700 — refined chicken shoyu; Tokusei adds 4 different chashu cuts + wontons
  - 🎭 Tiny 6-seat ramen temple; quiet, focused atmosphere
  - 👨‍👩‍👧‍👦 ⚠️ CHILDREN NOT ALLOWED. Weekday-only. Cash only
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13247487/)

- **Menya Sho Hon Ten** ⭐ 3.78 (4,301 reviews) 💰 Budget [ENRICHED MEDIUM]
  - 📍 Seibu Shinjuku Sta. | Under ¥999
  - 🍳 "Undisputed king of salt ramen in Shinjuku" — Shamo chicken shio ramen; special wonton
  - 💺 18 seats (counter only). Non-smoking, children welcome. Cash only
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13040181/)

- **Fuuunji Shinjuku Hon Ten** ⭐ 3.77 (4,984 reviews) 💰 Budget [ENRICHED MEDIUM]
  - 📍 Minami Shinjuku Sta. | Under ¥999
  - 🍳 Award-winning tsukemen; rich, creamy fish-pork broth — legendary queues
  - 💺 15 seats. Non-smoking. IC cards (Suica) accepted
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13044091/)

- **Tsukemen Gonokami Seisakujo** ⭐ 3.77 (4,958 reviews) 💰💰 Mid [ENRICHED MEDIUM]
  - 📍 Shinjuku Sanchome Sta. | ¥1,000-1,999
  - 🍳 Tokyo No.1 shrimp tsukemen — unmatched ebi broth
  - 💺 14 seats. Non-smoking, children welcome. Cash only
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13120708/)

- **Menya Kaijin Shinjuku Ten** ⭐ 3.74 (4,034 reviews) 💰 Budget [ENRICHED MEDIUM]
  - 📍 Shinjuku Sta. | ~¥1,000
  - ⏰ Mon-Fri 11:00-15:00 & 16:30-23:30; Sat 11:00-23:30; Sun 11:00-23:00
  - 🍳 Ara-cooked salt ramen — dashi from grilled fresh fish scraps; seafood-forward
  - 💺 16 seats. Non-smoking, children welcome, cash only
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13045287/)

- **Ramen Manrai** ⭐ 3.74 (3,573 reviews) 💰 Budget [ENRICHED MEDIUM]
  - 📍 Shinjuku Nishiguchi Sta. | ~¥1,000
  - ⏰ Daily 11:00-23:00
  - 🍳 Legendary chashu (mountain of pork slices), tsukemen; since 1960s
  - 💺 15 seats. Non-smoking, children welcome, cash only
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13000808/)

- **Niboshi Chuka Soba Suzuran** ⭐ 3.70 (2,904 reviews) 💰 Budget [ENRICHED MEDIUM]
  - 📍 Shinjuku Sanchome Sta. | Under ¥999
  - ⏰ 11:00-23:00 year-round
  - 🍳 Rich niboshi ramen — tonkotsu + niboshi broth with curly noodles
  - 💺 18 seats. Non-smoking, cash only
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13141542/)

- **Ramen Hosenka** ⭐ 3.69 (2,861 reviews) 💰💰 Mid
  - 📍 Shinjuku Nishiguchi Sta. | ¥1,000-1,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13224521/)

- **Ramen Horiuchi Shinjuku Hon Ten** ⭐ 3.69 (2,302 reviews) 💰💰 Mid
  - 📍 Shinjuku Nishiguchi Sta. | ¥1,000-1,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13042962/)

- **Chuka Soba Rukawa** ⭐ 3.69 (1,694 reviews) 💰💰 Mid
  - 📍 Shinjuku Nishiguchi Sta. | ¥1,000-1,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13236258/)

- **Menya Sho Misodokoro** ⭐ 3.68 (865 reviews) 💰 Budget
  - 📍 Nishi Shinjuku Sta. | Under ¥999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13266123/)

- **Sarusuberi** ⭐ 3.68 (2,445 reviews) 💰💰 Mid
  - 📍 Shinjuku Sanchome Sta. | ¥1,000-1,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13116353/)

- **Ramen Jiro Shinjuku Kabukicho Ten** ⭐ 3.67 (1,489 reviews) 💰 Budget ⚠️ ALREADY IN GUIDES (ramen-noodles-guide.html)
  - 📍 Seibu Shinjuku Sta. | Under ¥999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13200815/)

- **Raa Men Kuro Uzu** ⭐ 3.67 (1,382 reviews) 💰💰 Mid
  - 📍 Shinjuku Sanchome Sta. | ¥1,000-1,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13241664/)

### Tonkatsu

- **Katsu Pulipo** ⭐ 3.95 (1,272 reviews) 💰💰 Mid [ENRICHED FULL]
  - 📍 JR Shinjuku East Exit (3 min) | Lunch ¥4,000-4,999 | Dinner ¥8,000-9,999
  - 🏆 Tabelog Tonkatsu 100 (2022, 2024, 2026)
  - 🍳 Premium branded pork tonkatsu — 150+ varieties sampled, 12-13 selected; double-fried; clay pot rice
  - 💺 50 seats: box sofas, semi-private rooms
  - 👨‍👩‍👧‍👦 Family-friendly — babies through school-age welcome; strollers OK. Visa/Master/Diners, Suica, PayPay
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13264309/)

### Udon / Soba

- **Udon Shin** ⭐ 3.70 (2,551 reviews) 💰 Budget [ENRICHED MEDIUM]
  - 📍 Minami Shinjuku Sta. | ¥1,000-1,999
  - ⏰ 11:00-22:00 daily; ticket distribution from 9:00
  - 🍳 Handmade udon — popular with international visitors
  - 💺 12 seats. Non-smoking, children welcome, strollers welcome, cash only
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13125862/)

### Yakitori

- **Michishirube** ⭐ 3.75 (593 reviews) 💰💰 Mid [ENRICHED MEDIUM]
  - 📍 Seibu-Shinjuku Sta., Kabukicho | Dinner ¥3,000-3,999
  - ⏰ Mon/Tue/Thu-Sat 18:00-01:00 | Closed Wed/Sun/holidays
  - 🍳 Exceptional yakitori; red lantern hideout; vegetarian options
  - 💺 24 seats (1F counter+table; 2F tatami rooms). Cash only
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13101685/)

### Japanese Curry

- **FISH Shinjuku Ten** ⭐ 3.79 (2,472 reviews) 💰💰 Mid [ENRICHED MEDIUM]
  - 📍 Seibu Shinjuku | Lunch ¥1,000-1,999 | Dinner ¥2,000-2,999
  - 🍳 Authentic Indian spice curry with fish fry; mild yet flavourful
  - 💺 26 seats. Non-smoking, children & strollers welcome. Cards+PayPay
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13222551/)

- **Spicy Curry House Hangetsu** ⭐ 3.79 (1,472 reviews) 💰 Budget [ENRICHED MEDIUM]
  - 📍 Seibu Shinjuku | Lunch ¥1,000-1,999
  - 🍳 Creative daily-changing spice curry; shrimp keema fan favourite
  - 💺 13 seats. Cash or PayPay only
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13211678/)

- **Epitaph Curry** ⭐ 3.76 (1,291 reviews) 💰 Budget [ENRICHED MEDIUM]
  - 📍 Shinjuku Sanchome | ¥1,000-1,999
  - 🍳 Goan vindaloo; creative curry platters — top 100 curry
  - 💺 12 seats. Cards+PayPay. Children welcome
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13246903/)

- **Gandhi** ⭐ 3.72 (4,086 reviews) 💰 Budget [ENRICHED MEDIUM]
  - 📍 Shinjuku Sanchome | ~¥1,000
  - 🍳 European-style beef tendon stew curry; long-established institution
  - 💺 16 seats. Cards+IC+QR accepted
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13000880/)

- **CHIKYU MASALA** ⭐ 3.72 (864 reviews) 💰 Budget [ENRICHED MEDIUM]
  - 📍 Shinjuku Sanchome | ~¥1,000
  - 🍳 Japanese dashi x Middle Eastern spice curry; Lebanese-style keema
  - 💺 6 seats (very small). English menu. QR pay only
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13248884/)

- **Tokyo Dominica** ⭐ 3.71 (1,956 reviews) 💰 Budget [ENRICHED MEDIUM]
  - 📍 Shinjuku Sanchome | Lunch under ¥999 | Dinner ¥1,000-1,999
  - 🍳 Soup curry — 5 soup types; sister restaurant has Michelin Bib Gourmand
  - 💺 20 seats. Non-smoking, takeout available
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13124113/)

- **Higashi Shinjuku Sanrasa** ⭐ 3.71 (497 reviews) 💰 Budget [ENRICHED MEDIUM]
  - 📍 Higashi Shinjuku Sta. | ¥1,000-1,999
  - ⚠️ Closed Mon/Sat/Sun/Holidays — Tue-Fri only
  - 🍳 Standing-only spice curry, 30 meals/day limit. No perfume. Photography prohibited
  - 💺 ~5 standing spots. Not suitable for families
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13215551/)

- **Spice Bazaar Achakana** ⭐ 3.70 (993 reviews) 💰 Budget [ENRICHED MEDIUM]
  - 📍 Shinjuku Nishiguchi Sta. | Lunch ¥1,000-1,999 | Dinner ¥3,000-3,999
  - 🍳 Indian-based spice curry & bar; naan, cheese kulcha
  - 💺 15 seats. Cash only
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13233798/)

- **Hot Spoon Nishi Shinjuku Ten** ⭐ 3.69 (1,160 reviews) 💰💰 Mid
  - 📍 Shinjuku Sta. | ¥1,000-1,999 | 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13198942/)

- **COCHIN NIVAS** ⭐ 3.68 (1,058 reviews) 💰💰 Mid
  - 📍 Nishi Shinjuku Gochome Sta. | Dinner ¥1,000-1,999 | Indian curry
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13056242/)

- **Mon Snack** ⭐ 3.67 (1,527 reviews) 💰💰 Mid
  - 📍 Shinjuku Sanchome Sta. | ¥1,000-1,999 | 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13012067/)

### Yakiniku (BBQ)

- **USHIGORO S. SHINJUKU** ⭐ 3.75 (441 reviews) 💰💰💰💰 Luxury [ENRICHED MEDIUM]
  - 📍 Shinjuku-sanchome Sta. | Lunch ¥10,000-14,999 | Dinner ¥20,000-29,999 (+10% service)
  - 🍳 Premium A5 wagyu; sommelier; private rooms for 2-8
  - 💺 54 seats. Children welcome; private rooms ideal for families. All cards
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13268688/)

- **Yugen Tei Shinjuku** ⭐ 3.69 (885 reviews) 💰💰💰 High
  - 📍 Seibu Shinjuku Sta. | Lunch ¥4,000-4,999 | Dinner ¥15,000-19,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13004152/)

### Cafe / Kissaten

- **CAFE AALIYA** ⭐ 3.75 (3,166 reviews) 💰 Budget [ENRICHED MEDIUM]
  - 📍 Shinjuku-sanchome Sta. | ¥1,000-1,999
  - 🍳 French toast (famous across Tokyo); cosy basement cafe
  - 💺 46 seats. Children welcome. All payment methods
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13012089/)

- **Coffee Kizoku Edinburgh** ⭐ 3.72 (1,653 reviews) 💰 Budget [ENRICHED MEDIUM]
  - 📍 Shinjuku Sanchome Sta. | 💺 117 seats (smoking/non-smoking sections)
  - 🍳 Siphon-brewed coffee, retro kissaten
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13017217/)

- **Jikabaisen Coffee Bon** ⭐ 3.70 (1,066 reviews) 💰💰 Mid [ENRICHED MEDIUM]
  - 📍 Shinjuku Nishiguchi Sta. | ⏰ 13:00-18:00 daily | Cash only
  - 🍳 Self-roasted specialty coffee (¥1,800); strawberry shortcake (¥1,700)
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13000735/)

- **All Seasons Coffee** ⭐ 3.67 (1,051 reviews) 💰💰 Mid
  - 📍 Shinjuku Gyoemmae Sta. | 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13187981/)

### Other

- **Tokyo Niku Shabuya** ⭐ 3.96 (605 reviews) 💰💰💰💰 Splurge [ENRICHED FULL] — Shabu-shabu
  - 📍 Higashi-Shinjuku Sta. | Lunch ¥15,000-19,999 | Dinner ¥20,000-30,000+
  - 🏆 Tabelog Award Bronze 2019-2026 (8 years)
  - 🍳 Kobe Beef Tajima-gyu shabu-shabu — only ~10 restaurants can source
  - 👨‍👩‍👧‍👦 ⚠️ ADULTS ONLY — minimum age 15. Non-smoking
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13196268/)

- **PRETTY PORK FACTORY** ⭐ 3.72 (1,033 reviews) 💰💰 Mid [ENRICHED MEDIUM] — Pork Shabu-shabu
  - 📍 Seibu Shinjuku Sta. | Lunch ¥3,000-3,999 | Dinner ¥6,000-7,999
  - 💺 66 seats; semi-private rooms
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13254601/)

- **Shinjuku Kappou Nakajima** ⭐ 3.69 (1,456 reviews) 💰💰 Mid — Japanese (sardine set lunch)
  - 📍 Shinjuku Sanchome | Lunch ¥1,000-1,999 | Dinner ¥15,000-19,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13000959/)

- **Sasamoto Shinjuku Ten** ⭐ 3.69 (272 reviews) 💰💰 Mid — Grilled tripe
  - 📍 Shinjuku Nishiguchi | Dinner ¥2,000-2,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13000779/)

- **SHOGUN BURGER Shinjuku Ten** ⭐ 3.67 (2,350 reviews) 💰💰 Mid — Wagyu Burger
  - 📍 Shinjuku Nishiguchi | ¥1,000-1,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1304/A130401/13227776/)""")

    # ==================== NEZU/UENO ====================
    sections.append("""
---

## 2. Tokyo Nezu / Ueno (Stay 2: Apr 7-10)

> Source: Tabelog English — Nezu/Sendagi/Yanaka + Ueno/Okachimachi, 3.5+. 52 restaurants total.

### Ramen / Tsukemen (sorted by score)

- **Chugoku Ikkyosai Bai En** ⭐ 3.76 (289 reviews) 💰 Budget(L)/💰💰💰 Splurge(D) — Chinese/Ramen
  - 📍 Inaricho Sta. | Lunch ¥1,000-1,999 | Dinner ¥10,000-14,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131101/13238666/)
- **Shisen Tantanmen Aun Yushima Honten** ⭐ 3.75 (2,863 reviews) 💰 Budget
  - 📍 Yushima Sta. | ¥1,000-1,999 — Famous spicy tantanmen
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131101/13042564/)
- **Ramen Kamo to Negi** ⭐ 3.74 (4,320 reviews) 💰 Budget
  - 📍 Okachimachi Sta. | ¥1,000-1,999 — Duck & scallion ramen, hugely popular
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131101/13210392/)
- **Ramen Inariya** ⭐ 3.74 (1,751 reviews) 💰 Budget
  - 📍 Inaricho Sta. | Under ¥999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131101/13180646/)
- **China Soba Yamato** ⭐ 3.73 (955 reviews) 💰 Budget
  - 📍 Inaricho Sta. | ¥1,000-1,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131101/13206756/)
- **Oudouya Chokkei IEKEI TOKYO** ⭐ 3.72 (2,197 reviews) 💰 Budget
  - 📍 Suehirocho Sta. | Under ¥999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131101/13261243/)
- **Aida Ya** ⭐ 3.71 (1,387 reviews) 💰 Budget — Tsukemen
  - 📍 Naka Okachimachi Sta. | ¥1,000-1,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131101/13288181/)
- **Sanji** ⭐ 3.70 (1,202 reviews) 💰 Budget
  - 📍 Inaricho Sta. | ¥1,000-1,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131101/13136639/)
- **Tanaka Soba Ten Akihabara Ten** ⭐ 3.68 (1,545 reviews) 💰 Budget
  - 📍 Suehirocho Sta. | 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131101/13137336/)
- **Tomishiro** ⭐ 3.68 (504 reviews) 💰 Budget
  - 📍 Naka Okachimachi | 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131101/13135911/)
- **Menya Hidamari** ⭐ 3.60 (554 reviews) 💰 Budget
  - 📍 Sendagi Sta. | Under ¥999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131106/13129718/)

### Tonkatsu

- **Ponta Honke** ⭐ 3.77 (1,943 reviews) 💰💰💰 Splurge — Est. 1905
  - 📍 Ueno Hirokoji Sta. | ¥4,000-4,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131101/13003587/)
- **Tonpachi Tei** ⭐ 3.68 (1,285 reviews) 💰💰 Mid
  - 📍 Ueno Okachimachi | Dinner ¥2,000-2,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131101/13003593/)

### Udon / Soba

- **Soba Kokoro** ⭐ 3.72 (608 reviews) 💰 Budget(L)/💰💰 Mid(D)
  - 📍 Nezu Sta. | Lunch ¥1,000-1,999 | Dinner ¥3,000-3,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131106/13187177/)
- **Teuchi Soba Nezu Takajo** ⭐ 3.71 (794 reviews) 💰💰 Mid
  - 📍 Nezu Sta. | ¥2,000-2,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131106/13009812/)
- **Nezu Kamachiku** ⭐ 3.66 (1,190 reviews) 💰💰 Mid — Beautiful traditional udon house
  - 📍 Nezu Sta. | Lunch ¥2,000-2,999 | Dinner ¥5,000-5,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131106/13020252/)
- **Yoshibo Rin** ⭐ 3.65 (641 reviews) 💰 Budget(L) — Soba + Tempura
  - 📍 Nezu Sta. | 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131106/13018408/)
- **Udon Nenotsu** ⭐ 3.57 (192 reviews) 💰 Budget(L)
  - 📍 Nezu Sta. | 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131106/13259738/)
- **Nezu Soushian** ⭐ 3.56 (32 reviews) 💰💰💰 Splurge — Soba
  - 📍 Nezu Sta. | Dinner ¥10,000-14,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131106/13178315/)
- **Sendagi Udon Shioman** ⭐ 3.54 (260 reviews) 💰 Budget(L)
  - 📍 Sendagi Sta. | 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131106/13252906/)

### Yakitori / Kushikatsu

- **Nezu Yakitori Terusumi** ⭐ 3.89 (398 reviews) 💰💰💰 Splurge — Premium yakitori omakase
  - 📍 Nezu Sta. | Dinner ¥10,000-14,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131106/13182104/)
- **Yakitori Nishiki** ⭐ 3.71 (118 reviews) 💰💰💰 Splurge
  - 📍 Yushima Sta. | 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131101/13297763/)
- **Torie Ueno Hiro Koji Ten** ⭐ 3.70 (682 reviews) 💰💰💰 Splurge
  - 📍 Ueno Hirokoji Sta. | 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131101/13128870/)
- **Hantei Nezu Honten** ⭐ 3.65 (961 reviews) 💰💰 Mid(L)/💰💰💰 Splurge(D) — Kushiage in stunning 1917 wooden building
  - 📍 Nezu Sta. | Lunch ¥3,000-3,999 | Dinner ¥6,000-7,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131106/13003577/)

### Tempura

- **Tempura Shimomura** ⭐ 3.90 (314 reviews) 💰💰💰 Splurge
  - 📍 Shin Okachimachi Sta. | Lunch ¥5,000-5,999 | Dinner ¥10,000-14,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131101/13213663/)
- **Tempura Fukutarou** ⭐ 3.70 (214 reviews) 💰💰💰 Splurge
  - 📍 Nezu Sta. | ¥10,000-14,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131106/13204299/)

### Japanese Curry

- **DELHI Ueno Ten** ⭐ 3.79 (3,469 reviews) 💰 Budget — Legendary (est. 1956)
  - 📍 Ueno Hirokoji Sta. | Under ¥999 — Try the Kashmir Curry
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131101/13003605/)
- **Spice Palette** ⭐ 3.77 (927 reviews) 💰 Budget
  - 📍 Akihabara Sta. | ¥1,000-1,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131101/13240357/)
- **Caligari Akihabara** ⭐ 3.76 (1,885 reviews) 💰 Budget
  - 📍 Suehirocho Sta. | ¥1,000-1,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131101/13178599/)
- **BROWNIE** ⭐ 3.74 (914 reviews) 💰 Budget
  - 📍 Suehirocho Sta. | Under ¥999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131101/13006343/)
- **Raffles Curry** ⭐ 3.73 (823 reviews) 💰 Budget
  - 📍 Naka Okachimachi | ¥1,000-1,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131101/13033116/)
- **Andhra Kitchen** ⭐ 3.67 (1,548 reviews) 💰 Budget — South Indian thalis
  - 📍 Okachimachi Sta. | Under ¥999 (lunch)
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131101/13096305/)
- **Spice Curry Tokujiro** ⭐ 3.54 (179 reviews) 💰 Budget
  - 📍 Sendagi Sta. | Under ¥999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131106/13215316/)

### Izakaya

- **Yanaka Toriyoshi** ⭐ 3.61 (217 reviews) 💰💰💰 Splurge — Chicken hot pot
  - 📍 Nishi Nippori Sta. | Dinner ¥6,000-7,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131106/13054593/)
- **Gyokai Zanmai Akira** ⭐ 3.57 (207 reviews) 💰💰💰 Splurge — Seafood
  - 📍 Sendagi Sta. | 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131106/13018434/)
- **Kuruma Ya** ⭐ 3.54 (327 reviews) 💰💰💰 Splurge
  - 📍 Nezu Sta. | Dinner ¥8,000-9,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131106/13020753/)

### Yakiniku (BBQ)

- **Namaiki** ⭐ 3.71 (2,251 reviews) 💰💰💰 Splurge — Offal/tripe yakiniku
  - 📍 Suehirocho Sta. | 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131101/13165294/)
- **Niku to Nihonshu** ⭐ 3.57 (538 reviews) 💰💰💰 Splurge — Wagyu + sake
  - 📍 Sendagi Sta. | Dinner ¥8,000-9,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131106/13194197/)

### Cafe / Kissaten

- **Zehn Coffee** ⭐ 3.71 (568 reviews) 💰 Budget — Classic kissaten
  - 📍 Yushima Sta. | Under ¥999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131101/13043953/)
- **Kissa Ko** ⭐ 3.71 (445 reviews) 💰 Budget
  - 📍 Keisei Ueno Sta. | Under ¥999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131101/13049802/)
- **HAGI CAFE** ⭐ 3.64 (712 reviews) 💰 Budget — Converted 1950s wooden building, atmospheric
  - 📍 Sendagi Sta. | ¥1,000-1,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131106/13153660/)
- **CIBI Tokyo Ten** ⭐ 3.56 (427 reviews) 💰 Budget
  - 📍 Sendagi Sta. | ¥1,000-1,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131106/13213733/)

### Other Notable

- **Fugu Makino** ⭐ 4.03 (419 reviews) 💰💰💰💰 Luxury — Legendary fugu specialist
  - 📍 Inaricho Sta. | Dinner ¥20,000-29,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131101/13003708/)
- **Fakalo pizza gallery** ⭐ 3.98 (308 reviews) 💰💰💰 Splurge — Neapolitan pizza
  - 📍 Shin Okachimachi Sta. | Lunch ¥5,000-5,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131101/13269491/)
- **EST!** ⭐ 3.85 (341 reviews) 💰💰💰 Splurge — Bar
  - 📍 Yushima Sta. | Dinner ¥5,000-5,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131101/13003582/)
- **Tori Tsune Shizen Do** ⭐ 3.75 (1,465 reviews) 💰💰 Mid — Best oyako-don in Tokyo (lunch)
  - 📍 Suehirocho Sta. | Lunch ¥2,000-2,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131101/13005547/)
- **Gensen Yoshoku Sakurai** ⭐ 3.68 (1,841 reviews) 💰💰 Mid — Omurice, hamburg steak
  - 📍 Ueno Hirokoji Sta. | Lunch ¥2,000-2,999
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131101/13003638/)
- **Bar Hasegawa** ⭐ 3.64 (66 reviews) 💰 Budget
  - 📍 Nezu Sta. | 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131106/13180746/)
- **Ichifuji** ⭐ 3.57 (161 reviews) 💰 Budget(L) — Beef dishes
  - 📍 Sendagi Sta. | 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131106/13108521/)
- **Mametan** ⭐ 3.58 (83 reviews) 💰💰💰 Splurge — Kaiseki
  - 📍 Nezu Sta. | 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131106/13184493/)
- **Wosakana Shokudo** ⭐ 3.53 (90 reviews) 💰 Budget — Seafood
  - 📍 Nezu Sta. | 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131106/13307799/)""")

    # ==================== REMAINING LOCATIONS (abbreviated for file size) ====================
    # For the remaining locations, we include the raw data directly since it's already well-organized

    sections.append("""
---

## 3. Osaka Dotonbori / Namba / Shinsekai (Stay 3: Apr 10-14)

> Source: Tabelog English, Namba/Dotonbori + Ebisu/Shinsekai areas, 3.5+. 57 restaurants total.
> See raw file tabelog-raw-dotonbori.md for full details. Key enriched entries below.

### Ramen / Tsukemen (13 restaurants, sorted by score)

- **Menya Joroku Nanba Ten** ⭐ 3.74 (2,540 reviews) 💰 Budget — Most reviewed ramen in area
  - 📍 Namba Sta. | Under ¥999 | 🔗 [Tabelog](https://tabelog.com/en/osaka/A2701/A270202/27084754/)
- **Naniwa Menjiro** ⭐ 3.72 (1,943 reviews) 💰 Budget — Ramen/Tsukemen
  - 📍 Osaka Namba Sta. | Under ¥999 | 🔗 [Tabelog](https://tabelog.com/en/osaka/A2701/A270202/27112089/)
- **Men no Youji** ⭐ 3.72 (1,400 reviews) 💰 Budget
  - 📍 Nippombashi Sta. | Under ¥999 | 🔗 [Tabelog](https://tabelog.com/en/osaka/A2701/A270202/27072765/)
- **Yuai Tei** ⭐ 3.72 (982 reviews) 💰 Budget
  - 📍 Ebisucho Sta. | ¥1,000-1,999 | 🔗 [Tabelog](https://tabelog.com/en/osaka/A2701/A270202/27079226/)
- **Mutekko Oosakaten** ⭐ 3.71 (2,275 reviews) 💰 Budget
  - 📍 Imamiyaebisu Sta. | 🔗 [Tabelog](https://tabelog.com/en/osaka/A2701/A270206/27005006/)
- **NEXT Shikaku** ⭐ 3.69 (1,057 reviews) 💰 Budget | **Dashi to Komugi** ⭐ 3.66 | **Men ni Hikari o Bettei** ⭐ 3.62 | **Oudouya Chokkei** ⭐ 3.62 | **Men ni Hikari o** ⭐ 3.61 | **Chuka Soba Fujii** ⭐ 3.60 | **Ramen So Rekishi** ⭐ 3.55 | **Hong Kong** ⭐ 3.55

### Yakiniku (BBQ) (9 restaurants)

- **Kitan In** ⭐ 3.77 (181 reviews) 💰💰💰💰 Splurge — Premium innovative yakiniku
  - 📍 Namba Sta. | Dinner ¥20,000-29,999 | 🔗 [Tabelog](https://tabelog.com/en/osaka/A2701/A270202/27128757/)
- **Seoul** ⭐ 3.70 (609 reviews) 💰💰💰 — ¥4,000-4,999
- **Nikushou Nakata** ⭐ 3.69 | **Tahei** ⭐ 3.67 | **Niku Horumon Tetsuwan** ⭐ 3.64 | **Yakiniku Wabi Sabi** ⭐ 3.64 | **Shinjuku Yakiniku Gyutan** ⭐ 3.61 | **Yakiniku Kazumasa** ⭐ 3.60 | **Yakiniku Horumon Kagiya** ⭐ 3.55

### Izakaya (8 restaurants)

- **Sakana Tetsu** ⭐ 3.69 | **Kisetsu Ryori Ichii** ⭐ 3.64 | **Havana** ⭐ 3.63 | **Stand Tsumamigui** ⭐ 3.63 | **Tosui** ⭐ 3.63 | **Nihonshu to Robatayaki** ⭐ 3.61 | **556** ⭐ 3.58 | **Tachinomi Maruya** ⭐ 3.57

### Udon / Soba (4 restaurants)

- **Chitose Hon Ten** ⭐ 3.72 (2,109 reviews) 💰 Budget — Namba institution
  - Under ¥999 | 🔗 [Tabelog](https://tabelog.com/en/osaka/A2701/A270202/27002763/)
- **Kida Take Udon** ⭐ 3.69 | **Tezukuri Udon Tenkomori** ⭐ 3.68 | **Tenmasa** ⭐ 3.66

### Yakitori / Kushikatsu (4)

- **Tori Ichi** ⭐ 3.73 | **Rokukaku tei** ⭐ 3.69 | **Yakitori Oren** ⭐ 3.64 | **Datedachi** ⭐ 3.61

### Tempura

- **Tempura Ando** ⭐ 3.73 (163 reviews) 💰💰💰💰 Splurge — ¥20,000-29,999

### Japanese Curry (3)

- **Curry Ya Madras** ⭐ 3.66 | **Singh's Kitchen** ⭐ 3.65 | **Magic Spice** ⭐ 3.61

### Okonomiyaki (2)

- **Fukutarou Hon Ten** ⭐ 3.70 (2,485 reviews) 💰💰 Mid — Very popular, high review count
  - Lunch ¥1,000-1,999 | 🔗 [Tabelog](https://tabelog.com/en/osaka/A2701/A270202/27002665/)
- **Okonomiyaki Chitose** ⭐ 3.63 💰 Budget

### Cafe / Kissaten (4)

- **Creperie Alcyon** ⭐ 3.72 | **ARABIYA** ⭐ 3.67 | **Junkissa American** ⭐ 3.66 | **Sennariya Coffee** ⭐ 3.62

### Other Notable

- **Shimanouchi Ichiyo** ⭐ 3.83 💰💰💰💰 — Kaiseki/Kappo
- **Mikuni Tei** ⭐ 3.72 — Chinese
- **Naniwa Kappou Kigawa** ⭐ 3.71 — Kappo
- **Tonkatsu Shabushabu Arata** ⭐ 3.63 — Tonkatsu
- **Juutei** ⭐ 3.66 — Yoshoku
- **Ippotei Hon Ten** ⭐ 3.66 — Chinese dim sum
- **Daikoku** ⭐ 3.65 — Cafeteria/Teishoku""")

    sections.append("""
---

## 4. Kyoto Kawaramachi / Gion / Kyoto Station (Stay 4: Apr 14-19)

> Source: Tabelog English, Central Kyoto areas, 3.5+. ~45 restaurants.

### Ramen / Tsukemen (4 restaurants)

- **Honke Daiichi Asahi Hon Ten** ⭐ 3.74 (6,414 reviews) 💰 Budget — Iconic Kyoto ramen, massive reviews
  - 📍 Kyoto Sta. | Under ¥999 | 🔗 [Tabelog](https://tabelog.com/en/kyoto/A2601/A260101/26000873/)
- **Ginjo Ramen Kubota** ⭐ 3.74 (1,667 reviews) 💰 Budget — Tsukemen
  - 📍 Gojo Sta. | ¥1,000-1,999 | 🔗 [Tabelog](https://tabelog.com/en/kyoto/A2601/A260101/26004660/)
- **Menya Inoichi** ⭐ 3.71 (1,031 reviews) 💰 Budget
  - 📍 Kyoto Kawaramachi Sta. | ¥1,000-1,999 | 🔗 [Tabelog](https://tabelog.com/en/kyoto/A2601/A260201/26032368/)
- **Kaidashi Men Kitada** ⭐ 3.69 (1,550 reviews) 💰 Budget
  - 📍 Kyoto Sta. | Under ¥999 | 🔗 [Tabelog](https://tabelog.com/en/kyoto/A2601/A260101/26036754/)

### Udon / Soba

- **Yamamoto Menzou** ⭐ 3.91 (2,598 reviews) 💰 Budget — Tabelog Award Bronze; Udon WEST Top 100
  - 📍 Higashiyama Sta. | Lunch ¥1,000-1,999 — Best udon in Kyoto
  - 🔗 [Tabelog](https://tabelog.com/en/kyoto/A2601/A260301/26002504/)

### Tempura

- **Tempura Kyoboshi** ⭐ 3.87 (133 reviews) 💰💰💰💰 Splurge — Tabelog 100
  - 📍 Gion Shijo Sta. | Dinner ¥15,000-19,999 | 🔗 [Tabelog](https://tabelog.com/en/kyoto/A2601/A260301/26006057/)
- **Tempura Tokoro Kyorynsen** ⭐ 3.66 (303 reviews) 💰💰 Mid(L)/💰💰💰 Splurge(D)
  - 📍 Kyoto Sta. | 🔗 [Tabelog](https://tabelog.com/en/kyoto/A2601/A260101/26000484/)

### Izakaya

- **Shokudo Ogawa** ⭐ 4.28 (358 reviews) 💰💰💰💰 Splurge — Exceptionally high score
  - 📍 Kyoto Kawaramachi Sta. | ¥10,000-14,999
  - 🔗 [Tabelog](https://tabelog.com/en/kyoto/A2601/A260201/26013892/)
- **Hotel De Ogawa** ⭐ 3.72 (142 reviews) 💰💰💰 | **Henkotsu** ⭐ 3.65 💰💰 Mid — Great value near station

### Yakiniku (BBQ) (5 restaurants)

- **Shinya Yakiniku Daichan** ⭐ 4.28 (96 reviews) 💰💰💰💰 Splurge — Extremely high rating
  - 📍 Kawaramachi | ¥20,000-29,999 | 🔗 [Tabelog](https://tabelog.com/en/kyoto/A2601/A260201/26039693/)
- **Niku Ryori Arakawa** ⭐ 3.77 | **Yakiniku Yamachan** ⭐ 3.77 — Children welcome
- **Yakiniku Yazawa Kyoto** ⭐ 3.71 — Good lunch deal (¥3,000)
- **Fujimura** ⭐ 3.70 — Best value yakiniku (¥5,000)

### Chinese (5 restaurants — exceptionally strong in Kyoto)

- **Hirosawa** ⭐ 4.38 (280 reviews) 💰💰💰💰 Luxury — ¥30,000-39,999
- **Nishibuchi Hanten** ⭐ 4.35 (447 reviews) 💰💰💰💰 Luxury
- **Kyo Seika** ⭐ 4.18 (244 reviews) 💰💰💰💰 Splurge
- **VELROSIER** ⭐ 4.01 (243 reviews) 💰💰💰💰 Splurge
- **Ikki** ⭐ 3.95 (212 reviews) 💰💰💰 — Tabelog Award Bronze; Chinese WEST 100

### Beef / Meat Specialist

- **Niku no Takumi Miyoshi** ⭐ 4.46 (665 reviews) 💰💰💰💰 Luxury — Highest in all Kyoto
  - 📍 Gion Shijo Sta. | Dinner ¥60,000-79,999 | Closed Sunday
  - 🔗 [Tabelog](https://tabelog.com/en/kyoto/A2601/A260301/26002222/)
- **Yassan** ⭐ 4.17 (463 reviews) 💰💰💰 — More accessible beef specialist
- **Kyoto Niku Kappou Miyata** ⭐ 3.64 — Lunch ¥8,000-9,999

### Cafe / Kissaten (5)

- **Kissa Ashijima** ⭐ 3.73 | **Salon de the FRANCOIS** ⭐ 3.72 — Historic, stunning interiors
- **Smart Coffee** ⭐ 3.71 — Famous pancakes | **ELEPHANT FACTORY COFFEE** ⭐ 3.71
- **FUKUNAGA901** ⭐ 3.62

### Bars (5)

- **El Tesoro** ⭐ 3.96 — Tabelog 100 Bar | **Bar Rocking chair** ⭐ 3.89
- **BAR TALISKER** ⭐ 3.88 | **Calvador** ⭐ 3.83 | **BAR Kingdom** ⭐ 3.83

### Other Notable

- **Shokudo Miyazaki** ⭐ 3.97 — Japanese Cuisine | **Kyoto Wakuden** ⭐ 3.92 — Accessible Wakuden branch
- **Kyoshumi Hishiiwa** ⭐ 3.88 — Bento, Tabelog 100 | **Kon** ⭐ 3.86 — Unagi
- **Yamamoto Mambo** ⭐ 3.69 — Okonomiyaki, budget | **Yoshida Yama Seseri** ⭐ 3.62 — Yakitori
- **Gozan Nozomi** ⭐ 3.62 — Teppanyaki | **Koryouri Takaya** ⭐ 3.64 — Affordable Japanese lunch""")

    # ==================== ACTIVITY AREAS ====================
    sections.append("""
---
---

# ACTIVITY AREAS

---

## 5. Tokyo Shibuya

### Yakitori

- **Tori Chataro** ⭐ 4.43 (700 reviews) 💰💰💰 High [ENRICHED FULL]
  - 📍 Shibuya Sta. (10 min) | Dinner ¥20,000-29,999 (course only)
  - ⏰ Wed-Sun 17:30-23:30 | Closed Mon & Tue
  - 🏆 Tabelog Award 2026 Silver; Yakitori EAST Top 100
  - 🍳 Omakase with six chicken varieties — Hinai Jidori, Ikoku Shamo, etc. Signature tasting comparison skewers
  - 👨‍👩‍👧‍👦 ⚠️ NOT family-friendly — requests no small children. 11 counter seats only. Reservation only, extremely hard to book
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1303/A130301/13157208/)

### Yakiniku

- **Sumibi Yaki Yuji** ⭐ 4.19 (2,218 reviews) 💰💰 Mid [ENRICHED FULL]
  - 📍 Shibuya Sta. | Dinner ¥6,000-9,999
  - ⏰ Mon-Sat 16:00-23:00 | Closed Sun
  - 🏆 Tabelog Award Silver/Bronze (2019-2026); Yakiniku TOKYO 100
  - 🍳 Legendary horumon (offal); curry served at end is cult favourite. Cash only
  - 👨‍👩‍👧‍👦 Older kids (8+) could enjoy. Non-smoking. Cash only
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1303/A130301/13001794/)

### Tempura

- **CHIKAMINE** ⭐ 3.94 (168 reviews) 💰💰💰 High [ENRICHED FULL]
  - 📍 Shibuya Sta. (7 min) | Lunch ¥3,000-3,999 | Dinner ¥15,000-16,000
  - 🍳 20-piece seasonal tempura omakase incl. dessert + finishing ramen; uni tempura standout
  - 👨‍👩‍👧‍👦 9 counter seats; NO English spoken; 2.5hr course. Not ideal for young children
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1303/A130301/13280028/)

### Ramen

- **Hayashi** ⭐ 3.78 (3,323 reviews) 💰 Budget [ENRICHED MEDIUM]
  - 📍 Shibuya Sta. | Lunch ¥1,000-1,999 | 10 seats, English menu
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1303/A130301/13003367/)
- **Chuka Menten Kiraku** ⭐ 3.76 (4,641 reviews) 💰 Budget [ENRICHED MEDIUM]
  - 📍 Shinsen Sta. | Under ¥999 | 27 seats (2F tables good for families)
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1303/A130301/13001705/)

### Curry

- **Murghee** ⭐ 3.77 (2,248 reviews) 💰 Budget [ENRICHED MEDIUM]
  - 📍 Shinsen Sta. | Egg Murghee curry; 32 seats
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1303/A130301/13001732/)
- **Curry Shop Hatsukoi** ⭐ 3.76 (1,529 reviews) 💰 Budget [ENRICHED MEDIUM]
  - 📍 Shinsen Sta. | Sri Lankan/South Indian; biryani on weekends
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1303/A130301/13240190/)
- **Pork Vindaloo Taberu Fukudaitoryo** ⭐ 3.76 (976 reviews) 💰 Budget [ENRICHED MEDIUM]
  - 📍 Shinsen Sta. | 5 seats only
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1303/A130301/13235448/)
- **MarieIranganee** ⭐ 3.76 (920 reviews) 💰 Budget [ENRICHED MEDIUM]
  - 📍 Shinsen Sta. | Sri Lankan curry; 15 seats
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1303/A130301/13166471/)

### Kissaten / Cafe

- **Minimal Tomigaya Honten** ⭐ 3.85 (774 reviews) 💰 Budget [ENRICHED FULL] — Bean-to-bar chocolate
  - 📍 Yoyogi Hachiman Sta. | ¥1,000-1,999
  - 🍳 Chocolate tasting, hot chocolate. Walk-in only. Family-friendly, strollers OK
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1303/A130301/13175834/)
- **Chatei Hatou** ⭐ 3.76 (2,016 reviews) 💰 Budget [ENRICHED MEDIUM] — Classic kissaten
  - 📍 Shibuya Sta. | 50 seats. Children welcome. Cash only
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1303/A130301/13001169/)

---

## 6. Tokyo Asakusa

- **Takajo Kotobuki** ⭐ 4.38 (191 reviews) 💰💰💰💰 Luxury [ENRICHED FULL] — Wild game bird
  - 📍 Asakusa Sta. | Dinner ¥30,000-39,999 | Invitation only (parties of 4+). Cash only
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131102/13003661/)
- **Asakusa Juroku** ⭐ 3.90 (438 reviews) 💰💰 Mid [ENRICHED FULL] — Soba
  - 📍 Asakusa Sta. | Dinner ¥10,000-14,999
  - 🍳 Ni-hachi Soba; omakase with garden vegetables. Private rooms ideal for families
  - 👨‍👩‍👧‍👦 Children explicitly welcome; private rooms available. ¥9,900 same-day course
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131102/13185027/)
- **Men Mitsui** ⭐ 3.83 (1,340 reviews) 💰 Budget [ENRICHED FULL] — Ramen
  - 📍 Tawaramachi Sta. | ¥1,000-1,999 | Michelin Bib Gourmand; English menu
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131102/13284327/)
- **Asakusa Sanboa** ⭐ 3.76 (377 reviews) 💰💰 Mid [ENRICHED MEDIUM] — Standing cocktail bar
  - Smoking allowed — not for families
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131102/13123270/)
- **BILLIKEN** ⭐ 3.75 (1,726 reviews) 💰 Budget [ENRICHED MEDIUM] — Ramen/Tsukemen
  - Near Kaminarimon Gate; kids plates available
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131102/13235761/)
- **LOOP TOKYO** ⭐ 3.75 (76 reviews) 💰💰💰 High [ENRICHED MEDIUM] — Creative omakase
  - Dinner ¥10,000-14,999; reservation only
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131102/13274915/)
- **Hatsu Ogawa** ⭐ 3.74 (744 reviews) 💰💰 Mid [ENRICHED MEDIUM] — Unagi (est. 1907)
  - Lunch/Dinner ¥4,000-5,000; reserve 10 days ahead. Cash only
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1311/A131102/13003702/)

---

## 7. Tokyo Harajuku

- **BLOCK HOUSE Suiyou Curry** ⭐ 3.85 (492 reviews) 💰💰 Mid [ENRICHED FULL] — Curry
  - ⚠️ WEDNESDAYS ONLY | Lunch 12:15-15:00; Dinner 17:30-19:30
  - 🍳 Rotating trio of curries; art gallery vibe. 17 seats. No reservations for first-timers
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1306/A130601/13183182/)
- **Tamawarai** ⭐ 3.85 (1,846 reviews) 💰💰 Mid [ENRICHED FULL] — Soba, Michelin 1 Star
  - Lunch ¥2,000-2,999 | Dinner ¥10,000-14,999 | Tabelog Bronze 10 consecutive years
  - ⚠️ NOT suitable for young elementary school children
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1306/A130601/13129390/)
- **YOGORO** ⭐ 3.79 (1,713 reviews) 💰 Budget [ENRICHED MEDIUM] — Spinach curry
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1306/A130601/13076645/)
- **Pretty Pork Factory & Katsu Puripo** ⭐ 3.78 (683 reviews) 💰💰 Mid [ENRICHED MEDIUM] — Shabu/Tonkatsu
  - 70 seats; semi-private rooms. Family-friendly
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1306/A130601/13295369/)
- **Minoringo** ⭐ 3.73 (1,834 reviews) 💰 Budget [ENRICHED MEDIUM] — Butter Chicken Curry
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1306/A130601/13108716/)
- **Takenoshita Soba** ⭐ 3.71 (115 reviews) 💰💰💰 High [ENRICHED MEDIUM] — Artisan soba
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1306/A130601/13286285/)
- **BLAKES for JOURNEY** ⭐ 3.71 (482 reviews) 💰 Budget [ENRICHED MEDIUM] — Revival of 1980s curry shop
  - Children welcome, strollers welcome, English menu
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1306/A130601/13195491/)
- **Enseigne d'angle** ⭐ 3.71 (691 reviews) 💰 Budget [ENRICHED MEDIUM] — Kissaten, cheesecake
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1306/A130601/13007015/)
- **Handmade Buckwheat Matsunaga** ⭐ 3.70 (624 reviews) 💰 Budget [ENRICHED MEDIUM] — Soba
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1306/A130601/13024514/)
- **Omotesando Ukai Tei** ⭐ 3.70 (1,030 reviews) 💰💰💰💰 Luxury [ENRICHED MEDIUM] — Teppanyaki
  - Lunch ¥10,000-14,999 | Dinner ¥20,000-29,999 | Private rooms; family-friendly
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1306/A130601/13044361/)

---

## 8. Tokyo Akihabara (20 restaurants)

### Ramen (13 restaurants, sorted by score)

- **Hotate Biyori** ⭐ 3.87 (1,265 reviews) 💰 Budget [ENRICHED FULL] — Scallop tsukemen
  - 📍 Akihabara Sta. | ¥1,000-1,999 | Tabelog Ramen TOKYO 100 (3 years)
  - 8 seats; complicated reservation system. Cash only
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1310/A131001/13280086/)
- **Mendokoro Honda** ⭐ 3.85 (3,312 reviews) 💰 Budget [ENRICHED FULL]
  - 📍 Akihabara Sta. | ¥1,000-1,999 | Tabelog Ramen TOKYO 100 (5 years)
  - 🍳 Tokusei Shoyu Tsukemen; English ticket machine. Children welcome. Reservations via TableCheck
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1310/A131001/13246285/)
- **Aoshima Shokudo** ⭐ 3.75 (3,471 reviews) 💰 Budget [ENRICHED MEDIUM] — Niigata-style ramen
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1310/A131001/13094776/)
- **Ramen Tenjinshita Daiki** ⭐ 3.75 (1,137 reviews) 💰 Budget [ENRICHED MEDIUM]
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1310/A131001/13208678/)
- **Spice Ramen Manriki** ⭐ 3.68 | **Ramen Tsumugi** ⭐ 3.64 | **Men ZIN Saito** ⭐ 3.62 | **Marusho Ramen** ⭐ 3.59 | **Gottsu** ⭐ 3.58 | **MAZERU** ⭐ 3.58 | **Iekei Bushouya Gaiden** ⭐ 3.58 | **Iekei Bushouya** ⭐ 3.57 | **Ramen Ninja** ⭐ 3.55

### Tonkatsu

- **Tonkatsu Marugo** ⭐ 3.76 (3,219 reviews) 💰 Budget [ENRICHED MEDIUM]
  - Yamagata San Gen Pork; 34 seats. Children welcome. Cash only
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1310/A131001/13000379/)

### Curry (3)

- **Ethiopia Curry Kitchen** ⭐ 3.67 | **Spice Curry Karikari** ⭐ 3.67 | **European Curry M** ⭐ 3.63

### Yakiniku

- **Tan Kiyo** ⭐ 3.62 (1,079 reviews) 💰💰💰 High — Beef tongue specialist

### Cafe (2)

- **The French Toast Factory** ⭐ 3.67 | **KIELO COFFEE** ⭐ 3.58

---

## 9. Tokyo Ginza / Tsukiji (17 restaurants)

### Ramen

- **Ginza Hachigo** ⭐ 3.93 (2,336 reviews) 💰 Budget [ENRICHED FULL]
  - 📍 Shintomicho Sta. | ¥1,000-1,999 | Michelin Bib Gourmand; formerly 1 Michelin Star
  - 🍳 French-inspired broth with duck, cured ham, scallops, dried tomatoes. 6 counter seats
  - ⚠️ Children of elementary school age or younger prohibited
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1301/A130101/13228602/)
- **Mugi to Olive** ⭐ 3.77 (4,432 reviews) 💰 Budget [ENRICHED MEDIUM] — Clam ramen with olive oil
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1301/A130101/13164932/)

### Tempura

- **Tempura Kondo** ⭐ 4.10 (1,098 reviews) 💰💰💰 High [ENRICHED FULL] ⚠️ ALREADY IN GUIDES (sushi-seafood-guide.html, calendar-planner.html)
  - 📍 Ginza Sta. | Lunch ¥10,000-14,999 | Dinner ¥20,000-29,999
  - 🏆 2 Michelin Stars; Tabelog Tempura 100
  - 🍳 Vegetable-forward tempura; 50+ year veteran Chef Kondo
  - 20 counter seats. Better for adults/older children
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1301/A130101/13004993/)

### Yakiniku (5 restaurants)

- **Edo Yakiniku** ⭐ 4.10 (178 reviews) 💰💰💰💰 Luxury [ENRICHED FULL]
  - 📍 Ginza Sta. | Dinner ¥33,000 course | 6 seats only. NOT for children
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1301/A130101/13270037/)
- **USHIGORO S. GINZA** ⭐ 4.08 (891 reviews) 💰💰💰💰 Splurge [ENRICHED FULL]
  - 📍 Ginza Sta. | Dinner ¥30,000-50,000+ | 58 seats, 11 private rooms
  - 👨‍👩‍👧‍👦 Children welcome; private rooms ideal for families. English service
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1301/A130101/13222093/)
- **Tokyo En** ⭐ 3.87 (429 reviews) 💰💰 Mid [ENRICHED FULL]
  - Dinner ¥8,000-9,999 — Outstanding value for Ginza. Retro hidden gem. Cash only
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1301/A130101/13002566/)
- **Setsugekka Ginza** ⭐ 3.83 (236 reviews) 💰💰💰 High [ENRICHED FULL]
  - Dinner ¥20,000-29,999; 12 counter seats; children welcome but 15+ preferred
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1301/A130101/13249568/)
- **Yakiniku Ginza Kobau** ⭐ 3.73 (1,036 reviews) 💰💰💰💰 Luxury [ENRICHED MEDIUM]
  - All private rooms; Mino Shabu exclusive dish
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1301/A130101/13005008/)

### Shabu-shabu

- **subin** ⭐ 4.23 (134 reviews) 💰💰💰💰 Luxury [ENRICHED FULL]
  - 📍 Ginza Sta. | Lunch ¥15,000-19,999 | Dinner ¥40,000-49,999
  - 🍳 Tajima Beef — available at only 13 restaurants in Japan
  - 👨‍👩‍👧‍👦 Children ONLY in private rooms; must order same course
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1301/A130101/13287203/)

### Chinese

- **GINZA JOTAKI** ⭐ 4.27 (70 reviews) 💰💰💰💰 Luxury [ENRICHED FULL]
  - Dinner ¥38,500-165,000; 10 counter seats. NOT for young children
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1301/A130101/13267801/)

### Curry

- **Spicy Curry House Ginza Hangetsu** ⭐ 3.75 (2,286 reviews) 💰 Budget [ENRICHED MEDIUM]
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1301/A130101/13246897/)

### Unagi

- **TAKAHASHIYA Ginza Ten** ⭐ 3.74 (417 reviews) 💰💰💰 High [ENRICHED MEDIUM]
  - 🍳 Premium eel; Michelin Selected; children welcome, English menu, wheelchair accessible
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1301/A130101/13262334/)

### Yoshoku

- **Shiseido Parlor** ⭐ 3.73 (1,280 reviews) 💰💰💰 High [ENRICHED MEDIUM]
  - Iconic omurice; Ginza institution since 1902. Children welcome, wheelchair accessible
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1301/A130101/13004938/)

### Cafe / Kissaten (4)

- **Tricolore Hon Ten** ⭐ 3.76 [ENRICHED MEDIUM] — Est. 1936; cloth-filter coffee
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1301/A130101/13007761/)
- **Juichibo Coffee Ten** ⭐ 3.76 [ENRICHED MEDIUM] — 11-coupon set ¥6,000
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1301/A130101/13007721/)
- **Sumibi Baisen Coffee Rin** ⭐ 3.73 [ENRICHED MEDIUM] — Charcoal-roasted coffee
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1301/A130101/13004102/)
- **YOU** ⭐ 3.72 (3,458 reviews) [ENRICHED MEDIUM] — Legendary fluffy omurice since 1970
  - 🔗 [Tabelog](https://tabelog.com/en/tokyo/A1301/A130101/13002318/)""")

    sections.append("""
---

## 10. Kyoto Arashiyama (10 restaurants)

- **Tempura Matsu** ⭐ 3.80 (297 reviews) 💰💰💰 High [ENRICHED FULL]
  - 📍 Matsuo Taisha Sta. | Lunch ¥20,000-29,999 | Dinner ¥30,000-39,999
  - 🏆 Tabelog Award Silver/Bronze (2017-2022); Tempura 100
  - 🍳 Inventive kaiseki — "onsen uni" in warm yuba; massive tempura oyster. Family-run 50+ years
  - 👨‍👩‍👧‍👦 Private rooms available. Cash only
  - 🔗 [Tabelog](https://tabelog.com/en/kyoto/A2601/A260403/26001461/)
- **Unagiya Hirokawa** ⭐ 3.69 💰💰💰 — Eel | **Shorai An** ⭐ 3.60 — Tofu
- **Inoue** ⭐ 3.60 — Izakaya | **Ramen Senmon Ten Daiki** ⭐ 3.57 💰 Budget — Ramen
- **Wagyu Volcano OAGARI** ⭐ 3.57 💰💰 — Meat donburi | **Shigetsu** ⭐ 3.57 💰💰 — Buddhist veg
- **Sagano Yu** ⭐ 3.56 💰💰 — Cafe in converted bathhouse | **Yamamoto** ⭐ 3.56 — Kissaten
- **Unagi Issei** ⭐ 3.54 💰💰💰 — Eel

---

## 11. Kyoto Fushimi (12 restaurants)

- **Honkaku Teuchi-Udon Taiga** ⭐ 3.72 (868 reviews) 💰 Budget [ENRICHED MEDIUM] — Udon
  - 🍳 Hand-made udon, curry udon, tempura. Children welcome; kids chairs available
  - 🔗 [Tabelog](https://tabelog.com/en/kyoto/A2601/A260601/26020260/)
- **Tsukemen Kirari** ⭐ 3.67 💰 | **Ganko Men** ⭐ 3.63 💰 | **Tokusei Ramen Daichu** ⭐ 3.59 💰
- **Ramen So Chikyu** ⭐ 3.57 | **Fushimi Sakagura Koji** ⭐ 3.57 — Sake bar
- **Oden Senmon Ten Bengaraya** ⭐ 3.57 — Oden | **Teuchi Udon Kendonya** ⭐ 3.54
- **Daikoku Ramen** ⭐ 3.54 | **Ramen Ginkaku** ⭐ 3.54 | **Seabura no Kami** ⭐ 3.54 | **Ramen Tanukiya** ⭐ 3.54

---

## 12. Osaka Umeda (13 restaurants)

### Kushikatsu

- **Kushikatsu Daibon** ⭐ 4.09 (218 reviews) 💰💰💰 High [ENRICHED FULL]
  - 📍 Naniwabashi Sta. | Dinner ¥15,000-20,000+
  - 🍳 19-piece omakase kushikatsu; offshoot of #1-ranked Aabon
  - 👨‍👩‍👧‍👦 Children explicitly welcome; kids menu; strollers OK. Book the private room
  - 🔗 [Tabelog](https://tabelog.com/en/osaka/A2701/A270101/27119483/)

### Yakitori (3)

- **Yakitori Ichimatsu** ⭐ 3.96 (805 reviews) 💰💰💰 High [ENRICHED FULL]
  - Michelin 1 Star; Hinai Jidori chicken. Children welcome during 16:00-18:00 only
  - 🔗 [Tabelog](https://tabelog.com/en/osaka/A2701/A270101/27013209/)
- **Yakitori Shidare** ⭐ 3.93 💰💰💰 High [ENRICHED FULL] — Kyoto chicken, Kishu Duck
  - 🔗 [Tabelog](https://tabelog.com/en/osaka/A2701/A270101/27147023/)
- **Shinhaku** ⭐ 3.92 💰💰💰 High [ENRICHED FULL] — Yakitori 100 (4 consecutive years)
  - 🔗 [Tabelog](https://tabelog.com/en/osaka/A2701/A270101/27122059/)

### Ramen

- **Mugi to Mensuke** ⭐ 3.90 (2,220 reviews) 💰 Budget [ENRICHED FULL]
  - 📍 Nakatsu Sta. | Under ¥999 | Michelin Bib Gourmand; Ramen OSAKA 100 (7 consecutive years)
  - 🍳 Kuradashi Shoyu Soba — "unrivalled perfection." 1+ hour queue expected. Cash only
  - 🔗 [Tabelog](https://tabelog.com/en/osaka/A2701/A270101/27104891/)
- **Ramen Yashichi** ⭐ 3.76 (1,893 reviews) 💰 Budget [ENRICHED MEDIUM] — Chicken paitan
  - 🔗 [Tabelog](https://tabelog.com/en/osaka/A2701/A270101/27015342/)
- **Osaka Mentetsu** ⭐ 3.72 (2,216 reviews) 💰💰 Mid ⚠️ URL redirect issues — verify before visiting
  - 🔗 [Tabelog](https://tabelog.com/en/osaka/A2701/A270101/27074083/)

### Curry

- **BOTANI:CURRY Umeda** ⭐ 3.80 (1,662 reviews) 💰 Budget [ENRICHED FULL]
  - 📍 Hanshin Dept Store 9F | Lunch ¥1,000-1,999 (no dinner)
  - 🍳 Instagram-worthy plate; timeslot ticket system from 10am. Family-friendly, mild spice available
  - 🔗 [Tabelog](https://tabelog.com/en/osaka/A2701/A270101/27125687/)
- **Kyu Yamu Tetsudo** ⭐ 3.72 (2,873 reviews) 💰 Budget [ENRICHED MEDIUM] — Creative monthly-changing curry
  - 🔗 [Tabelog](https://tabelog.com/en/osaka/A2701/A270101/27072441/)

### Udon (4)

- **Udon Bo** ⭐ 3.77 💰 [ENRICHED MEDIUM] | **Takeuchi Udon** ⭐ 3.77 💰 [ENRICHED MEDIUM]
- **Udonya Kisuke** ⭐ 3.76 💰💰 [ENRICHED MEDIUM] | **Umeda Kamatake** ⭐ 3.76 💰 [ENRICHED MEDIUM]

### Other

- **epais** ⭐ 3.72 (912 reviews) 💰💰 Mid [ENRICHED MEDIUM] — Premium tonkatsu
  - 🔗 [Tabelog](https://tabelog.com/en/osaka/A2701/A270101/27084538/)
- **Yakiniku Futoro** ⭐ 3.75 💰💰💰 [ENRICHED MEDIUM] — Smoking allowed; not for families
- **Satsuma** ⭐ 3.73 💰💰 [ENRICHED MEDIUM] — Value yakiniku""")

    # ==================== DAY TRIPS ====================
    sections.append("""
---
---

# DAY TRIPS (3.30+ threshold)

---

## 13. Nara (~25 restaurants)

> Removed: Kitsune (closure undetermined), Oryori Tomiyama (permanently closed — note: this was in Kamakura raw but Nara enriched shows a different Oryori Tomiyama in Yokohama which was closed)
> URL issues: Toi Inshokuten (redirect), Izumo Soba Dandan (redirect to closed restaurant)

### Soba / Udon

- **Gen** ⭐ 3.96 (537 reviews) 💰💰 Mid [ENRICHED FULL] — Michelin 1 Star
  - 📍 Kintetsu Nara Sta. (16 min walk) | Lunch ¥3,000-5,000 | Dinner ¥8,000-12,000
  - 🍳 Stone-ground soba with sake-brewing water; tatami rooms overlooking garden
  - 👨‍👩‍👧‍👦 Tatami works for kids; serene atmosphere. Cash only. Reservation required (phone, Japanese)
  - 🔗 [Tabelog](https://tabelog.com/en/nara/A2901/A290101/29000710/)
- **Soba Dokoro Kitahara** ⭐ 3.60 💰 | **Soba Kiri Momoyo Zuki** ⭐ 3.59 💰💰

### Ramen (7+ restaurants)

- **Menya K** ⭐ 3.70 (775 reviews) 💰 Budget [ENRICHED MEDIUM] — Ramen WEST Top 100
  - 📍 Kintetsu Nara Sta. | Under ¥999 | 11 seats. Children welcome. Cash only
  - 🔗 [Tabelog](https://tabelog.com/en/nara/A2901/A290101/29011962/)
- **Men Shokudo 88** ⭐ 3.68 💰 | **Chuka Soba Oshitani** ⭐ 3.67 💰 | **Menya Eguchi** ⭐ 3.67 💰
- **Mutekko Shabaton** ⭐ 3.63 💰 | **Buta Soba Ichibo** ⭐ 3.60 💰 | **Menmen Musubi** ⭐ 3.60 💰 | **Minami Shokudo** ⭐ 3.59 💰

### Other Notable

- **Toi Inshokuten** ⭐ 3.74 💰💰 — Indian curry ⚠️ URL redirect; verify before visiting
- **Poku Poku** ⭐ 3.68 💰💰 — Tonkatsu
- **Yakitori Mochizuki** ⭐ 3.65 💰💰💰 | **Nara** ⭐ 3.64 💰💰💰 — Izakaya
- **Awa Naramachi** ⭐ 3.63 — Regional | **Yakiniku Hachina** ⭐ 3.63 💰💰 — Yamagata beef
- **Wakakusa Curry Honpo** ⭐ 3.63 💰 — Curry | **Chinese Ryouri Shijin** ⭐ 3.62 💰💰 — Chinese
- **Momoshiki** ⭐ 3.61 💰💰 — Sukiyaki | **Una Kiku** ⭐ 3.67 💰💰 — Unagi (130 years)
- **Kanakana** ⭐ 3.59 — Cafe | **Rokumei Coffee** ⭐ 3.58 💰 — Specialty coffee

---

## 14. Himeji (~40 restaurants, 3.30+ threshold)

> Full details in tabelog-raw-daytrips-a.md. Strong in: ramen, tonkatsu, oden, anago. Key picks:

- **Eiyo Ken** ⭐ 3.65 💰💰 — Himeji gyoza legend
- **Hamamoto Coffee** ⭐ 3.62 💰 — Beloved coffee institution
- **Tonkatsu Saku** ⭐ 3.60 💰💰 | **Sumibi Yaki Danshu** ⭐ 3.59 💰💰💰 — Anago/yakitori
- **Shinsei Ken** ⭐ 3.58 💰 — Old-school Himeji ramen | **Himeji Tanmen** ⭐ 3.58 💰
- **Cafe Domusshu** ⭐ 3.58 💰 — Famous almond butter toast
- **Sumiyaki Anago Yamayoshi** ⭐ 3.49 💰 — Charcoal-grilled conger eel, must-visit
- **Himeji Takopi** ⭐ 3.49 💰 — Akashiyaki
- **Maneki no Eki Soba** ⭐ 3.46 💰 — Iconic platform soba at Himeji Station
- Himeji specialties: Anago (conger eel), Oden (ginger soy style), Ekisoba (station platform soba)

---

## 15. Kamakura (18 restaurants, 3.30+ threshold)

> Removed: Oryori Tomiyama (permanently closed)

### Soba (5)

- **Kamakura Matsubara An** ⭐ 3.67 (1,641 reviews) 💰 | **Teuchi Soba Chihana An** ⭐ 3.67 💰
- **Kamakura Kitahashi** ⭐ 3.62 💰💰 | **Karasumi Soba Tsuki to Matsu** ⭐ 3.60 💰💰
- **Soba Sake Seikaiha** ⭐ 3.57 💰💰

### Curry (5) — Kamakura is a curry destination

- **OXYMORON komachi** ⭐ 3.67 (1,227 reviews) 💰 — Most famous curry shop
- **Caraway** ⭐ 3.63 (1,479 reviews) 💰 — Classic old-school, under ¥999
- **Sango Sho** ⭐ 3.60 💰💰 — Ocean-view | **Moana Makai** ⭐ 3.59 💰💰 — Ocean views
- **Ginza Furukawa** ⭐ 3.56 💰

### Other

- **Iwata Coffee Ten** ⭐ 3.69 (1,527 reviews) 💰 — Legendary 1948 kissaten, thick hotcakes
- **Kikuta** ⭐ 3.66 💰💰💰 — Izakaya/Seafood
- **Cafe Vivement Dimanche** ⭐ 3.65 💰 — Freshly roasted coffee
- **Kamakura Sasho** ⭐ 3.62 — Sukiyaki/Shabu-shabu
- **Oishi** ⭐ 3.60 💰💰💰 — Tempura | **Akimoto** ⭐ 3.56 💰💰 — Tempura bowls
- **Pho RASCAL** ⭐ 3.56 💰 — Vietnamese | **Teppanyaki Shichirigahama** ⭐ 3.56 💰💰💰
- **Tsuruya** ⭐ 3.56 💰💰💰 — Unagi | **Kakan** ⭐ 3.55 💰💰 — Chinese

---

## 16. Yokohama Chinatown (32 restaurants, 3.30+ threshold)

> Full details in tabelog-raw-daytrips-b.md. All Chinese/dim sum unless noted.

### Top Picks

- **Goku Chasou** ⭐ 3.71 (1,161 reviews) 💰 Budget [ENRICHED MEDIUM] — Chinese tea cafe, pork buns
  - 30+ tea varieties; reservations weekdays only. Children welcome
  - 🔗 [Tabelog](https://tabelog.com/en/kanagawa/A1401/A140105/14000153/)
- **Juraku** ⭐ 3.71 (822 reviews) 💰 Budget [ENRICHED MEDIUM] — Chinese sweets, steamed buns
  - Takeout only; 50+ years. Marai-ko steamed sponge cake
  - 🔗 [Tabelog](https://tabelog.com/en/kanagawa/A1401/A140105/14010383/)
- **Elena** ⭐ 3.68 💰 — Kissaten
- **Saiko Shinkan** ⭐ 3.66 💰💰 — Dim sum | **Kinryo** ⭐ 3.66 💰
- **Shiokumizaka Ebina** ⭐ 3.63 💰💰💰 — Yakitori
- **Yakiniku Torachan** ⭐ 3.60 💰💰💰 — Yakiniku
- **Aichun** ⭐ 3.60 💰 | **Shatenki** ⭐ 3.57 💰 | **Keitokuchin** ⭐ 3.56 💰 — Mapo Tofu
- **Shatenki Nigo** ⭐ 3.56 💰 — 60-year congee specialist
- **Shigekichi** ⭐ 3.55 💰💰 — Female wagyu specialist yakiniku
- **Spice Curry Stand Washin** ⭐ 3.51 💰 — Curry | **Shu Mien** ⭐ 3.48 💰 — Taiwanese

---

## 17. Hakone (21 restaurants, 3.30+ threshold)

### Top Picks

- **Unagi Tei Tomoei** ⭐ 4.39 (3,428 reviews) 💰💰 Mid [ENRICHED FULL] — Top-rated in all Hakone
  - 📍 Kazamatsuri Sta. | ¥8,000-9,999 | Walk-in queue (no regular reservations)
  - 🏆 Tabelog Award Silver (4 consecutive years); #1 unagi in Japan by reviews
  - 🍳 Unaju with proprietary secret sauce; underground spring water charcoal preparation
  - 👨‍👩‍👧‍👦 VERY family-friendly — all ages welcome, strollers OK, tatami+private rooms, 32 parking spaces
  - 🔗 [Tabelog](https://tabelog.com/en/kanagawa/A1410/A141001/14001626/)

- **Menan Chitose** ⭐ 3.80 (636 reviews) 💰 Budget [ENRICHED FULL] — Ramen
  - 📍 Kazamatsuri Sta. | ¥1,000-1,999 | Ramen KANAGAWA 100
  - 🍳 Tokusei Shoyu Ramen; also excellent Tantanmen. Mom-and-pop cafe atmosphere
  - 🔗 [Tabelog](https://tabelog.com/en/kanagawa/A1410/A141001/14083221/)

- **Takeyabu** ⭐ 3.67 💰💰 — Soba | **Amazake Chaya** ⭐ 3.67 💰 — Historic teahouse
- **Restaurant Cascade** ⭐ 3.62 💰💰 — Fujiya Hotel yoshoku
- **Aihara Seiniku Ten** ⭐ 3.62 💰💰 — Street food croquettes
- **Hatsu Hana** ⭐ 3.49 (2,039 reviews) 💰 — Popular soba
- **Tamura Ginkatsu Tei** ⭐ 3.49 (1,338 reviews) 💰 — Tonkatsu
- **Yubadon Naokichi** ⭐ 3.49 (1,265 reviews) 💰 — Tofu/yuba donburi
- **Nisshin Tei** ⭐ 3.49 | **Gyoza Center** ⭐ 3.47 | **Tsukumo** ⭐ 3.48 — Soba
- **Irori Saryo Hachiri** ⭐ 3.46 | **Garou Kissa Utrillo** ⭐ 3.46 | **Irori Ya** ⭐ 3.46
- **Pan no Mimi** ⭐ 3.50 | **Gongen Karame Mochi** ⭐ 3.55 | **Mori Meshi** ⭐ 3.46

---

## 18. Kinkakuji / North Kyoto (33 restaurants, 3.30+ threshold)

> Full details in tabelog-raw-daytrips-b.md. Key picks:

### Top Picks

- **Yamazaki Menjiro** ⭐ 3.70 (923 reviews) 💰 Budget [ENRICHED MEDIUM] — Ramen WEST 100
  - 📍 Emmachi Sta. | Under ¥999 | 9 counter seats. Cash only
  - 🔗 [Tabelog](https://tabelog.com/en/kyoto/A2601/A260501/26008681/)
- **Ebata** ⭐ 3.68 💰💰💰 — Yakiniku/tripe
- **Kitchen Papa** ⭐ 3.65 💰 — Yoshoku, hamburger steak
- **Tenjaku** ⭐ 3.65 💰💰💰 — Tempura | **Ito Sen** ⭐ 3.65 💰💰 — Chinese
- **Soba Shubo Ichii** ⭐ 3.60 💰 — Soba | **Shizuka** ⭐ 3.54 💰 — Kissaten, pancakes
- **Dandelion** ⭐ 3.53 | **Nishijin Toriiwa Rou** ⭐ 3.51 — Oyako-don
- **Toyouke Chaya** ⭐ 3.50 💰 — Tofu dishes near Kinkakuji
- 9 ramen shops ranging 3.35-3.70
- Multiple soba/udon options (3.34-3.60)
- Yoshoku (Kitchen Papa ⭐ 3.65, ITADAKI ⭐ 3.42, Kinkakuji Itadaki ⭐ 3.40)

---

*End of compiled Tabelog research file. Source files: 9 raw scrapes + 4 enriched-full + 4 enriched-medium = 17 files total.*
""")

    # Write the full file
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(sections))

    print(f"Written to {OUTPUT}")
    print(f"Total size: {os.path.getsize(OUTPUT):,} bytes")

if __name__ == '__main__':
    write_file()
