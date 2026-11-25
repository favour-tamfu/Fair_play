# Fair Play song package v3 (test set, for partner review)

## What is new in v3
- 19 new songs: FP-165 to FP-183. The 164 songs from v1 and v2 are unchanged in audio and metadata. Total: 183 songs in `audio/`.
- Every batch 3 and 4 "unknown" row was researched again (88 rows). Results:
  - 19 promoted to the catalogue (kept, see `catalogue.csv`, source_urls).
  - 2 excluded: Gloria Bash (Wikipedia: Congolese) and AFROSAO (Chadian).
  - 4 left as `unknown` with the decision marked "NEEDS TEAM DECISION": Tayc (3 songs) and Ines D (1 song). The evidence is in `not_included.csv`.
  - 63 still `unknown`. Each reason in `not_included.csv` says what was searched.
- The reasons for the 63 still-unknown songs were rewritten. Most have an Apple Music title match but no verifiable Cameroonian lead, or the reverse.
- Artists: King Luca, Tim Kayzer, Yvi Atia, Raizy and Cabrel Nanjip are new lead artists. Santrinos Raphael, Fanicko, Annie Anzouer and Papy 2PP are new featured-only names.
- Cabrel Nanjip (FP-180) died in June 2023. Rights holders are not known.
- FP-172 (Viviane, Assiko Remix) is `title_status = tentative`: Apple lists the same artists under "Vivianne (Remix)". Please check.
- FP-176 (Ma Ba Nze) is a cover per the file name; Apple lists Ulanda's release of this title.
- Duplicates: no new duplicates were added. The 11 duplicates from v2 are unchanged (`duplicates.csv`).

| | v2 | v3 |
|---|---|---|
| songs in audio/ | 164 | 183 |
| not_included rows | 161 | 142 |
| unknown rows (batch 3-4) | 88 | 67 (63 unknown + 4 needs team decision) |
| excluded rows (batch 3-4) | 12 | 14 |

Sources for each promoted song are in `catalogue.csv` (`source_urls`): the Apple Music match and the lead artist evidence.

---

# Previous notes (v2)

## What is new in v2
- Two more archives were added: batch 3 (148 files) and batch 4 (67 files).
- 104 new songs: FP-061 to FP-164. The 60 songs from v1 (FP-001 to FP-060) are unchanged in audio and metadata.
- 164 songs in total, in `audio/`.
- 100 new rows were left out (`not_included.csv`): 12 excluded (verified non-Cameroonian lead, or DJ mixes) and 88 unknown (not verified). The table below gives the split.
- 11 new duplicates were not copied (`duplicates.csv`).
- The database was rebuilt with the batch 3-4 artists and the same schema.

| | batch 3 | batch 4 | total new |
|---|---|---|---|
| files in archive | 148 | 67 | 215 |
| kept (new songs) | 71 | 33 | 104 |
| excluded (not Cameroonian lead, or DJ mix) | 8 | 4 | 12 |
| unknown (not verified) | 63 | 25 | 88 |
| duplicates (not copied) | 6 | 5 | 11 |

(Totals: 104 + 12 + 88 + 11 = 215.)

## Where the songs come from
- v1: playlist_songs_archive.zip (84 files) and playlist_songs_archive_2.zip (37 files).
- v2: playlist_songs_archive_3(1).zip (148 files) and playlist_songs_archive_4.zip (67 files).
- Only songs whose lead artist was confirmed as Cameroonian are included. Featured artists may be foreign.

## How each song was checked
- Lead artist nationality: from a press or encyclopaedia source (Cameroon Tribune, Music in Africa, camer.be, Afrik, 237online, Wikipedia), or from a streaming-platform artist profile (Apple Music). A profile on an aggregator site alone (LiveOne, Viberate, afrobirthdays, Profileability) was not enough, so those artists are `unknown`.
- Song title and artist: matched against Deezer or iTunes (title and artist both matched). The match link is in `source_urls`. Titles not matched are not included.
- Featured artists: kept only when the platform credit (Deezer or iTunes) names them.
- Duplicates: sha256, normalised title+artist, and audio fingerprint (fp-1.0) against all 273 songs (60 v1 plus 213 batch 3-4). Only strong fingerprint matches were treated as duplicates.

## What is still missing before any upload
- Owners (singer, composer, producer, shares), MoMo and consent for every song. Nothing is ready to upload to SONACAM yet.
- ISRC and ISWC: not known. Left blank.

## Known limits (please read)
- Many artists could not be verified (see `not_included.csv`, decision `unknown`), for example AlemsKen, King Luca, Tim Kayzer, Chako, Mr Biyong, Elisha K, Petit Bozard, Kankan Boys, Watto de Souza. A song is excluded when its lead artist or its title could not be verified. It is not a judgement about the song.
- Borderline: Tayc (French-born, of Cameroonian origin) and Ines D (Cameroonian-born, US-based) are `unknown`, not included.
- Chako is listed by Cameroon Tribune as an alias of Tzy Panchak. The Chako songs are `unknown` until that is confirmed.
- "Culture & Money" (FP-097) was matched by hand: Apple Music lists it as "Culture and Money", the same song.
- Featured credit "Happy" on "La Fête" (Boy Tag, FP-139) comes from the Apple Music credit. Who that Happy is has not been established.
- Artist origin for several artists (for example Ngoma, Vernyuy Tina, Happy d'Efoulan, Fhish) rests on press articles, not on the artists' own statements.
- Possible overlap in v1 (not changed here): FP-003 "Kam We Stay" and FP-006 "Mimbayeur" (both Blanche Bailly) gave a strong shared-audio fingerprint match. Please listen to both before treating them as separate songs.

## Artists in this set
See `catalogue.csv` (`artist_name`, `featured_artists`) and `database/fairplay_catalogue.sqlite` (table `artists`). 55 lead artists; 87 names in total with featured artists.

## Tags embedded in each audio file
title, artist, album_artist, album ("Fair Play test set"), and a comment with the song_id, the source file's SHA-256 and the featured artists. Owners, ISRC, ISWC and consent are not in the tags.
