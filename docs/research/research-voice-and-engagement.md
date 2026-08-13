# Voice & Engagement — Implementation Reference

Scope: Uzbek Latin register (posts vs comments), orthography, MT-tell detection, engagement mechanics ranked by evidence strength. Target system: Uzbek AI-education Telegram channel (3000+ members) + quiet linked discussion group, 2 posts/day 10:00 & 21:00 Asia/Tashkent (UTC+5), Python + Postgres on Hostinger VPS, $50–150/mo.

---

## 1. UZBEK POST REGISTER

### 1.1 Structural template (from @mohirdev, the closest high-quality analogue)

```
<ONE topical lead emoji> <bold one-line hook>
<1–2 sentence body, sentence case>
[optional em-dash bullet list, each item ending in ';']
👉 <single short CTA line>
```

Observed lead emoji set on @mohirdev: 📥 📈 📁 😵 🚀 👾 🎉 🦾 📄. In-body emoji density ≈ zero. `👉` prefixes the CTA line — dominant Uzbek tech-channel convention.

Bullet form, verbatim: `— Odoo kompaniyasi tasdiqlangan oʻquv dasturi;` (em dash U+2014, semicolon terminator).

Channel-type calibration:
- Professional tech (@mohirdev): 1 lead emoji + 👉 CTA, nothing else. **Use this.**
- Edtech/promo (@ustozai): denser, 🚀🏆🎓⚡️🚗🤔❗️, often one per line.
- News (@kunuz): zero emoji in headlines.

### 1.2 Rules

- Sentence case. Correct oʻ/gʻ and tutuq belgisi. Near-zero typos.
- Politeness = `-ing`/`-ingiz` respectful imperative, NOT formal vocabulary: `oling, yozing, boring, oʻtiring, koʻring, kelingizlar` (`-ingiz` respect + `-lar` plural).
- Casualness = short sentences, direct questions, `— ` dashes. NOT dialect words, NOT slang.
- Uzbek is pro-drop and verb-final. Do not emit `biz/siz/u` in every clause.
- At most ONE particle per post (budget, not sprinkle).
- Hard cap 4,096 chars; 1,024 if sent as a media caption. (Premium: 8,192 / 4,096 — irrelevant for a bot.)
- Paragraph breaks mandatory (87.9% of surveyed TG readers react negatively to unbroken long posts).

### 1.3 Verified example lines (verbatim from live channels)

```
Sizningcha, Changan bilan qanday loyiha eng foydali boʻlardi?
Oramizda talabalar ham bormi? 🤔
Oʻqish bilan birga ishlashni rejalashtiryapsizmi?
Agar siz ham gid boʻlib daromad qilishni istasangiz — bu kurs aynan siz uchun
Videodagi usullarni sinab sunʼiy intellektdan sifatli javoblar oling.
Batafsil videoda tomosha qiling.
Kimga kerak boʻlsa @javohircoder ga «Gemini pro 18 oy» deb yozing.
Odooʼni uning oʻzi tasdiqlangan kursda oʻrganing.
👉 SI hafta yangiliklari
Fikringizni izohlarda yozib qoldiring!
Izohda fikringizni yozib qoldiring!
Izohlarda ismingiz, qaysi tilni oʻrganayotganingiz ... yozib qoldiring
Sizningcha, Photoshopni bilish bugungi kunda ahamiyatlimi?
```

`Sizningcha, ...?` is the workhorse engagement opener. `SI` = @mohirdev's Uzbek abbreviation for *sunʼiy intellekt*.

### 1.4 Number / date / time / currency formatting (generate in CODE, never let the LLM format)

| Item | Correct | MT/LLM default (wrong) |
|---|---|---|
| Date | `2023-yil 25-sentabr`, `2026-yil 12-avgust` | `25 sentyabr 2023` |
| Month names | sentabr, oktabr, noyabr, dekabr | sentyabr, oktyabr, noyabr, dekabr |
| Issue no. | `5-son`, `25-Iyul` | `son 5` |
| Time | `soat 20:45 da`, `soat beshgacha` | `20:45 da` |
| Currency | `100 million soʻm`, `10 soʻmlik chiptani` (lowercase after numeral) | `100 million Soʻm` |
| Latin brand + suffix | `Odooʼni`, `OpenAIʼning`, `Google'ning`, `Qwen 3.8 Max'ni`, `Ustoz AI'da`, `video'ning` | `Google ning` / `Googlening` |

The scheduler already knows Tashkent time (UTC+5) — inject formatted strings.

---

## 2. UZBEK COMMENT REGISTER (strictly separate agent)

Empirical base: `risqaliyevds/uzbek-sentiment-analysis` on HuggingFace, 352,151 Uzum Market comments.

### 2.1 Hard style contract

| Dimension | Comment agent | (Post agent, for contrast) |
|---|---|---|
| Length | 1–8 words, cap ~10 | 1–3 sentences |
| Capitalization | all lowercase, incl. sentence start | sentence case |
| Terminal punctuation | optional / often absent | required |
| Apostrophes | may be dropped (`zur`, `zor` for `zoʻr`) | correct U+02BB/U+02BC |
| Emoji | no emoji-as-bullet; sparse | 1 lead + 👉 |
| Structure | none | hook/body/bullets/CTA |
| Particles | up to 2 | max 1 |
| Typos | tolerated (see 2.3) | never |

**Never share a system prompt between the two agents.** A single "Uzbek informal" prompt produces mid-register text wrong for both surfaces.

### 2.2 Verbatim corpus samples

```
rahmat, juda yoqdi!
shuni qoygandan keyin maza qildik
rahmat zor ekan
super
ajoyib maxsulot
narxi super
zo'r ekan
osh zur chikdi !
ajoyib
arzon va sifatli
yaxshi ekan.
orqa tor, oldi keng shalvirab g'alati ko'rinyapti
zur
bu qo'lda yasalganmi?
zamogi yaxshi emas ekan
ajoyib...
```

Observable micro-features: stray space before `!` (`chikdi !`), `...` ellipsis common, Russian nouns nativized with Uzbek possessives (`zamogi` = замок 'zipper' + `-i`).

### 2.3 Attested human error types (imitate ONLY these, never random noise)

- `q → k`: `chikdi` for `chiqdi`
- dropped oʻ/gʻ diacritic: `zur` / `zor` for `zoʻr`
- `x/h` substitution: `Ohirgi` for `Oxirgi` (observed on @kadirovDev). Canonical direction: `h` written for `x` (`hoto` for `xato`). Recognized high-frequency Uzbek error class — **qualitative only, no percentage exists** (see §11).
- metathesis: `firk` for `fikr` (@kadirovDev: `Kim qo'shiladi shu firkga?`)
- Turkish-influenced plural: `talabları` for `talablari` (@kadirovDev: `Ohirgi video'ning texnik talabları`)

### 2.4 Reply patterns

**Agreement / praise:**
```
zo'r-ku
rozi, shunday
qoyil
ha, aynan shunday
menam shunaqa o'ylagandim
```
Register note: `qoyil` praises the *agent/achievement* ("bravo, well done"); `zoʻr / ajoyib / super` evaluate the *object*. So a bot replying to a member's answer should use `qoyil`; a bot describing its own content must not (self-praise).

**Disagreement (softened, `siz`-compatible):**
```
menimcha unday emas-ku
lekin shunda ham qiyin bo'ladi-da
hammasi ham unaqa emas
```
Uses `-ku` (gentle "but you know") and `-da`, not blunt negation.

**Joke / light tag:**
```
hahah zo'r-a?
voy bu jiddiy-ku 😄
menam o'shanaqa qilgandim :)
```

**Prompting a newcomer (Arguello-style: question + on-topic + low complexity):**
```
qaysi modelni ishlatyapsiz?
bitta misol yozib yuboring-chi
sizda qanday chiqdi?
```

### 2.5 Particle hyphenation — hard, checkable rule

Source formulation (Mengliyev & Xaliyarov 2018:233): *"Bu koʻrinishdagi yuklamalar; -mi, -gina, -kina, -qina (gʻina), -oq/-yoq, -ov/-yov soʻzga qoʻshilib yoziladi. -chi, -ku, -da, -e, -a/-ya, -u/-yu, -ey/-yey yuklamalari esa chiziqcha bilan yoziladi."*

- **JOINED, no hyphen:** `-mi`, `-gina/-kina/-qina` (dial. `-gʻina`), `-oq/-yoq`, `-ov/-yov`
- **HYPHENATED:** `-chi`, `-ku`, `-da`, `-e`, `-a/-ya`, `-u/-yu`, `-ey/-yey`
- **SEPARATE WORDS:** `axir`, `faqat`, `nahotki`, `hattoki`, `xuddi`, `ham`, `esa`

Correct: `zoʻr-da`, `shunday-ku`, `bormi`. Wrong: `zoʻrda`, `shundayku`, `bor-mi`.
Critic tuning: hyphenless `-mi` (`bor-mi`) = ERROR. Joined `-ku`/`-chi` (`dedimku`, `qoʻyingchi`) = informal-acceptable, real writers do it.

### 2.6 Particle functions with attested examples

| Particle | Function | Attested examples |
|---|---|---|
| `-chi` | question + request/urging, softened imperative | `Otabekni-chi?`, `Undan keyin-chi?`, `bizga choy qaynatib bersangiz-chi!`, `Qoʻyingchi...`, `Koʻray-chi`, `Bir narsa desang-chi` |
| `-ku` | emphasis / "but you know", mild contradiction | `Hali yoshqa oʻxshaysiz-ku`, `Necha marta uchrashay dedimku` |
| `-da` | emphatic "you see/obviously"; also sequencing "and then" | `Oʻz qizingiz-ku, tengini topib bering-da!`, `qarab qoʻydi-da daqiqa ichida koʻrinmas boʻlib ketdi` |
| `-a / -ya` | surprise / agreement-seeking tag question | `Bu gap oramizda qolsin-a!`, `jonim chiqib ketdi-ya!`, `Bu gaping toʻgʻri-ya` |
| `-mi` | plain question, attaches directly | `Bu kitobni oʻqidingizmi?` |
| `-oq / -yoq` | immediacy | `oʻqib tugatmasdanoq` |
| `-gina` | only/just; diminutive-affectionate | `sekingina`, `yaxshigʻina`, `ohistagʻina` |

