# CBJ competitors, their ads, and success/fail scenarios for our tool (2026-10-10)

How this was researched:
- Three research agents worked on it.
- About 136 real video ads were downloaded from the **Meta Ad Library** and checked frame by frame.
- Market data came from AppMagic, Naavik, Mobidictum and PocketGamer, plus the iTunes API and store pages.
- Performance and policy evidence came from AppsFlyer, academic papers, ASA rulings and platform rules.

Every ad link opens in a browser. Ads that have stopped running may no longer open.

Evidence files:
- `~/cbj-work/ad-research/2026-10-10-meta-ad-library/` (notes and contact sheets)
- `~/cbj-work/ad-research/2026-10-10-top3-competitors/` (frame sheets, screenshots, scrape data, scripts)

---

## 1. Bottom line

1. **The top 3 competitors are Block Out!, Pixel Flow! and Magic Sort!**
   - Block Out! and Magic Sort! are by Grand Games (Istanbul). Pixel Flow! is by Loom Games, which Scopely has majority-owned since February 2026.
   - Block Out! is an almost exact copy of CBJ. It even copies CBJ's ad hooks.
2. **Almost no one shows a real gameplay fail.**
   - Across about 136 ads from CBJ and its rivals, the dominant ending is **unresolved**: the video cuts mid-level and nobody wins or loses.
   - Only **Wool Crush** shows an explicit "FAIL".
   - Rivals often *say* "only 1% can solve this" but never show the fail.
3. **CBJ itself avoids staged fails and rarely shows its timer.** In the CBJ ads we checked, exactly one gameplay ad shows the countdown, and it ends in a comfortable win.
4. **A near-fail ending is unused territory.** That means a real level won at 0:01 with the timer red and shaking. No rival runs it, the research supports it, and CBJ's own YouTube brand film tells this story emotionally ("Frustratingly Fun!", 2.27M views). This is a strong differentiator for the brief.
5. **What works depends on the channel** (AppsFlyer 2025):
   - On **ad networks** (AppLovin, Unity Ads), **success** endings get more installs.
   - On **social** (Meta, TikTok), **failure** endings get more.

   So the tool should make the *ending* one switch and render matching pairs.

---

## 2. The top 3 competitors

