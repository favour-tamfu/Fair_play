# Fair Play {VERSION}: start here

Fair Play is one system in three parts. This release has all of them (built from commit {COMMIT}).

| Part | File | Runs on | What it does |
|---|---|---|---|
| **1. SONACAM server** | `FairPlay_Server_{VERSION}.zip` | One Windows computer with Docker Desktop (SONACAM's office or a cloud server) | Receives the meters' reports, recognises the songs, keeps the tamper-proof play log, computes each artist's share, and serves the web pages: the public product page, the sign-in page, SONACAM's app (dashboard and operations) and the artist portal. |
| **2. Meter** | `FairPlayMeter_windows_{VERSION}.zip` | Each bar's meter. During the hackathon: a laptop with a microphone. In the real product: a small sealed box (see the README, "The real product"). | Listens, turns sound into fingerprints (never keeps the sound), seals them with its own key and sends them to the server. |
| **3. Documents** | `FairPlay_Docs_{VERSION}.zip` | — | README (plain-language guide), decisions, the contract between meter and server, plans. |

Not in this release on purpose: the **song package** (audio files and their rights; handed over separately), passwords, keys and the database.

## 1. Install the SONACAM server (about 10 minutes)
1. Install and start **Docker Desktop** for Windows.
2. Unzip `FairPlay_Server_{VERSION}.zip`, for example to `C:\FairPlay`.
3. In PowerShell, in that folder:
   ```
   powershell -ExecutionPolicy Bypass -File .\scripts\install_server.ps1 -SongPackage C:\path\to\Fair_Play_song_package
   ```
   It creates `.env` with new random passwords, starts every part, imports and fingerprints the songs, runs the readiness check, and prints the addresses.
4. Once, in an **administrator** PowerShell, let meters on the network reach the server: `.\scripts\firewall_b.ps1`.
5. **Sign in** at `http://localhost:8000/login.html`:
   - **SONACAM:** name `sonacam`, password = `ADMIN_TOKEN` in `.env`. Give it only to SONACAM staff. It opens SONACAM's app: the dashboard (analytics) and the operations page (meters, activity log, review flags, catalogue, actions).
   - **Artists:** their artist name as in the catalogue. In this prototype every artist's password is `SONACAM`. It opens the artist portal: upload songs with their owners and shares, and see their own songs only.

Addresses (on the server computer): public page `http://localhost:8000/`, sign-in `/login.html`. Other computers on the network use the address the installer prints.

## 2. Install a meter (each bar laptop, about 5 minutes)
1. Unzip `FairPlayMeter_windows_{VERSION}.zip` (for example to `C:\FairPlayMeter`). Python is not needed.
2. Double-click `FairPlayMeter.exe`. Enter the meter id and bar id SONACAM gave, and the server address printed by the installer (`http://<server-ip>:8000`). It makes this meter's own private key and shows its public key file (`contract\meters\<meter>.pub.json`).
3. Sign in as SONACAM, open **Operations › Meters**, and use **Register a meter** with that public key file. (A meter can be retired there too: its reports are then refused.)
4. `FairPlayMeter.exe check` lists the microphones and checks that the server answers.
5. Double-click `FairPlayMeter.exe` again: it starts listening. Keep the laptop plugged in and set it to **never sleep**.
The meter's private key (`device\secrets\`) never leaves that laptop. Details: `README.md` inside the meter zip.

## 3. Check that it all works
- In SONACAM's app, **Operations › Activity log** shows each meter report, every song heard, every play logged, sign-ins and admin actions, live.
- Play a catalogue song near a meter: within about a minute it appears as a play on the dashboard, and in that artist's portal.
- The dashboard's top bar says **Log intact**: the play log has not been changed.

## Verify the files
`SHA256SUMS.txt` lists the SHA-256 of each zip. In PowerShell: `Get-FileHash .\<file>.zip` and compare.