Highest value for a friendly bot: `-da` (warm obviousness), `-ku` (gentle correction), `-chi` (CTA softener: `yozib yuboring-chi`), `-a/-ya` (`zoʻr-a?`).

---

## 3. WORD LISTS

### 3.1 Russian loanwords — three tiers by writability

**TIER 1 — fully naturalized, safe in written Uzbek, not perceived as Russian:**
`kompyuter, telefon, avtobus, universitet, direktor, kompaniya, proyekt, planshet, magazin, sifat, marafon, promokod, start, klub, super`

**TIER 2 — spoken colloquialisms that do appear in casual writing, mild:**
`super, klass` ('cool'), `normalno`, `davay`

**TIER 3 — spoken discourse markers. DO NOT SHIP.**
`karoche, prosto, voobshe, zato, konechno, ladno, tipa, xarosh, kstati, znachit`

Tier-3 status after verification:
- `karoche` **IS attested in written Uzbek-matrix text** — 2 independent sources: Dilnoz, "Ay yay yay" published lyrics (`Karoche bo'ldi / Sabr kosasi to'ldi`, https://lyricstranslate.com/en/dilnoz-ay-yay-yay-lyrics) and a Letterboxd Uzbek film review (user masterofcrying, film "Dacha" 2026, https://letterboxd.com/film/dacha-2026/): `boshida manimcha yaxshi ketyotgandi, manu bachalar karoche gunohlariga ko'ra o'lishyapti deb o'ylagandim, shahvat, ochko'zlik bla bla deb turgan joyimda film o'zbekistonda olinganini bildirib qo'ydi` (note surrounding colloquial forms: `manimcha`, `bachalar`, `ketyotgandi`, `bla bla`). Weak third: translate.com carries `karoche` as an Uzbek headword (https://www.translate.com/dictionary/uzbek-english/karoche-4456833, machine-generated).
- **But both attestations are *sen*-register youth/snark writing** (pop lyrics, film-review sarcasm), not *siz*-register educational. Attested ≠ appropriate. **Ship none of the seven in the siz-register generator.** If a Russian-flavored casual marker is ever wanted, `karoche` is the only one with written evidence and belongs in COMMENT voice only, never in the 10:00/21:00 channel posts.
- The other six (`prosto, voobshe, zato, konechno, ladno, tipa`) have **zero** written-Uzbek attestations across targeted searches. Decisive negative: full-text string counts on the Turkophone code-switching PDF (dergipark article-file 4044388) returned karoche 0, koroche 0, prosto 0, voobshe 0, voobshche 0, zato 0, konechno 0, ladno 0, tipa 0, davay 0, znachit 0.
- The only Russian tag with a scholarly citation is sentence-final `da`: *"The use of the Russian tag 'da' at the end of an Uzbek sentence is a common feature in everyday speech"* — example `Bu juda qiyin masala, da?`

**Native Uzbek equivalents — use these by default:**

| Russian marker | Uzbek default |
|---|---|
| karoche | `qisqasi` / `xullas` |
| prosto | `shunchaki` |
| voobshe | `umuman` |
| konechno | `albatta` |
| ladno | `mayli` |
| davay | `qani` / `yur` |
| tipa | `degandek` / `kabi` |
| zato | `lekin` / `ammo` / `buning evaziga` |
| znachit | `demak` |

### 3.2 Positive evaluatives / interjections — allowlist

**Verified in real Uzbek text:** `zoʻr` (written zoʻr/zo'r/zur/zor — extremely frequent), `ajoyib`, `super`, `yaxshi`, `maza qildik`, `rahmat`, `arzon va sifatli`.

**Verified as standard interjections (grammar/dictionary):** `voy` (surprise/dismay), `ha`, `axir` (separate word), `qani`.

**`qoyil` — lexically confirmed, frequency unconfirmed.** https://izoh.uz/word/qoyil gives it as both *sifat* and *undov soʻz*: "Zavqlanib yoki tan berib, ofarin oʻqishga, tasanno aytishga arzirli", examples `Qoyil ish. Qoyil odam`; interjection sense glossed "Ofarin, tasanno"; productive family `qoyil qolmoq/boʻlmoq` ("Bu ishga barcha qoyil qolmoqda"), `qoyil qilmoq`, `qoyil qoldirmoq`. No Uzbek Telegram-comment corpus exists to settle frequency. **Design action: put `qoyil` in the bot's positive-sentiment RECOGNITION lexicon; do not weight it as a high-frequency generator output.**

**`top` — HARD-EXCLUDE.** https://izoh.uz/word/top returns ONLY the verb stem `top-` (topmoq) with seven senses (find lost thing, accidentally obtain, discover via investigation, identify unknown, acquire through work, occur/manifest as in `tashkil topmoq`, consider/deem). No adjectival/evaluative sense. Extra hazard: bare `top` as praise collides with `topdi/topding/topdingiz` in an Uzbek reader's parse. Exclude from generator vocabulary, not merely defer.

### 3.3 Street-slang DENYLIST (off-brand and in several cases insulting for a *siz*-register educational channel)

`gʻijim, olmaxon, quyon, jirafa, yedirdi, saqich, patina yuldi, qulogʻiga tepdi, bortini berdi, sigir, stalba, strelka belgiladi, mashinasi beton`
(`klass` = 'cool' is the only mild one.) Source: Modern Science and Research, https://inlibrary.uz/index.php/science-research/article/view/30025

### 3.4 Tashkent colloquial dial

**Safe mild-casual in writing:** `qanaqa` (for literary `qanday`), `shunaqa`, `baribir`, `eplab`, `Manashu` (< mana shu, observed on @kadirovDev), contracted progressive in questions (`rejalashtiryapsizmi?`).
**Spoken-only, exclude from posts:** `kelvoldi` (< kelib oldi), `aytvordi`.
Note: Tashkent dialect is the Qarluq variety closest to literary Uzbek and was the main input to 20th-c. standardization — a "Tashkent voice" needs LESS dialectal marking than assumed. Casualness comes from syntax and particles.

---

## 4. ORTHOGRAPHY RULES

### 4.1 Two different characters, two different jobs

- **U+02BB MODIFIER LETTER TURNED COMMA (ʻ)** — the "okina". Used in **Oʻ / Gʻ** (Cyrillic Ў/Ғ). Examples: `boʻladi`, `oʻrganing`, `yoʻlga qoʻyganmiz`, `koʻrsatish`, `qoʻllab`.
- **U+02BC MODIFIER LETTER APOSTROPHE (ʼ)** — *tutuq belgisi*, glottal stop / vowel-length mark. Examples: `sunʼiy`, `taʼlim`, `maʼno`, `sanʼat`, `aʼzo`, `maʼlum`.

They are visually mirrored. **A blanket "replace all apostrophes with U+02BB" post-processor corrupts `sunʼiy` → `sunʻiy` and is worse than leaving straight quotes.** Implement lexicon-aware replacement with an explicit tutuq-belgisi wordlist.

1995 alphabet: 29 letters (A B D E F G H I J K L M N O P Q R S T U V X Y Z Oʻ Gʻ Sh Ch) plus Ng. The apostrophe is NOT a separate letter.

### 4.2 What people actually type

Nobody types U+02BB/U+02BC — Windows Uzbek Latin layouts don't expose them. Common substitutes: **U+0027** straight `'`, **U+2018** `‘`, **U+2019** `’`. Most Uzbek websites including some government sites use U+2018 or U+0027. Fourth sloppy variant in the wild: grave-accented vowel — Texnokun.uz wrote `Qurbon hayiti muborak bòlsin!` (`ò` for `oʻ`).

**Real premium channels are inconsistent.** @mohirdev has `boʻladi / oʻrganing / sunʼiy / yoʻlga qoʻyganmiz / aʼzosi` (correct U+02BB/U+02BC) in the same post set as `ta'lim` and `o'quv` (U+0027). Texnokun mixes `koʻrsatish/qoʻllab` with `ko'rsatadigan` across adjacent posts.

**Style space:**
- U+0027 everywhere = NORMAL and human.
- U+02BB/U+02BC correctly = CORRECT and premium (slightly super-human but safe).
- RANDOM MIXING within one message = the tell of copy-paste / MT. **This is the failure mode.**

### 4.3 Enforcement decision

Normalize at RENDER time in a deterministic post-processor; never trust the LLM. Recommended convention: **U+02BB (ʻ) for oʻ/gʻ, U+02BC (ʼ) for tutuq belgisi**, matching @mohirdev. Enforce globally — one convention channel-wide.

### 4.4 Inbound normalization (separate direction)

Real members write `zur` and `Ohirgi`. Before intent classification, normalize inbound text:
- `zur|zor|zoʻr|zo'r` → `zoʻr`
- `chikdi` → `chiqdi`
- `x ↔ h` treated as near-equivalent in fuzzy match
- all four apostrophe characters (U+0027, U+2018, U+2019, U+02BB/U+02BC) → canonical
- Cyrillic → Latin transliteration

Uzbek circulates in **both Latin and Cyrillic simultaneously**; script choice does not indicate language switching. Some of the 3000 members (esp. older) read/write Cyrillic. Also strip Cyrillic homoglyphs (е, о, а, с, р) that contaminate Latin words via copy-paste and silently break string matching, dedup and keyword triggers.

---

## 5. MACHINE-TRANSLATION TELLS — critic checklist

**Framing that matters:** LLM-generated Uzbek fails toward **newspaper/government register**, not toward broken grammar. A critic tuned to find grammatical errors will miss the actual failure mode entirely. MT tells and over-formality tells are largely the same list.

### Layer 1 — regex/deterministic, zero LLM cost, run first and short-circuit

| # | Detectable pattern |
|---|---|
| L1-1 | Mixed apostrophe characters within one message (any two of U+0027, U+2018, U+2019, U+02BB, U+02BC) |
| L1-2 | Cyrillic homoglyphs (е о а с р) inside a Latin-script word |
| L1-3 | Literal `hisoblanadi` (officialese copula abuse: "X Y hisoblanadi" where natural Uzbek uses a bare nominal predicate or a dash) |
| L1-4 | `amalga oshiril` / `amalga oshirish` |
| L1-5 | `mazkur` |
| L1-6 | `ushbu` |
| L1-7 | `bugungi kunda` / `hozirgi kunda` |
| L1-8 | Sentence-initial `Keling,` |
| L1-9 | Capitalized `Siz` mid-sentence (Russian `Вы` calque; in Uzbek only formal letters) |
| L1-10 | Hyphenated `-mi` (`bor-mi`, `keldi-mi`) |
| L1-11 | Date pattern `DD <monthname> YYYY` (correct is `YYYY-yil DD-monthname`) |
| L1-12 | `sentyabr\|oktyabr\|noyabr\|dekabr` (Russian `-y-` retained) |
| L1-13 | `muhim ahamiyatga ega` |
| L1-14 | `quyidagilarni oʻz ichiga oladi` |
| L1-15 | `imkoniyatini beradi` |
| L1-16 | `eʼtiboringizga havola etamiz` |
| L1-17 | `shu munosabat bilan` |
| L1-18 | Latin brand + case suffix without apostrophe (`Googlening`, `Google ning`) |
| L1-19 | Message length > 4096 (or > 1024 when a media caption) |

### Layer 2 — LLM critic

| # | Pattern |
|---|---|
| L2-1 | Section-announcing calques: `Keling, boshlaymiz` / `Keling, koʻrib chiqamiz` / `Keling, batafsil koʻrib chiqaylik` (< ru `Давайте…`, en `Let's…`); `Ushbu maqolada biz ... haqida gaplashamiz`; a labelled `Xulosa:` section inside a 4-sentence post |
| L2-2 | Stacked formal connectives — `Bundan tashqari`, `Shu bilan birga`, `Shuningdek`, `Bunga qoʻshimcha ravishda`, `Natijada`, `Shunday qilib` appearing 3+ times in one short post |
| L2-3 | **Pro-drop violation** — explicit `biz/siz/u` subject in every clause. Uzbek drops them; English MT keeps them. Survives fluent-sounding output; a non-native reviewer cannot spot it |
| L2-4 | Verb not in final position / SVO word order leaking through |
| L2-5 | `va` overuse where Uzbek juxtaposes or uses `-u/-yu` or `hamda` |
| L2-6 | Calqued idioms: `kunning oxirida` (at the end of the day), `oʻyin oʻzgartiruvchi` (game changer), `keyingi darajaga olib chiqish` (take it to the next level) |
| L2-7 | Register drift toward press/government prose generally |

### 5.1 Calibration requirement before this list gates anything

The tell list is **synthesized, not extracted from a study.** No accessible study anywhere provides concrete Uzbek MT error examples. The one MT-quality paper located (https://www.wosjournals.com/index.php/shokh/article/view/8009, "QUALITY ANALYSIS OF ENGLISH–UZBEK TRANSLATIONS IN MACHINE TRANSLATION SYSTEMS", Narkabilova Rayhonoy Alisherovna, SHOKH LIBRARY, 2025-12-10) contains **zero** example sentences, no side-by-side pairs, no Uzbek samples — only abstract categories ("incorrect rendering of polysemantic units", "grammatical mismatches between nouns and verbs", "disrupted consistency in complex sentences", "literal translation"), consistent with low-quality/AI-written. Alternatives inaccessible: papers.ssrn.com abstract_id=6346938 (HTTP 403), internationaljournals.co.in 6568 (Uzbek-Russian, no examples), PMC12548925 (Uighur, wrong language).

**Required calibration:**
1. Generate ~50 Uzbek texts via MT from **both** Google Translate **and a Russian source language** — the plausible contamination path for an Uzbek AI-education channel is Russian→Uzbek MT of AI news, not English→Uzbek.
2. Measure each tell's **false-positive rate** against the verified human corpus (@mohirdev / @texnokun_uz post text) before wiring it into the critic. A tell that fires on real human posts will make the critic reject good output.
3. **Until that calibration exists, the tell list is an advisory score, not a blocking gate.**

### 5.2 Style-reference corpus (cheap, no auth, no API key)

Scrape 200–500 posts each from `@mohirdev`, `@webdev07`, `@texnokun_uz`, `@ustozai`, `@kadirovDev` via the `t.me/s/<channel>` HTML preview into Postgres, tagged by surface (post/comment) and formality. Higher-signal than any prompt description of "Tashkent voice", and it doubles as the false-positive baseline for §5.1.

Named Uzbek channels verified to exist and render posts: `@mohirdev` (MohirDev.uz, OpenAI Partner Network member, weekly "SI hafta yangiliklari" digest), `@texnokun_uz`, `@webdev07`, `@tahrirchi_uz` (Uzbek spellchecker + MT startup), `@ustozai`, `@kadirovDev`, `@aisiouz`, `@machine_learning_lab`, `@kunuz` (largest UZ channel; subscriber count inconsistent across sources, 1.1M vs 1.6M). Directory of ~21 more UZ IT channels: https://github.com/asakew/IT-telegram-kanallar (`@codeclean, @ITmavzu, @CybersUz, @virtualdars, @devbros_uz, @progerlive, @thestartupuz, @TashkentIT, @github_uz, @uz_work`).

---

## 6. ENGAGEMENT PLAYBOOK — RANKED BY EVIDENCE STRENGTH

### TIER A — randomized field experiments with disclosed method and effect sizes

**A1. Seeded comment CONTENT matters, and supportive seeds do nothing.**
Donati & Song, "The Influence of the Vocal Minority: Evidence from Social Media Comments" (SSRN 6529698, doi 10.2139/ssrn.6529698; PDF https://marketing.wharton.upenn.edu/wp-content/uploads/2026/04/04.23.2026-Donati-Dante-PAPER.pdf; summary https://www.promarket.org/2026/05/14/opposing-comments-drive-organizations-social-media-engagement-but-undermine-offline-goals/). Randomized Facebook field experiment, ~1,000,000 US users, 4 arms: no visible comments (control) / 2 supportive comments / 2 opposing comments / 1 supportive + 1 opposing. Seed comments were real user comments harvested from a prior campaign (~135,000 users).
- Any comments vs none: **+13.4% overall engagement, +19.3% comment-section expansion**
- **Opposing** comments: **≈+45% reactions/comments/shares, ≈+15% link clicks**
- **"Supportive comments, by contrast, had little effect."**
- Companion survey experiment (n=5,000): opposing comments **cut incentivized donations 7.3–7.5%** and shifted attitudes negatively.

Implication: a bot posting a friendly "Great post! What do you think?" first comment is **the exact arm that showed ~no effect.** Contestable/mildly contrarian prompts drive the lift, but with measurable attitudinal and downstream-goal damage — needs a guardrail metric.

**A2. Goal framing (Ling et al., JCMC 2005, 4 field experiments on MovieLens, https://academic.oup.com/jcmc/article/10/4/JCMC10411/4614451):**
- Specific + challenging goals → **+27% more ratings** than "do your best" (z=2.87, p<.01)
- "Your taste is UNIQUE" → significantly more ratings overall (z=1.92, p<.05) and **+40% more ratings of rarely-rated items** (z=2.30, p<.01)
- **"This benefits others" framing DECREASED contributions (z=-2.46, p<.01); "this benefits you" also decreased them (z=-2.52, p<.01)**
- **Group goals beat individual goals** — individual-goal subjects produced only **42%** of group-goal subjects' output (z=-2.43, p<.02)
- Goal difficulty is **inverted-U** — output declined at the hardest goal (64 ratings), z=1.85, p=.06

**A3. Social comparison is asymmetric and dangerous (Chen, Harper, Konstan & Li, American Economic Review 2010, MovieLens field experiment, https://www.aeaweb.org/articles?id=10.1257/aer.100.4.1358):** after being shown the MEDIAN user's total ratings, **below-median users +530% monthly ratings; above-median users −62%.** Direction likely transfers; magnitudes (2007 MovieLens, movie-rating task) almost certainly do not.

**A4. Positive-first-signal herding (Muchnik, Aral & Taylor, Science 2013, 341:647-651, doi 10.1126/science.1240466):** administrators randomly up-voted, down-voted, or left untouched the first vote on >100,000 posts on a social news aggregator. A single positive first vote **+32%** probability of a subsequent positive rating, accumulating herding **+25%** final mean ratings. **Negative first votes were CORRECTED by users, not herded — the effect is asymmetric.** Topic-dependent. **This measured VOTES, not authored comments** — it is adjacent evidence for seeding, not direct.

**A5. Badges causally steer behavior (Anderson, Huttenlocher, Kleinberg & Leskovec, WWW 2013, Stack Overflow, https://www.cs.cornell.edu/home/kleinber/www13-badges.pdf):** users increase effort on the badge-targeted action as they approach the threshold and **revert afterward**. Follow-up (Yanovsky et al., JASIST 2021, doi 10.1002/asi.24409) finds the effect heterogeneous — depends on the user's contribution rate; some significant contributors are unaffected. Design recurring weekly thresholds, not one-off lifetime badges.

### TIER B — large-N observational / regression, method disclosed

**B1. What makes a post get a reply (Arguello et al., CHI 2006, "Talk to Me", 6,172 messages across 8 Usenet newsgroups, https://ils.unc.edu/~jarguell/ArguelloCHI06.pdf):** **27% of posts received NO response.** Significantly increasing reply probability: **asking a question, posting on-topic, using less complex language, including autobiographical/testimonial self-disclosure.** **Newcomers were significantly LESS likely to get a reply than established members** — the failure loop a reply-SLA exists to break. Observational regression, not an experiment.

**B2. Replying to comments lifts engagement (Buffer, Nov 2025, https://buffer.com/resources/replying-to-comments-boosts-engagement/):** ~2 million posts, 220,000+ accounts, 6 platforms, **fixed-effects regression** (each account compared to itself over time, controlling for size/location/niche). Threads **+42%**, LinkedIn **+30%**, Instagram **+21%**, Facebook **+9%**, X **+8%**, Bluesky **+5%**. Per-platform samples: Threads 128k posts; LinkedIn 72k posts/25k accounts; Instagram 700k posts/68k profiles; Facebook >1M posts; X ~30k posts/16k accounts; Bluesky 73k posts. **Telegram was not in the sample, and Telegram has no ranking algorithm** — the algorithmic-amplification mechanism does not exist there, so the effect must operate purely through social reciprocity and may be substantially different.

**B3. Curated highlighting raises quality AND frequency (Wang & Diakopoulos, ACM TSC 2021, >13 million New York Times comments, https://dl.acm.org/doi/10.1145/3484245):** an "NYT Pick" badge correlates with higher-quality subsequent comments from that user; replies to Picks have higher median quality than replies to non-Picks; **the boost attenuates after subsequent Picks and decays over time** but stays above never-picked commenters. Related work: after a user's first featured comment, commenting frequency increased. **Rotate picks across people.**

**B4. Telegram participation profiles are stable (arXiv 2503.13635):** ~6 million messages, 29,196 users, 409 public Telegram groups, 10 topics, March 2024, median group size 493 active users. **For 76.6% of users, >50% of messages fall in a single participation profile.** Social-influence-driven profiles = 28% of all messages. In OLS, "direct influence" users (responding to peers) posted LESS frequently and occupied peripheral network positions; "independent" users occupied the most central positions and **"often act as conversation catalysts."** **Average group message activity strongly and positively predicted individual participation** — mechanistic case for seeding (raise ambient activity → individuals participate more).

**B5. Telegram reactions are a corrupted signal (arXiv 2508.06349):** 647,879 reacted-to messages across 993 channels. **Joy-type reactions >95% of ALL emoji reactions. >84% of negative and neutral messages received predominantly positive reactions. <0.3% of negative messages received negative reactions (chi-squared p<0.001).** A Random Forest using reaction features reached only **accuracy 0.71 / macro-F1 0.71** at separating high- from low-engagement posts. **Never use reaction counts as the LLM's content-quality feedback signal or as the optimization target.**

**B6. Group-oriented membership claims (Burke, Kraut & Joyce, https://www.dhi.ac.uk/san/waysofbeing/data/communication-zangana-burke-2009b.pdf):** a newcomer describing their participation in the group elevated community responses by **38%** in correlational data; an experiment inserting such claims into Usenet posts increased replies. Supports scripting the welcome DM to prompt a group-relevant self-fact before the newcomer's first comment.

**B7. MOOC completion does not improve with better content (Reich & Ruipérez-Valiente, Science 2019, "The MOOC Pivot", MITx/HarvardX, doi 10.1126/science.aav7958):** three verified qualitative findings — the vast majority of learners never return after their first year; growth is concentrated almost entirely in the world's most affluent countries; **low completion rates have NOT improved over 6 years.** Exact certification percentages could NOT be extracted (paywalled) — do not cite a number. Prior: completion must be *engineered* with commitment devices, not assumed.

### TIER C — survey data, self-selected samples

**C1. vc.ru Telegram reader-preference survey, n=2,108** (https://vc.ru/social/879075-kak-ne-nado-vesti-telegram-kanaly-issledovanie-predpochtenii-chitatelei-telegrama). See §10 for the full annoyance table. Self-selected online sample of Russian-speaking readers responding to *hypothetical* annoyances — stated irritation ≠ measured unsubscribing.

**C2. TGStat 2023 Russian audience research** (50,000 users, 15,000 channel admins, 800 brand/agency reps, 90+ questions; read via https://searchengines.guru/ru/articles/2057066, primary tgstat.ru report not fetched): **40% disabled notifications for ALL channels; another 37% receive pushes from only 1–5 channels (77% combined minimal notification exposure).** ~50% subscribe to 25+ channels, 25% to 50+, but **75% actively read no more than 15.** **84% engage with post reactions.** Ad perception among non-Premium: 10% never noticed ads, 42% rarely, 48% frequently. Russian audience, secondary source.

**C3. elama/SMMplanner survey, n=89** (mostly digital professionals, https://elama.ru/blog/kak-auditoriya-ispolzuet-telegram-na-rubezhe-20222023-godov-rezultaty-issledovaniya/): **68.5% mute a channel immediately after subscribing; 28% mute later; only 3.5% keep notifications on.** Of muted channels, 40% still opened 1–2×/day, 28% several times a week, 15% never reopened. **83% subscribed because of a recommendation (57% from an account they already follow).** Before subscribing, **46% read 3–5 recent posts and 37% read 5+.** >50% unsubscribe over irrelevant content; 19% because they forgot why they subscribed. Tiny, skewed sample.

### TIER D — documented single-company case studies (self-reported, unaudited)

| Case | Numbers |
|---|---|
| **Giveaway growth** — OneSpot, 8–15 Nov 2023, 7 days (https://onespot.one/all-posts/keys-s-rozygryshem-v-telegram-priglasili-v-kanal-klientov-i-poluchili-podpischika-za-40-rubley) | Channel 9,868 subs; prize 10 × Telegram Premium 6-month (15,999 RUB total); entry = be a subscriber; promoted by email + Telegram Ads reaching 40,000 users in 2 days + partner channels. Result **+537 subs, 397 retained** after post-giveaway churn (**≈26% of newly acquired churned**). **30 RUB per subscriber acquired, 40 RUB per subscriber retained.** |
| **Referral bot** — SOKOLOV, 1 month (https://www.sostav.ru/blogs/281129/66465) | Flow: enter bot → verify channel subscription → share phone → receive personal referral link → +1 entry per referred user; draws Mon/Wed/Fri. **18,762 participants** completing all conditions, **14,442 new subscribers** via referral links, budget ~1.2M RUB (300,000 dev/support + ~900,000 prize fund for 79 winners) → **≈83 RUB/subscriber vs ≈214 RUB (€2.30) via Telegram Ads** in the same niche. Anti-fraud: phone requirement, automatic bot detection, admin blocking panel, base cleansing. |
| **Channel-first vs bot-first A/B** — BotHelp online school (https://bothelp.io/ru/blog/keys-prodvizhenie-onlayn-shkoly-cherez-targetirovannuyu-reklamu-telegram-ads-i-avtovoronki) | Ads→channel: **271 subs at €2.89**. Ads→bot: **2,365 subs at €0.91 (3.2× cheaper)** plus **1,038 marathon registrations at €2.02**. Stated cause: step removal (Ad→Channel→Post→Registration vs Ad→Bot registration). |
| **Bot funnel conversion** — Carrot quest / GOOD NIGHT SHOW, 2 months, 26,000 monthly site visits, 16 cities (https://www.carrotquest.io/blog/telegram-bot-case-good-night-show/) | **6% of pop-up viewers subscribed to the bot; 52% of bot subscribers submitted a phone number inside the bot; 3.1% end-to-end.** Bot produced **24% of ALL site leads** and 45% of leads from the vendor's toolset; **16.4% of those leads converted to a sale.** Mobile clicked 10% vs desktop 4.7%. Flow: enter bot → qualification questions → submit phone for a quote. |
| **Ads → course sales** — hairdressing school, first month from Dec 2023 (https://www.sostav.ru/blogs/267280/43057, https://ruward.ru/cases/6368/) | 57,476 RUB spend → **1,684 subs at 34.13 RUB** (5,000+ clicks at 11.27 RUB); separately 2,548.86 RUB (€26.48) → **32 webinar registrations at 79.66 RUB**; **5 sales**; 99,472 RUB revenue. Implies **≈0.3% channel-subscriber→buyer** and **≈15.6% webinar-registrant→buyer** on cold traffic, month one. |
| **Launch structure** — yagla, 25 Sep–10 Oct 2023, ~15 days (https://yagla.ru/blog/socialnye-seti/keys-marafonnoy-voronki-v-telegram--2405u99870/) | 105,000+ RUB ad spend → 770 subs at 137 RUB. 7-stage cycle: preparation (1 month prior) → advertising (15–20 days before warming) → packaging → **active warming 7–10 days** → **3-day marathon shifting value/sales ratio 80/20 → 20/80** → **7-day sales window** → fulfilment. Budget split: 10–15% testing, 60–65% main buy, 20–30% retargeting. Claimed 2,000,000+ RUB revenue, ~18× ROI — **self-reported, discount heavily; the STRUCTURE and DURATIONS are the usable output.** |
| **Content rubrics** — cleaning online school, Jul 2024 (https://blog.tochkadostupa.pro/kejs-kak-poluchit-450-podpischikov-v-telegram-i-uvelichit-prodazhi-v-onlajn-shkole-po-uborke/) | 2,355 subs → **+450 new**; Telegram's share of flagship course sales rose **6.9% → 18.95%**; chatbot's share 10.53% → 11.58%. Rubrics: product reviews, how-to answers, life hacks, engagement posts (polls/tasks/audience questions), expert posts. Personal content raised viewership. Free bot marathon converted into the paid program. |
| **Pair mechanic** — Duolingo (https://blog.duolingo.com/friend-streak/, https://www.getrecall.ai/summary/lennys-podcast/behind-the-product-duolingo-streaks-or-jackson-shuttleworth-group-pm-retention-team) | Users with at least one **Friend Streak are 22% more likely to complete their daily lesson**. **600+ experiments on the streak feature alone.** Four years of retention work → +21% Current User Retention Rate, >40% reduction in daily churn, 450% DAU increase; share of DAU with a 7+ day streak roughly tripled; one copy change = 10,000 incremental DAU. Secondary write-ups of a podcast + company blog, no disclosed experiment methodology. |

### TIER F — MARKETING FOLKLORE. Do not plan around.

- **"3–8% of bot subscribers / 1–3% of channel subscribers take the target action"; "2–5% drop-off after welcome, 1–2% per content message"; "~50% conversion into channel subscription, ~90% into bot subscription, ~10% never press Start"** (https://360uniquizer.com/ru/news/telegram-funnel-ubt-2026, https://vc.ru/marketing/1417430-voronka-v-telegram-i-socsetyah) — no published methodology anywhere. **Additional defect: the 3–8% figure is published as an Uzbekistan ERR (Engagement Rate by Reach) benchmark, not a bot conversion rate** — https://101digital.uz/en/blog/telegram-marketing-uzbekistan/ states "Average ERR in Uzbekistan is 3-8%" (unsourced agency claim). Different denominator. **Do not use as a funnel step.**
- Lead-magnet / referral benchmarks: website opt-in 1.95% average (Sumo), bottom quartile 0.8%, top 6.5%; referral share rate 5–15%; referral link CTR 10–25%; median referral conversion 3–5%; mature programs 15–25% of new-customer acquisition; 83% say willing to refer, 29% do; dual-sided rewards +29% participation; tiered rewards +27% more referrals (https://mycodelesswebsite.com/lead-magnet-statistics/, https://growsurf.com/blog/good-referral-rate/, https://www.referralcandy.com/blog/referral-program-benchmarks-whats-a-good-conversion-rate-in-2025/). Web-form benchmarks, not Telegram. Use as a floor only — Telegram opt-in should far exceed them (compare measured 6% pop-up→bot and 52% bot→lead).
- Webinar/challenge benchmarks: webinar→paid 8–15% under $500, 5–10% $500–1,500, 1–4% $2,000+; registration→show-up 30–40% average / 50–60% top; **free challenge→paid 10–20%, up to 30%; challenge completion 70–80%** (https://aevent.com/average-webinar-conversion-rate/, https://scaleforimpact.co/webinar-conversion-rate-benchmarks-what-to-expect-at-every-price-point/, https://communipass.com/blog/9-day-challenge-funnel-for-course-creators-2026-conversion-framework/). The price-tiered webinar bands are the most plausible of this group (an Uzbek-market course sits in the sub-$500 / 8–15% tier). **The 70–80% challenge-completion figure directly contradicts the MOOC evidence (B7) — ignore it.**
- Push-notification opt-out figures (Localytics, original study not retrievable, via https://www.mobiloud.com/blog/push-notification-statistics and https://www.pushwoosh.com/blog/push-notification-best-practices/): 46% opt out after 2–5 irrelevant messages/week; 32% at 6–10/week; 32% uninstall after >6 irrelevant pushes; >1 promotional notification/day correlates with increased opt-outs. Directionally useful as a bot-DM ceiling only.
- **"Polls are the single most effective engagement tool on Telegram"** — no data behind it in any source located. See §8.

---

## 6.1 WHAT DID NOT SURVIVE VERIFICATION

**REFUTED — dropped entirely:**

1. **"No written attestation of `karoche` in Uzbek exists."** Wrong — two independent written attestations found (§3.1). But the *design conclusion* is unchanged: both are *sen*-register, so it still ships nowhere in the *siz* generator. What is dropped is the blanket "not a single instance" statement, not the recommendation.
2. **"Telegram Ads CPM in Uzbekistan can be as low as €0.02."** REFUTED — below Telegram's published bid floor and therefore not purchasable. Primary source https://ads.telegram.org/getting-started: **"The minimum CPM for a sponsored message is 0.1 Toncoin."** TON ≈ $1.39 (Aug 2026, https://metamask.io/price/toncoin) → floor **≈ $0.139 ≈ €0.12 CPM**, ~6× the alleged €0.02 — and that is a *minimum bid*, not a clearing price. EUR-denominated accounts (secondary, LOW CONFIDENCE — Telegram reduced euro-office CPM minimums, announced 16 Feb 2026): **€0.7 CPM** for channel-category/audience-segment targeting, **€1.0 CPM** for specific channels/bots/search. Vendor spread on Uzbekistan is 35×: 101digital.uz says "CPM starting from 2 EUR", https://adsly.pro/guides/telegram-ads-cpm-by-country/ says ~$0.70. **Plan growth at €0.5–1.5 CPM.** If €0.02 was genuinely observed it is a different unit (cost per single impression = €20 CPM), a mini-app network like Adsgram, or a direct private buy from an Uzbek channel owner outside the ad platform.
3. **The "19% of Uzbek spelling errors are x/h confusion" figure.** Not merely soft — **UNSOURCED.** No accessible paper states 19% or any percentage. https://inlibrary.uz/index.php/science-research/article/view/107280 ("OʻQUVCHILARDAGI TIPIK ORFOGRAFIK XATOLARNI ANIQLASH") was fetched and contains **no numerical data of any kind**; it categorizes errors as phonetic, morphological, graphic, syntactic only. Abdurakhmonova "Personal Names Spell-Checking" — ResearchGate HTTP 403. acta.polito.uz art. 209 and cajlpc 1545 expose no error-type breakdown. **Strip the number. Keep the qualitative fact** (x/h substitution is a recognized high-frequency error class, canonical direction h-for-x as in `hoto`/`xato`), which alone justifies the design actions.
4. **"The evidence for comment seeding is adjacent, not direct."** REFUTED — Donati & Song (2026) is a direct randomized ~1M-user manipulation of seeded comment content (§A1). What IS confirmed: no *Telegram-specific* seeding experiment exists.
5. **The Popsters posting-time result as a source of posting hours.** The findings were verified verbatim against the primary source (https://popsters.com/blog/post/social-networks-users-activity-report, PDF https://popsters.com/app/docs/Popsters_research_2019_en.pdf): Telegram "activity peaks are at 4 a.m., 12 and 3 p.m."; "The activity leaders are Saturday and Friday" with "a decrease seen on Tuesday"; long text = "37.1% of all activities, while medium-size texts received 32.8%"; night (defined 9 p.m.–1 a.m.) more active than day. **But the disqualifying defects are different from the ones originally claimed.** The "Russian-language-dominated" premise is NOT verified — Popsters explicitly claims "604 million posts by 934 thousand public pages on 11 social networks... The data cover 150 countries" and publishes no language, country, or per-platform breakdown. The real defects: (a) **self-selected convenience sample** — the corpus is whatever pages Popsters' own paying customers chose to analyze ("Popsters users analyze thousands of pages daily... Depersonalized results are stored on the server"), with **no published Telegram-specific N**; (b) **"the metrics were reduced to a single time zone" and the report never states WHICH.** A UTC-vs-Moscow(UTC+3) read shifts the peak 2 hours; UTC-vs-UTC+5 shifts it 5. **"4:00/12:00/15:00" is unmappable to Asia/Tashkent under any assumption. Derive no posting hour from this report.** The long-text finding is a share-of-activity split, not a per-post lift, and is also not actionable.
6. **The posting-frequency numbers as "no published methodology."** Partially wrong — https://postmypost.io/resources/research-how-posting-frequency-affects-the-number-of-post-views-on-telegram (direct fetch repeatedly ECONNRESET; read via search index) **does** state a method: "examin[ing] channels of different sizes" and "for each channel, compar[ing] the reach of the first and last publication of the day." Figures: "with 4 posts, reach drops by 30-40% for the last post"; "with 8+ posts, each new material receives 2-3 times fewer views than the first"; recommendation "1-2 posts per day, with 3 posts being an acceptable maximum"; explicit exception for news/media channels. **Genuinely absent:** sample size, date range, data source, channel-size strata, language/geography, any statistical test. **Fatal confound:** last-post-of-day reach is measured with less elapsed time than first-post reach unless views are age-matched, which the description does not mention — the design would produce the reported effect with zero real cannibalization. **Moot anyway:** 2 posts/day sits below the source's own 4-post threshold. Justify any cadence change from the channel's own reach at fixed post age (e.g. views at t+12h).
7. **Uzbek-market engagement benchmarks are unobtainable.** Wrong — ER/reach benchmarks for Uzbek Telegram **are measurable from panel analytics**: Telemetrio (https://telemetr.io/en/catalog/uzbekistan) indexes **75,649 Uzbek Telegram communities** with daily-updated ER and real post reach (e.g. `@uzbekistan24` shows **9.56% average ER**, June 2026 data). TGStat offers equivalent Uzbek coverage. **Pull a peer set of Uzbek AI-education channels before setting targets** instead of importing vendor funnel numbers.

**CONFIRMED as doubtful — keep the doubt:**

8. **`top` as Uzbek praise** — confirmed no source exists; hard-exclude (§3.2).
9. **`qoyil` frequency in Telegram comments** — confirmed unknowable; no Uzbek Telegram-comment corpus exists. The only public Uzbek comment dataset is the same Uzum e-commerce set (352,151 rows). `issai/Uzbek_Speech_Corpus` and `murodbek/uzbek-speech-corpus` are speech. The one paper on written Uzbek internet discourse (Temirova, BG Pulse Journal USA Vol.2 No.07, 23 July 2026, http://www.bgpulseusa.com/index.php/bg/article/view/1841) covers Telegram/Instagram/YouTube but has a corpus of **17 public sources recorded on a single day (19 July 2026)**, reports no statistics, and gives zero verbatim examples.
10. **MT tell list is synthesized and unvalidatable against literature** — confirmed, and understated (§5.1).
11. **Poll/quiz cadence has no primary evidence** — confirmed (§8).

**UNUSABLE (numbers real, transfer invalid):**

12. **Uzbek-Russian code-switching statistics.** Every number is an accurate quotation from Mizuki Sakurama Nakamura, *Turkophone* Vol.11 Iss.3, Dec 2024, pp.118-137, published 8 Feb 2025, JSPS Grant-in-Aid 18J20041, Tokyo University of Foreign Studies project jrp000295 (https://dergipark.org.tr/en/download/article-file/4044388). Verbatim: "intra-sentential switching being the most common (58% of all switches), followed by inter-sentential (31%) and tag-switching (11%)"; "a notable preference for switching from Uzbek to Russian (63% of all switches) compared to Russian to Uzbek (37%)". §4.2.3 verbatim: "Older participants (50+) tended to use more Russian and engage in more frequent code-switching, particularly when discussing topics related to the Soviet era or their youth"; "In contrast, younger participants (18-30) showed a stronger preference for Uzbek, with code-switching often limited to specific technical or cultural terms." **Methodology (§3.2) is decisive: 30 Uzbek-Russian bilinguals aged 18–65, ALL Tashkent residents, 2018 fieldwork, data = audio recordings of natural conversation — family gatherings (16 recordings), public spaces/cafes/markets (22), sessions 15–30 min, "a total of 43 hours 13 minutes of recorded speech." Not one line of written or social-media data.** Percentages for café speech transfer to nothing about typed Telegram comments. Sample is Tashkent-only urban bilinguals, over-representing Russian vs a nationwide audience. The age finding is a qualitative observation, no counts, no significance test, n=30 convenience sample, unreplicated. Synthetic-prose suspicion supported: extracted text contains the artifact "researchers move between computers and computers". **Do NOT tune Russian-borrowing density by age using these figures.** The one directionally safe inference (younger speakers prefer Uzbek, switching limited to technical terms) coincides with the safe default — Uzbek matrix, Russian/English only for tech nouns (AI, promt, model) — so adopt that default on general grounds, not as evidence-backed calibration.

---

## 7. COMMENT SEEDING — what the evidence actually supports

**Supported:**
- Seeding *something* beats seeding nothing: **+13.4% engagement, +19.3% comment-section expansion** (A1).
- Raising ambient group activity raises individual participation (B4, observational).
- If a positive-valence seed is used, it should be positive rather than critical **on vote-like signals** — negative first signals get corrected, not herded (A4).

**Contradicted by the strongest evidence:**
- **A supportive/agreeable bot seed had "little effect"** (A1). "Great post! What do you think?" is the null arm.
- The **~+45%** lift came from **opposing/contestable** comments — and carried **−7.3 to −7.5%** on downstream incentivized action plus negative attitude shift.

**Unknown:**
- **No Telegram-specific seeding experiment exists.** Post-level randomization is still required.
- **A bot posts comments AS THE BOT.** Human channel admins can post to the discussion group *as the channel*; a bot cannot. Every seeded first comment is visibly bot-authored — a materially different stimulus from the anonymous vote in A4 and from the real harvested user comments in A1. The seeding effect may be much weaker or negative if members read it as astroturf.

**Implementation:**
- Detect the auto-forwarded channel post in the linked group via `message.is_automatic_forward == true` ("True, if the message is a channel post that was automatically forwarded to the connected discussion group"). Reply into the thread by sending to the discussion-group `chat_id` with `reply_to_message_id` = that forwarded message's `message_id`. **No other API surface exists for programmatic commenting.**
- Seed within 60–120 s of every post.
- Seed content must be on-topic, plain Uzbek, low linguistic complexity, ending in ONE explicit question (B1: question + on-topic + low complexity all raise reply probability independently).
- **Human layer:** recruit 3–5 real members with a private brief to post the 2nd and 3rd comments in the first 30 minutes. Peer comments are the stimulus A1 actually tested.
- **The required A/B (4 weeks, post-level randomization), 3 arms:** control (no seed) / supportive seed / genuinely contestable-or-mildly-contrarian prompt seed. Primary metric: **unique commenters per post.** Guardrail metrics: 24h unsubscribes, sentiment, mute rate. This is the single most important experiment in the system.

Seed template rotation (3 forms): (a) one-word/one-number answer, (b) binary A-or-B with a one-line reason, (c) sentence completion.

---

## 8. QUESTION AND POLL FORMATS

### 8.1 Question-design constraints (encode as hard rules in the prompt-agent)

From Ling et al. (A2), the only quantified guidance available:

1. **Ask for a SPECIFIC small quantity** — "name 2 tools", "write 1 sentence". **+27%** over "do your best" (z=2.87, p<.01).
2. **Include a uniqueness cue** — "nobody has answered for <topic> yet". Significant overall (z=1.92, p<.05); **+40%** on rarely-covered items (z=2.30, p<.01).
3. **State a visible COLLECTIVE target** — "30 answers by tonight". Individual-goal subjects produced only **42%** of group-goal output (z=-2.43, p<.02).
4. **Keep goals moderate, not maximal** — inverted-U; output declined at the hardest goal (z=1.85, p=.06).
5. **BAN the phrase family "this helps the community / your answer helps others / helps you learn."** Both benefit framings significantly REDUCED contributions (z=-2.46 and z=-2.52, both p<.01). **An LLM writing engagement copy will default to this framing unless explicitly forbidden.** Put it in the denylist.
6. Include a first-person disclosure line (B1: autobiographical/testimonial self-disclosure raises reply probability).

### 8.2 sendPoll — exact API constraints

| Param | Constraint |
|---|---|
| `question` | 1–300 chars (Bot API) / clients enforce 1–255 |
| `options` | 2–12 items, each 1–100 chars |
| `type` | `"regular"` \| `"quiz"` |
| `correct_option_id` | required for quiz, 0-based |
| `explanation` | 0–200 chars, **max 2 line feeds** |
| `is_anonymous` | **defaults to True** |
| `open_period` | 5–600 seconds |
| `close_date` | up to 2,628,000 s (~30.4 days) ahead |
| mutual exclusion | `open_period` and `close_date` cannot both be set |

Source: https://core.telegram.org/bots/api#sendpoll, https://limits.tginfo.me/en. Note: aiogram's page (https://docs.aiogram.dev/en/latest/api/methods/send_poll.html) **conflates `open_period` with `close_date` range** — trust core.telegram.org.

LLM-generated quiz explanations routinely blow the 200-char / 2-linefeed limits and cause `sendPoll` to fail. **Hard-truncate and validate before the API call.**

### 8.3 Per-user poll data — two simultaneous conditions

MTProto docs (https://core.telegram.org/api/poll): **"Bots receive new votes only in polls that were sent by the bot itself."** Bot API `PollAnswer` exposes `user` only **"if the voter isn't anonymous"** (`voter_chat` otherwise). `PollAnswer` fields: `poll_id`, `option_ids`, `option_persistent_ids`, `voter_chat`, `user`.

⇒ For a leaderboard or lead scoring, the poll **MUST be sent by the bot AND created with `is_anonymous=False`.** A human admin posting a poll manually, or leaving the default `is_anonymous=True`, yields **zero** user-level data. This silently breaks any quiz-leaderboard design.

**Tradeoff:** non-anonymous polls make every vote publicly visible. For self-assessment ("what's your AI skill level?") this suppresses honest answers and embarrasses beginners — exactly the audience you want to convert. Use non-anonymous only for quizzes and low-stakes preference questions; use anonymous for anything self-revealing and accept no user data.

### 8.4 Cadence — no evidence exists

**No primary evidence for poll/quiz cadence on Telegram, and no measured comparison of polls vs open questions on engagement or retention, in any source located.** The most-cited prescription is unsourced vendor assertion: https://blog.invitemember.com/engaging-telegram-polls/ and https://postly.ai/telegram/telegram-polls-quizzes state "1-2 polls per week is the sweet spot for most channels" and "posting too many in one week can annoy members" — no sample, no measurement, no citation. Adjacent-but-different: a live-poll medical-education study (https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10121230/) reports 86.9% of students enjoyed poll participation and 88% felt it improved understanding — self-report, classroom Zoom, not channel broadcast, not a cadence test. Telegram's own docs publish API constraints only, zero engagement data.

**Quantitative anchors that do exist:** TeraGram (arXiv 2605.15956) — 5.95 billion messages from 712,000 chats, 2015–2025 — contains **21.29 million poll questions with 79.44 million answers**. Polls are common but far from dominant. Telegram surfaces vote-change analytics only after a poll passes **100 votes**; a 3,000-member channel usually clears this, making polls a usable measurement instrument as well as an engagement device.

**Action:** treat cadence as an open experiment. Log per poll: `poll_id`, `total_voter_count` (Bot API `Poll` object) / channel reach at t+24h, unique voters, and 24h unsubscribe delta. **Alternate poll weeks with open-question weeks** so the project generates its own comparison within ~6–8 posts per arm.

### 8.5 Zero-build alternative

Telegram Polls 2.0 (official, 23 Jan 2020, https://telegram.org/blog/polls-2-0-vmq) introduced Visible Votes (non-anonymous), Multiple Answers, and Quiz Mode (one correct answer, confetti on correct). Official **@QuizBot** (https://telegram.org/tour/quizbot) builds multi-question quizzes, supports text/media before questions, tracks how many questions each user got right and how long they took, and maintains a global leaderboard per quiz. Useful as v0 — **but it keeps the data outside your Postgres.** For lead scoring you need bot-sent non-anonymous polls.

---

## 9. CHALLENGES, RECOGNITION, REFERRALS — and what backfires

### 9.1 Recognition — do this

**Curated highlighting (NYT Picks model, B3) is the recognition mechanic with the best evidence: it raises quality AND frequency, and unlike a leaderboard it has no explicit losers.**
- Daily: bot pins/highlights 2–3 "best answers" in the channel with the author's handle.
- **Rotate across DIFFERENT people** — the Picks quality boost attenuates on repeat recipients and decays over time.
- Deliver streak and rank feedback **PRIVATELY via DM.**

**Badges (A5):** work as a targeting device for one specific behavior with a threshold ("5 comments this week"), not as a general motivation layer. Expect spike-then-revert. Use **recurring weekly thresholds**, never one-off lifetime badges.

### 9.2 Recognition — what backfires

**Public global leaderboards are actively harmful to your best contributors.** In the AER field experiment (A3), above-median contributors **CUT output 62%** after being shown where they stood. A "commenter of the week" board that publishes full rankings risks demobilizing exactly the handful of members carrying the comment section.

Safe shape (JMIR Serious Games 2021, https://games.jmir.org/2021/2/e14746): macro (global) leaderboards accumulate perceptions of repeated failure for lower performers, with only mid-to-upper ranked users experiencing success; **combining macro with MICRO (local/relative, nearby-rank) leaderboards provides "more success opportunities for all participants."** ⇒ show each member only their local neighbourhood plus their own trajectory, never the full ranking of 3,000 people, and **never tell a top contributor they are far above the median.**

### 9.3 Challenges

- 5–7 days, one task per day requiring ≤10 minutes.
- Submission via bot command (`/submit`) so the bot stores the artifact in Postgres and `copyMessage`s it to a private review chat.
- Daily in-channel digest of 3 submissions.
- **Pair participants so BOTH must submit for the pair's streak to survive** — the Duolingo Friend Streak analogue (+22% daily completion, Tier D confidence).
- **Assume low completion by default (B7).** Engineer commitment explicitly: a public day-0 pledge comment, a paired partner, a visible deadline, optionally a nominal fee. Do not plan on the folklore 70–80% completion figure.
- **No evidence at all was found on UGC contest structure, duration, prize design, or submission mechanics** meeting a "documented results" bar. Every source located was generic marketing content. All contest recommendations here are design inference from adjacent evidence (goal-setting, badges, curation, giveaway case data).

### 9.4 Prizes and giveaways

**Telegram-native Giveaways** (official, launched 6 Nov 2023, https://telegram.org/blog/giveaways): the channel owner pre-purchases Telegram Premium subscriptions (via app, @PremiumBot, or Fragment for bulk); **Telegram selects winners randomly**; organizers can restrict eligibility to all subscribers **or new subscribers only**, restrict by country, and require subscription to additional channels. Channels earn **4 boosts per subscription given away** (boosts unlock channel Stories and custom colors). Premium giveaways require **≥50 subscribers**; Stars giveaways require **≥50 subscribers (channels)** or **≥500 members (groups)** (minimums reported secondarily via blog.invitemember.com). Zero-code, fraud-proof — prefer this over building a raffle. "New subscribers only" makes it a growth lever rather than a retention lever.

**Backfire:** generic-prize giveaways attract prize hunters. The documented case lost **≈26%** of newly acquired subscribers within ~10 days of the giveaway ending (30 RUB raw CAC vs 40 RUB retained CAC). **Report retained-subscriber CAC, never raw CAC.** Prefer prizes that self-select for course intent — a free seat, a 1:1 project review, a large course discount — over generic prizes.

### 9.5 Referral architecture

**Do NOT use one tracked invite link per referrer.** Two breakages:
- **`chat_member.invite_link` attribution is unreliable** — developers report it is absent when joining public chats/channels via invite link and on rejoins. python-telegram-bot issue **#3927** was **closed as not planned with no maintainer explanation** (https://github.com/python-telegram-bot/python-telegram-bot/issues/3927). A referral payout built on it will silently under-credit referrers and destroy trust.
- **~100 ACTIVE invite links per admin** (revoked/expired don't count); max 50 admins per group/channel. Secondary source (https://limits.tginfo.me/en), not core.telegram.org — **verify empirically.** A naive per-referrer design breaks past ~100 concurrent referrers.

**Use instead:** referrer receives `t.me/<bot>?start=ref_<short_id>`. The invitee's Start payload IS the attribution record. Bot then calls `getChatMember` on the channel to verify the invitee actually subscribed before crediting.

Deep-link format: `https://t.me/<bot_username>?start=<payload>`; **payload max 64 characters**, allowed chars `A-Z a-z 0-9 _ -`, base64url recommended for binary. Group form `?startgroup=<payload>`; bot receives `/start@your_bot <payload>` (https://core.telegram.org/bots/features). **Store a short opaque key in Postgres; put only the key in the payload.**

Mirror the SOKOLOV structure (Tier D): verify subscription → collect phone/contact → issue personal link → +1 entry per verified invitee → frequent small draws. ≈83 RUB/sub vs ≈214 RUB via ads. Anti-fraud: contact-sharing requirement, minimum account age, automatic bot detection, manual review queue.

`createChatInviteLink` params: `name` 0–32 chars, `expire_date` (Unix ts), `member_limit` 1–99999, `creates_join_request` (bool; **if true, `member_limit` cannot be set**). Returns `ChatInviteLink`. `chat_member` updates require the bot to be an administrator AND `"chat_member"` explicitly listed in `allowed_updates`. Use tracked invite links only for a small number of named campaign sources.

**Join-request links are the exception that gives clean attribution:** `ChatJoinRequest` carries `invite_link` directly.

---

## 10. WHAT CAUSES MUTES AND UNSUBSCRIBES IN TELEGRAM SPECIFICALLY

### 10.1 vc.ru survey, n=2,108 Telegram users, 8 annoyance categories

| Behavior | % negative |
|---|---|
| Long posts without paragraph breaks | **87.9%** |
| Admin deletes comments they disagree with | **76.3%** |
| Comments required to go through a closed chat | **70.5%** |
| Admin reposting from their own other channels | **69%** |
| Channel publishes too many updates daily | **65.8%** |
| Admin does not respond to comments | **64.4%** |
| Only positive reactions available | **62.7%** |
| CAPS LOCK | **61%** |
| Slang / misspellings | **57.9%** |

Neutral / tolerated: admin explicitly asking for reactions **53.6% indifferent**; irregular posting **61.5% indifferent**; no comments at all **51.4% indifferent**.

Direct rules: keep 2 posts/day; format with paragraph breaks; **never delete a dissenting comment** (route to a human review queue instead); **never gate comments behind a closed chat**; always reply; **it is safe to explicitly ask for reactions**; no CAPS LOCK; the comment agent's deliberate sloppiness (§2) is a calculated risk against the 57.9% slang/misspellings figure — keep it to the attested error types only, and never in channel posts.

Caveat: self-selected online sample of Russian-speaking readers responding to hypothetical annoyances. **Stated irritation ≠ measured unsubscribing.**

### 10.2 Muting is the default, not the exception

- **40% of Telegram users have muted ALL channels they read; another 37% receive pushes from only 1–5 channels** (77% combined, TGStat 2023, n=50,000).
- **68.5% mute a channel immediately after subscribing; 28% mute later; only 3.5% keep notifications on** (elama, n=89 — tiny, skewed).
- Of muted channels: 40% still opened 1–2×/day, 28% several times a week, **15% never reopened.**

⇒ **Channel posts are a pull medium. Notifications are not a delivery guarantee.** The **only** surface that reliably notifies is a bot DM to an opted-in user — which is the strategic argument for the whole lead-capture design, **and** the only surface where over-messaging causes **permanent, unrecoverable** loss (a blocked bot cannot be re-reached). Cap promotional DMs at ≤1/day and ≤3–4/week outside an active launch window.

### 10.3 Unsubscribe causes

- **>50% unsubscribe over irrelevant/uninteresting content; 19% because they forgot why they subscribed** (elama, n=89).
- Post-giveaway churn: **≈26%** of newly acquired subscribers within ~10 days (Tier D).
- **≈46% of pre-subscribe visitors read 3–5 recent posts and 37% read 5+** ⇒ **the last 5 posts are the conversion surface**; the pinned/recent slots must carry the lead magnet.
- **83% subscribed because of a recommendation (57% from an account they already follow)** ⇒ recommendation is the dominant acquisition path, which is the mechanism a referral program exploits.
- Frequency: the current **2 posts/day is inside every recommended band** and is almost certainly NOT the cause of the quiet comment section. **Do not increase frequency to fix engagement.** The problem is format and the absence of seeding/reply.

### 10.4 Guardrail metrics to log per post

`views`, `reactions` (log but **exclude from any quality-optimization loop** — B5, >95% joy skew), `comment_count`, **`unique_commenters`**, **`bot_start_events_attributed_to_post`**, `unsubscribes_next_24h`, `notification_off_rate_trend`. North-star pair: **unique commenters per post** and **bot opt-ins per post.**

---

## 11. OPERATIONAL CONSTRAINTS THAT SHAPE THE VOICE/ENGAGEMENT LAYER

- **Bot Privacy Mode is ENABLED BY DEFAULT for all bots.** With it on, a bot in a group receives only commands addressed to it, replies to its own messages, messages sent via it inline, and service messages. **It will silently miss most member comments** while appearing partially functional. Must be disabled via BotFather (`/setprivacy` → Disable). Explicit deployment-checklist item.
- **Rate limits** (https://core.telegram.org/bots/faq): "In a single chat, avoid sending more than one message per second"; **"In a group, bots are not able to send more than 20 messages per minute"**; "for bulk notifications, bots are not able to broadcast more than about 30 messages per second, unless they enable paid broadcasts." Paid broadcast raises the ceiling to **1,000 msg/sec at a non-refundable 0.1 Stars per message** above the free 30/sec tier. Exceeding → HTTP 429. ⇒ "Reply to every comment" is impossible during a busy thread. **Every write path (seed, reply, digest, moderation notice) must go through a single shared per-chat token bucket with 429 backoff**, not per-agent sends. Broadcasting to 3,000 opted-in leads takes ≥100 s at the free tier.
- **Users can comment on channel posts WITHOUT joining the linked discussion group.** Discussion-group member count is a meaningless KPI, and any logic gating on group membership misclassifies most commenters. `channels.toggleJoinToSend` forces membership and returns `CHAT_GUEST_SEND_FORBIDDEN` to non-members — but 70.5% of surveyed readers react negatively to gated comments. Architecture: after `channels.setDiscussionGroup`, "All messages sent to the channel will also be forwarded to the linked group (with sender peer `from_id` equal to the peer of the linked channel); those messages will also be automatically pinned in the group." The comment section IS "the message thread of the automatically forwarded channel message in the linked discussion supergroup." (https://core.telegram.org/api/discussion)
- **Bans in the discussion group are NOT federated with the channel.** The bot must maintain its own ban ledger in Postgres and apply it to both chats separately.
- **Slow Mode intervals:** 10 s, 30 s, 1 min, 5 min, 15 min, 1 hour. **Throttles text messages only — not media, not reactions, not inline bot results.** Wrong lever for a quiet chat (adds friction to the exact behavior you want); only partially effective during a flood. Interval list and federation note are secondary sources.
- **Join-request DM window (the only way to reach a non-Start member):** `ChatJoinRequest` carries `user_chat_id`, documented verbatim: *"The bot can use this identifier for 5 minutes to send messages until the join request is processed, assuming no other administrator contacted the user."* Requires an invite link created with `creates_join_request=true`, the bot to be channel admin with `can_invite_users`, and `"chat_join_request"` explicitly in `allowed_updates`. **Applies only to NEW joiners** — the existing 3,000 cannot be reached this way. Flow: intercept join → DM lead magnet + deep-link button → `approveChatJoinRequest`. Persist `{user_chat_id, invite_link.name, join_ts, payload_key}`.
- **Only bot-published posts can carry inline keyboards.** Human-posted channel messages cannot. Make the bot a channel admin with post rights and have IT publish both daily posts, so every post carries an `InlineKeyboardMarkup` URL button deep-linking to `t.me/<bot>?start=p<post_id>`.
- **Payments (blocking decision).** Telegram Bot Developer ToS: *"All transactions pertaining to digital goods and services must be executed exclusively through the exchange of Telegram Stars"*; third-party processors prohibited for digital goods inside Telegram apps (Google Payments Policies 1/2/4; Apple Guidelines 3.1.1, 3.1.1(a), 3.1.3(b)). Non-compliance → notice, then the bot becomes inaccessible from store versions of Telegram or is terminated. **Developers earn 0.013 USD per Star.** Physical goods/services may use other providers. Refunds via `refundStarPayment`; invoicing via `sendInvoice` / `createInvoiceLink` / `answerPreCheckoutQuery`. **Whether a bot may LINK OUT to an external payment page for a digital course is genuinely unresolved** — core.telegram.org/bots/payments-stars does not address external links, and the ToS prohibition on "leveraging your TPA with external interfaces to develop external services" is broad enough to read either way. **Do not build Payme/Click checkout inside the bot without legal sign-off.**
- **Message limits:** 4,096 chars (8,192 Premium); media caption 1,024 (4,096 Premium); up to 100 keyboard button entities; up to 100 formatting entities per message; 0–100 bot commands registrable in BotFather; up to 20 bots per account (40 Premium); up to 50 admins per group; supergroup participants up to 200,000. **The 4,096 / 1,024 cap is one of the most common production failures for agent-written Telegram content.**
- **Market context (DataReportal Digital 2025, https://datareportal.com/reports/digital-2025-uzbekistan):** population 36.7M; **32.7M internet users (89.0%)**; 33.9M mobile connections (92.2%); 11.7M social media user identities (31.7%). Instagram ad reach 11.7M, TikTok 2.57M adults, Facebook 2.30M, LinkedIn 850k, X 250k. **DataReportal reports NO Telegram figures** (Telegram has no comparable ad-reach API). Secondary estimates of ~18M Telegram users in Uzbekistan (>70% of population) and Uzbekistan ranked 2nd globally by indexed Telegram channels (~195,000) have **no primary source — LOW CONFIDENCE.** Telemetrio independently indexes **75,649 Uzbek Telegram communities.** Cross-promotion barter with other Uzbek channels is likely the dominant organic growth channel.
- **Cost envelope.** At $50–150/mo the binding constraint is LLM tokens per comment reply, not Telegram infrastructure. Route by task: cheap/small model for comment classification, spam detection, seed-template selection; expensive model only for substantive teaching answers. Run the critic on generated output only (2 posts/day + N comments), never on inbound member messages. **Deterministic Layer-1 checks run first and short-circuit** — most register failures are catchable by regex at zero LLM cost. Cache the few-shot corpus in the prompt prefix for prompt-caching discounts. Hard per-day LLM spend cap in code with a kill-switch that degrades to template replies.
- **Pre-launch gate:** have a native Tashkent speaker score a 50-sample output set on one question: *"would a real person from Tashkent write this in a Telegram channel?"* Prioritize their verdict on the Russian-loanword question over anything in this document — that item has the weakest evidence.
- **Verify before hard-coding orthography:** confirm no Uzbek alphabet reform took effect. Proposals replacing digraphs with Ç/Ş/Ğ/Ŏ have been repeatedly announced and deferred; Wikipedia is the only source for current status. (unverified)

---

## Surprises

1. **The one direct comment-seeding experiment says friendly seeds do nothing.** Donati & Song: supportive comments had "little effect"; opposing comments drove ≈+45%. Every naive design ("bot posts a warm first comment") is the null arm. And the effective arm damages downstream goals (−7.3 to −7.5% on incentivized donations).
2. **"This helps the community" — the most common piece of community advice — measurably reduced contributions** (z=-2.46, p<.01), as did "this helps you" (z=-2.52, p<.01). An LLM will emit this framing by default. It must be an explicit denylist entry.
3. **Public leaderboards cut your best contributors' output by 62%.** Social comparison mobilizes the inactive majority (+530%) and demobilizes the people actually carrying the section.
4. **Telegram reactions are near-useless as a signal:** >95% of all emoji reactions are joy-type, and >84% of *negative* messages get predominantly positive reactions. Yet 84% of users engage with reactions — high participation, zero information.
5. **The politeness axis is not siz/sen.** Uzbek `siz` is fully compatible with casual writing. Politeness lives in `-ing/-ingiz` verb endings; *formality* lives in VOCABULARY (mazkur, ushbu, amalga oshirish, hisoblanadi) and STRUCTURE (labelled sections, stacked connectives). An LLM told "use siz, be friendly" still emits government-announcement prose.
6. **LLM Uzbek fails toward newspaper register, not toward broken grammar.** A critic agent tuned to find grammatical errors will miss the actual failure mode entirely.
7. **A "Tashkent voice" needs LESS dialect marking, not more.** Tashkent dialect is the Qarluq variety closest to literary Uzbek and was the main input to standardization. Casualness comes from syntax and particles.
8. **Perfect apostrophe consistency is slightly super-human.** @mohirdev mixes correct U+02BB/U+02BC with U+0027 across the same post set. Random mixing *within one message* is the actual MT tell.
9. **The naive orthography fix corrupts the text.** "Replace all apostrophes with U+02BB" turns `sunʼiy` into `sunʻiy` — worse than doing nothing.
10. **The channel is not the conversion destination — the bot is.** Identical ads: €2.89/channel subscriber vs €0.91/bot subscriber, purely from removing one step.
11. **Muting is the default state.** 40% have muted every channel; 68.5% mute immediately on subscribing. The channel is a pull medium.
12. **A supposedly free lever costs money:** the €0.02 Uzbek CPM claim is below Telegram's own 0.1 TON floor and is unpurchasable. Real planning range is €0.5–1.5 CPM — two orders of magnitude off.
13. **The "19% x/h errors" statistic does not exist in any accessible source.** The phenomenon is real; the number was invented somewhere upstream.

## Open questions

1. **Does seeding work on Telegram at all, and which valence?** No Telegram experiment exists. Requires the 3-arm post-level randomization in §7. Complicated by the fact that a bot comment is visibly bot-authored (no "post as channel" for bots) — the astroturf read may invert the effect.
2. **Does the contrarian-seed lift survive in a *siz*-register educational channel**, or does it just produce the attitudinal damage without the engagement?
3. **What are the real Uzbek written-comment norms in a Telegram AI-education group?** The only corpus is Uzum e-commerce reviews. Length and lowercase findings likely transfer; **emoji-density findings likely do NOT.** Export ~200 real comments from the operator's own linked group and re-derive.
4. **Russian discourse markers in the operator's own audience.** Off by default. Enable only after the operator exports ~200 real comments from their linked group and validates frequency.
5. **`qoyil` output frequency** — unknowable from any public source; measure in the operator's own group.
6. **Which MT tells actually fire?** Requires the calibration set (Google Translate + Russian→Uzbek, 50 texts) and a false-positive measurement against the mohirdev/texnokun human corpus.
7. **Optimal posting hours for Asia/Tashkent.** No usable external data — Popsters is time-zone-unmappable. Derive from the channel's own Telegram Statistics view-accrual curves (**time-to-50%-of-final-views per post**) over 3–4 weeks; A/B 10:00/21:00 against an alternative pair.
8. **Poll vs open question**, and poll cadence. No evidence anywhere. Alternate poll weeks with open-question weeks; ~6–8 posts per arm.
9. **Payments legality** — whether the bot may link out to an external Payme/Click page for a digital course. Needs legal review, not more searching.
10. **Verify empirically before designing around:** the 100-active-invite-link cap, the Slow Mode interval list, whether Telegram Ads self-serve supports Uzbekistan targeting, and the minimum account top-up (vendor sources quote €10 / €500 / €1,500).
11. **Uzbek peer-channel ER baselines** — pull from Telemetrio/TGStat for a peer set of Uzbek AI-education channels in week 1 instead of importing vendor funnel numbers. Set the project's own baselines from Telegram's native channel Statistics.
12. **Whether an Uzbek alphabet reform (Ç/Ş/Ğ/Ŏ) has taken effect** before hard-coding orthography rules. (unverified)