| | **Block Out! – Color Sort Puzzle** | **Pixel Flow!** | **Magic Sort!** |
|---|---|---|---|
| Publisher | Grand Games A.Ş. | Loom Games A.Ş. (Scopely majority owner since Feb 2026) | Grand Games A.Ş. |
| Store | [App Store](https://apps.apple.com/us/app/id6752672568) · Play `com.grandgames.catblockjam` | [App Store](https://apps.apple.com/us/app/id6751056652) · Play `com.loomgames.pixelflow` | [App Store](https://apps.apple.com/us/app/id6499209744) · Play `com.grandgames.magicsort` |
| Launched | 2025-10-31 | 2025-08-17 | 2024-05-28 |
| Gameplay vs CBJ | **Almost the same**: slide coloured blocks to matching targets | Clear same-colour pixels; you fail when the tray fills (no countdown) | Liquid sorting; low similarity |
| Market evidence | 295,746 US iOS ratings (CBJ: 138,977); #2 in Casual. With Magic Sort it was #1 and #2 in US iOS downloads (~11M downloads and $11M in-app purchases in 30 days) | $198.4M gross and 34M installs in its first year | ~$50M in 2025; 675,508 US iOS ratings |
| Meta ads (active) | **~720**; the oldest still running since 1 Jul 2026 (101 days) | ~75, all started 1–9 Oct 2026 | ~160 |
| All their ads | [Meta page](https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=ALL&view_all_page_id=759030133968216) | [Meta page](https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=ALL&view_all_page_id=762604410262352) | [Meta page](https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=ALL&view_all_page_id=270275292836352) |
| Why chosen | Closest gameplay, fastest growth, most ads | The category's biggest new hit | Grand Games' cash cow; long-running winners are visible |

**For comparison, CBJ (its publisher):**
- Store: [App Store](https://apps.apple.com/us/app/id6504332779) · Play `com.GybeGames.ColorBlockJam`, released 2024-06-28.
- $42M revenue and 21.8M downloads in Q2 2025, about 75% of the block-puzzle subgenre.
- All of its ads: [Meta page](https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=ALL&view_all_page_id=108573341889195) (about 530 active).

**Runners-up:**
- **Arrows – Puzzle Escape** (Lessmore GmbH). It has the closest "escape" gameplay and 100M+ Play installs. No official Meta ads were found, only clones; Google shows about 1,000 Lessmore ads. Swap it in for Magic Sort if gameplay similarity matters more than ad volume.
- **Wood Away** (iKame): identical gameplay including a timer, but small.
- **Bus Escape**, **Screwdom** and **Block Blast!** are farther from CBJ's mechanic.

**Clone alert.** A Meta page named "CBJ" (page `756222637565654`) is **not the publisher**; it links to "Block Color Mania". Its ads attack CBJ's timer with "NO TIMER! No timers. No stress. Just fun." Example: https://www.facebook.com/ads/library/?id=955285320353998

---

## 3. Their ads (real links), tagged by how they end

**Endings:**
- **UNRESOLVED:** cut mid-level, nobody wins or loses.
- **WIN:** the level is completed.
- **NEAR-FAIL WIN:** won with seconds left.
- **FAIL:** a fail is shown.

### CBJ
| Ad | Hook | Ending |
|---|---|---|
| https://www.facebook.com/ads/library/?id=1252903916980534 | Real carpet-cleaning clip, then "I cannot reach green" | UNRESOLVED |
| https://www.facebook.com/ads/library/?id=1641370094214961 | "I can't reach colors" | UNRESOLVED with **2 blocks left** (closest to a near-clear) |
| https://www.facebook.com/ads/library/?id=972412472219824 | "If you can solve this, your IQ is 140", plus a live **Brain Age** counter | UNRESOLVED |
| https://www.facebook.com/ads/library/?id=4721638468068832 | "You cannot solve this" | UNRESOLVED, then a "Choose the next level!" card |
| https://www.facebook.com/ads/library/?id=1737379554208675 | "Want a chance to win £10,000?" (UK sweepstakes) | UNRESOLVED |
| https://www.facebook.com/ads/library/?id=2206396276604381 | Split screen: real Level 576 plus a hydraulic press (ASMR) | **WIN, the only CBJ ad with a visible timer** (03:30 → 02:27) |
| https://www.facebook.com/ads/library/?id=546296828285012 | Level montage: 138 → 45 → 1 → 2 | Progress |
| https://www.facebook.com/ads/library/?id=809086025180843 | Creator skit: "When your husband has ADHD…" | Creator video |
| https://www.youtube.com/watch?v=OiAdy4LNwSM | "Frustratingly Fun!" brand film (2.27M views) | **NEAR-FAIL → WIN** as an emotional story, no gameplay |

### Block Out!
| Ad | Hook | Ending |
|---|---|---|
| https://www.facebook.com/ads/library/?id=1277780310899283 | "I can't reach colors.." (running since 1 Jul 2026, **likely a winner**) | UNRESOLVED |
| https://www.facebook.com/ads/library/?id=1108296531873517 | Street crowd, "Only 1% can solve this puzzle." | UNRESOLVED, then "why is this so hard?!" |
| https://www.facebook.com/ads/library/?id=3948700678760036 | The board built from real toy bricks | UNRESOLVED |
| https://www.facebook.com/ads/library/?id=1418950530322410 | Tweezers "plating" tiles on a dinner plate | UNRESOLVED |

### Pixel Flow!
| Ad | Hook | Ending |
|---|---|---|
| https://www.facebook.com/ads/library/?id=1064518776342891 | "Relaxing Puzzle, Pure Flow" | UNRESOLVED |
| https://www.facebook.com/ads/library/?id=1710357384083734 | Brand montage: "NO ADS!", "TRAIN YOUR BRAIN" | WIN beat (a picture completes) |
| https://www.facebook.com/ads/library/?id=1575792674108490 | "ONLY 1% CAN BEAT THIS LEVEL." | Cut just before failing |

### Magic Sort!
| Ad | Hook | Ending |
|---|---|---|
| https://www.facebook.com/ads/library/?id=1785537872874289 | Pure gameplay | UNRESOLVED |
| https://www.facebook.com/ads/library/?id=1071112145609188 | CG bottles shattering, then Level 82 | UNRESOLVED |
| https://www.facebook.com/ads/library/?id=1097363532981005 | "Only 1% can solve" whiteboard | UNRESOLVED |

### Other games worth knowing
| Game | Ad | What it shows |
|---|---|---|
| **Wool Crush** | https://www.facebook.com/ads/library/?id=1161179599552873 | **The only explicit FAIL ad found:** danger approaches, red pulses flash at the screen edges, a red "FAIL" badge appears (57 s) |
| Car Out | https://www.facebook.com/ads/library/?id=1410133353578163 | An angry stickman, "Help the cars out!"; UNRESOLVED |
| Bus Go | https://www.facebook.com/ads/library/?id=1474062343880832 | An angry driver ("Hey, Move!!!") |
| Hole People | https://www.facebook.com/ads/library/?id=1182498880353884 | "Before your board overflows!" in the text, but no fail in the video |
| Block Blast! | https://www.facebook.com/ads/library/?id=850087581190001 | **WIN**: combo counters, "ALL CLEAR" |
| Knit Out (same publisher) | https://www.facebook.com/ads/library/?id=2423890571454613 | An EASY / MEDIUM / HARD / PRO choice |

### Endings compared
| | WIN | NEAR-FAIL | FAIL | UNRESOLVED | Timer shown |
|---|---|---|---|---|---|
| CBJ | 1 | 1 (brand film only) | 0 | **most** | 1 gameplay ad |
| Block Out! | 0 | 0 | 0 | all | never |
| Pixel Flow! | 1 | 0 | 0 | most | – |
| Magic Sort! | 0 | 0 | 0 | all | never |
| Wool Crush | – | – | **yes** | yes | – |

---

## 4. What works, and what is allowed

**Performance:**
- **The best ending depends on the channel.** This is from the AppsFlyer State of Creative Optimization 2025 (1.1M creatives, Q1'24 to Q1'25):
  - In Casual games (Puzzle included), **"Pure Success" endings get 33% more installs per 1,000 impressions on ad networks**.
  - On social and search, **"Pure Failure" gets 65% more**.
  - In hypercasual, **failure-then-success** gets over 4x the installs of pure success on ad networks. But pure success keeps almost double the day-7 players.
- **A real field test** (Luan & Li 2022, a short-video platform, N=9,993): **fail ads got 2.12% clicks vs 1.24%** for success ads. The effect held only when the task looked easy, and only for competitive viewers.
- **Near-miss** (Larche et al. 2017, Candy Crush players): losing by 1–2 moves gave the strongest urge to keep playing.
- **Medium difficulty beats extreme** (Moon et al. 2026). Failing a *reasonably* hard level makes people want to download more than failing an impossible one.
- **Unresolved endings** (Dai et al. 2024): cutting before the result raised willingness to play from 5.17 to 6.75 out of 10, driven by curiosity. Don't claim the Zeigarnik "better memory" effect; a 2025 meta-analysis found it doesn't hold.
- **Share of spend, not performance** (AppsFlyer 2026 via GameDevReports): 54.5% of "Puzzle & Lifestyle" ad-network spend goes to videos where the player loses.

**Allowed** (UK ASA rulings and Apple / Google / Meta / TikTok / AppLovin rules):
- Use only **real gameplay from main levels**, with the **real timer** and the **real fail screen**.
- **No invented odds** like "only 1% can solve this". The ASA ruled against Playrix's "ONLY 5% CAN SOLVE THIS"-style ads.
- In the UK, mention in-game purchases.
- Any AI-made segment, such as a hook or outro, must be clearly separate from gameplay. TikTok requires AI content to be labelled.

---

## 5. How to find these ads yourself

**Meta Ad Library (free, no login)**
1. Open https://www.facebook.com/ads/library/, set **Country: All** and **Ad category: All ads**.
2. Type the game name and **pick the official page from the dropdown**. Keyword results mix in clones.
3. Or open a game's page directly by replacing the number in: `https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=ALL&media_type=video&view_all_page_id=<PAGE ID>`. The IDs are:
   - CBJ: 108573341889195
   - Block Out!: 759030133968216
   - Pixel Flow!: 762604410262352
   - Magic Sort!: 270275292836352
4. **To spot winners:** look for an old "Started running on" date on an ad that is still active, plus a high "N ads use this creative" count. Many ads starting on the same day are a test batch.
5. **To keep a copy:** use Cmd+Shift+5 to record the screen while it plays, or open DevTools → Network → filter "mp4".

**TikTok Creative Center:** https://ads.tiktok.com/business/creativecenter/inspiration/topads/pc/en
- It needs a free TikTok for Business login.
- Then set Industry = Games, Objective = App installs, and Last 30 or 180 days.
- "See analytics" shows second-by-second viewer retention.

**Google Ads Transparency Center:** https://adstransparency.google.com/?region=anywhere
- Search the companies' legal names: "GRAND GAMES OYUN VE YAZILIM ANONİM ŞİRKETİ", "Loom Games Oyun Yazilim Ve Pazarlama Anonim Şirketi", "Lessmore GmbH".
- Filter Format = Video. Each ad shows its first and last shown dates.
- the publisher didn't appear under its own name; it may be under "Zynga Inc." (unverified).

**YouTube:** search "<game> ad" and check the publisher's channel. A short brand video with millions of views is usually a paid ad.

**Paid tools:**
- AppMagic and Sensor Tower: free charts; the ad data is paid.
- SocialPeta, AppGrowing and BigSpy: creative search, behind login or trial.
- AdMapix and Segwise: free blog teardowns.

---

## 6. Success and failure scenarios for our tool (proposed)

Every scenario plays a **real, solvable level** with **legal moves** from our solver, in the real game. Each is tagged:
- **on-brand:** CBJ itself runs this;
- **competitor-proven:** rivals run it;
- **new:** nobody runs it yet, but research supports it.

| # | Scenario | Ending | What the gameplay script does | Tag | Evidence |
|---|---|---|---|---|---|
| S1 | **Cliffhanger** | Unresolved | Optimal solve, cut with **1–2 blocks left** | on-brand (CBJ's main ending) | All four games; Dai 2024 |
| S2 | **"I can't reach <colour>"** | Unresolved, or a win after the trapped block exits | Clear the blockers around a trapped block; the hook names its colour | on-brand (CBJ, Block Out) | Meta ads in section 3 |
| S3 | **Satisfying clean win** | WIN | Optimal solve at a steady pace, timer visible, exit cascades, "LEVEL COMPLETE" | on-brand (CBJ 2206396276604381) | AppsFlyer: success wins on ad networks |
| S4 | **Near-fail win** | NEAR-FAIL WIN | Hesitation plus 1–2 believable wrong moves; the timer goes **red and shakes** (built into the game below 0:50); the last block exits at **0:01–0:03** | **new** (gap; matches CBJ's brand film) | Larche 2017; Moon 2026 |
| S5 | **Time-out fail, 1 block left** | FAIL | Slow, plausible play on a **medium-hard** level; the timer hits 0:00 with **one** block left; the real fail screen shows | competitor-proven (Wool Crush) but **not CBJ's style**, so for social A/B tests only | AppsFlyer social +65%; Luan & Li |
| S6 | **Fail, then win** | FAIL → WIN | S5, then retry and the clean solve from S3 | new for this genre | AppsFlyer: failure-to-success 4x installs on ad networks |
| S7 | **Brain Age / IQ overlay** | Any | Any of the above, with a live counter overlay | on-brand (CBJ) | Insightrackr; Meta ads |
| S8 | **Level montage** | Progress | Several short level clips, rising level numbers | on-brand (CBJ) | Meta 546296828285012 |

**Rules for every scenario:**
- Only real game levels and the real fail screen.
- No "only 1%" or "IQ" claims stated as facts; CBJ's "your IQ is 140" is a dare in quotes, not a statistic.
- Fail scenarios only on medium-hard levels, using mistakes that read as "I could avoid that".
- Every render stores its level file and move log as proof.

**Cuts:** 15 s, 30 s and 60 s. The hook lands in 0–3 s and the result in the last seconds before the end card.

**What our solver needs to add for these:**
1. A timing model: seconds per cell moved, pauses between drags, and the 0.1 s snap, then a 0.1 s gate dip and a slide of (cells to the edge + 2) x 0.1 s (corrected 2026-10-10 from the game's `ExitService.PerformExit`).
2. Legal "wrong moves" and pick-up-and-put-back hesitations; the replay checker already accepts both.
3. A level timer chosen so the clock lands exactly where the scenario needs it (0:01 left, or 0:00 with one block left).
4. A cut point for cliffhangers.

**Decision (2026-10-10):**
- Default endings are S3 (win), S4 (near-fail win) and S1 (cliffhanger).
- S5 is opt-in, for explicit fail requests or social-channel tests only.
- S6 is timeboxed.

The reasons are in RUNNER-REPORT-2026-10-10.md, "Decisions".

---

## 7. Corrections to earlier notes
- **The top 3 are Block Out!, Pixel Flow! and Magic Sort!** Car Out and the bus games, which I guessed from ads alone earlier today, are further away by market data.
- **AppsFlyer's "33%" and "54.5%" come from different reports.** One measures performance in 2025; the other measures share of spend in 2026. Fixed in `RESEARCH-TOOLS-PAPERS-2026-10-09.md`.
- **"CBJ never shows a timer" was too strong.** One CBJ ad (2206396276604381) shows the countdown and a win.

## 8. What could not be checked
- TikTok Creative Center needs a login.
- the publisher wasn't found under its own name in Google Ads Transparency.
- AppLovin and Mintegral ads can't be viewed publicly. They carry about 49% of CBJ's ad-network share.
- Paid tools weren't used.
- Ad audio wasn't transcribed, so voiceover lines are unverified.
- The Meta scrape covered 343 of about 530 CBJ ads and 318 of about 720 Block Out ads.
