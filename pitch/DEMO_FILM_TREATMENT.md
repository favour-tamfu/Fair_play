# Fair Play — demo film treatment (2:00 max, motion graphics)

## The idea in one line
**Follow one song**: it plays in a maquis in Douala, becomes a constellation of fingerprint dots, flies across Cameroon, lands
as a square on the SONACAM chart, and ends as a fair share on the artist's phone. One continuous journey, told with match cuts.

## Rules the film follows (from film/motion-design practice)
- **Hook in the first 3–5 s**, problem in ~15 s, solution in one sentence, then show the product. Most of the time = product.
- **Voice-over 240–260 words** for 2:00 (≈130–140 words/min; faster than 160 feels rushed). Leave 2–3 s of silence for the reveal.
- **Kinetic type**: short words, each on screen ~5–7 frames at 24/25 fps when it pulses with the beat; key lines held 1.5–2 s.
- **One visual language, Apple values**: black and #f5f5f7, white type in SF Pro Display semibold, one accent blue (#0071e3/#2997ff),
  covers as the only colour. No gradients on text, no 3D bevels, no stock "tech" swooshes.
- **Motion feel**: everything eases (ease-in-out, overshoot ≤ 5 %), nothing moves linearly; objects have weight and settle.
- **Every transition is a match cut** (shape or motion carries to the next scene): no wipes, no dissolves except the final fade.
- **Music decides the cut**: pick the track first, cut on the beat (≈100–110 BPM Afro/makossa groove). The track must be licensed —
  this is a film about paying artists: use a song from our catalogue with the artist's written OK, or a royalty-free/CC-BY track credited.
- **Numbers on screen only if the code computed them**, and simulated ones say so on screen ("simulated month").
- **Pipeline**: script → scratch voice-over → animatic (storyboard frames + temp music + VO, timed) → 3 style frames → animate →
  final VO → sound design → grade/export. Lock timing in the animatic; don't animate before the animatic plays well at 2:00.

## Shot list (timecodes = target)
| # | Time | Picture (motion) | Voice-over | Sound |
|---|---|---|---|---|
| 1 | 0:00–0:05 | Black. A beer cap pops off in macro; the cap spins, flips and becomes a coin (match cut). | "Every drink sold in a Cameroonian bar pays for music." | cap pop, coin ring, beat drops |
| 2 | 0:05–0:18 | The coin splits into identical slices pushed to a row of artist names, equal no matter what (flat split). Several names barely played still get the same slice; type: **"Shared by guess."** | "But nobody knows what really played. So the money is shared as a guess." | music thins out |
| 3 | 0:18–0:24 | Slices collapse to a single white dot → the Fair Play wordmark. | "Fair Play counts what really plays." | one clean hit, then silence 1 s |
| 4 | 0:24–0:38 | Photo of a maquis (our party/bar photos), speaker pulsing. A small meter beside it. The sound wave from the speaker freezes into **peaks** (dots), the dots form a constellation. Type: **"No sound leaves the bar."** | "A small meter beside the speaker listens for songs, never for people. It keeps only fingerprints." | room tone → muffled, a tick per dot |
| 5 | 0:38–0:50 | The constellation lifts off, shrinks to a point and flies onto the map of Cameroon (our map outline); 15 bars light up in 8 cities. | "Every metered bar, every night, across the country." | whoosh, soft pings per city |
| 6 | 0:50–1:08 | The point lands on the **real dashboard** (screen capture, slow push-in): the live feed adds the song, a square drops into the dot-matrix chart, columns grow. | "Within seconds, SONACAM sees which song played, where, and when." | UI clicks, chart squares tick on the beat |
| 7 | 1:08–1:25 | A square from the chart flies into an **iPhone**: the Artists page — cover hero, Top songs, "Bars that played this artist". | "And artists see it too: every bar that played them, every song." | lift, small chime |
| 8 | 1:25–1:38 | Play log as a chain of blocks; one block is edited, the chain snaps red, the dashboard banner turns red: **"Results withheld."** | "Every play is sealed to the one before. Change one, and the results stop." | glass crack, red pulse, music drops out |
| 9 | 1:38–1:52 | Back to the coin from shot 2: now the slices resize by plays. Big number **7,7×** with caption **"less money to the wrong artists — simulated month"**. Type: **"Bars pay nothing extra."** | "The same levy, shared by what really played. Bars pay nothing extra." | music returns full |
| 10 | 1:52–2:00 | Black. **"Every play counts."** Wordmark, "CIMFEST Hackathon 2026", team names. | "Fair Play. Every play counts." | final hit, 1 s tail |

Voice-over total ≈ 175 words (room to breathe; add at most ~60 words if needed).

## Assets we already have
- Real UI to screen-record: landing (`web/index.html`), dashboard (`web/sonacam-x7k2q9.html`), Artists page, portal.
  Record at 1920×1080 or 2560×1440, browser full screen, mock data replay or live against B.
- Album covers (`web/assets/covers/`), bar photos (`web/assets/img/`, Pexels/Unsplash licences — credit them), Cameroon map outline
  (`web/js/cameroon.js`), the chart and chain designs.
- Numbers the code computes: plays counted, meters online, 15 bars / 8 cities, 31.4 % vs 4.1 % and 7,7× (simulated month).

## Tools (pick one track)
- **Fast, free:** Jitter (web motion tool, good for UI + type), screen captures in OBS, edit + sound in DaVinci Resolve (free) or Clipchamp.
- **Full control:** After Effects (shape layers for dots/map, text animators for type) → Premiere/Resolve for the edit.
- Voice: a calm, clear voice; record in a quiet room or a closet, phone close to the mouth; or a licensed AI voice if the rules allow.

## Schedule (fits before 12:00)
1. 30 min — finalise VO script, pick music, record scratch VO.
2. 45 min — animatic: stills of each shot on the timeline with VO + music at 2:00.
3. 30 min — screen recordings (shots 6–8) and 3 style frames (shots 1, 4, 9).
4. 2–3 h — animate shots 1–5, 8–10; drop screen recordings into 6–7.
5. 30 min — final VO, sound effects, mix (music −18 LUFS under VO), export 1080p H.264, check on a phone.

## Don't
- Don't open on the logo or the team; open on the cap.
- Don't show code, terminals, keys, the admin page's meter keys or the device\secrets folder.
- Don't present simulated numbers as real ones, or song play counts as real popularity.
