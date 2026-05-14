# Prolific Studies Monitor

Polls `app.prolific.com/studies` every 60–90s during waking hours (08:00–23:00 UK)
and posts a Discord webhook for every newly-spotted study.

Uses **CDP-to-real-Chrome** on a dedicated `Chrome-Prolific` profile (port 9224)
to avoid the `--enable-automation` fingerprint that Playwright's launched
Chromium leaks. Same pattern as the Vinted sniper.

## One-time setup

### 1. Create a Discord webhook

In Discord: Server Settings → Integrations → Webhooks → New Webhook. Point it
at the channel you want alerts in. Copy the URL.

### 2. Add the webhook to `.env`

```env
DISCORD_WEBHOOK_PROLIFIC=https://discord.com/api/webhooks/...
```

If unset, alerts fall back to `DISCORD_WEBHOOK_ALERTS`.

### 3. Log in to Prolific (one time)

```powershell
cd "C:\Users\Chris Hadley\claude-projects\discord-messenger"
python -m domains.prolific.login
```

A real Chrome window opens against `app.prolific.com/login`. Sign in (Google or
email). Confirm you can see `/studies`. Press Enter in the terminal to close.

Cookies persist in `%LOCALAPPDATA%\Google\Chrome-Prolific`. Subsequent monitor
runs reuse the session headlessly.

### 4. Restart the bot

```powershell
Restart-Service DiscordBot   # admin shell
```

Look for `Prolific monitor registered (75s ± 15s, active 08:00-23:00 Europe/London)`
in `bot.log`.

## Config knobs

All optional, set in `.env`:

| Var | Default | Purpose |
|---|---|---|
| `PROLIFIC_CDP_PORT` | `9224` | CDP port for Chrome-Prolific (must differ from Vinted's 9222 and SeedImport's 9223) |
| `PROLIFIC_PROFILE_DIR` | `%LOCALAPPDATA%\Google\Chrome-Prolific` | Dedicated Chrome profile |
| `PROLIFIC_CHROME_EXE` | `C:\Program Files\Google\Chrome\Application\chrome.exe` | Chrome binary |
| `DISCORD_WEBHOOK_PROLIFIC` | — | Channel webhook (falls back to `DISCORD_WEBHOOK_ALERTS`) |

Poll cadence, active hours, and embed colour thresholds live in
`domains/prolific/config.py`.

## How it works

1. `bot.py` registers `poll_studies` on APScheduler (75s interval, 15s jitter).
2. Outside 08:00–23:00 UK, the job returns immediately.
3. Inside active hours, `chrome.ensure_chrome_running()` spawns Chrome-Prolific
   headless via `subprocess.Popen` if it isn't already up.
4. Playwright `connect_over_cdp` attaches, navigates `/studies`, waits 3.5s for
   render, runs an in-page JS extractor that finds every `a[href*="/studies/"]`
   and pulls the surrounding card text.
5. Python parses titles, `£X • £Y/hr`, `N mins`, `M places`, tags.
6. SQLite (`data/prolific_seen.db`) dedupes against already-alerted IDs.
7. New studies → Discord embed coloured by hourly rate (green ≥£10, amber ≥£7, red <£7).

## When it stops working

- **Bot logs `Prolific session expired — login page hit.`** → re-run
  `python -m domains.prolific.login`.
- **Bot logs `Chrome-Prolific failed to open CDP port 9224`** → another process
  may already be using the port; check `Get-NetTCPConnection -LocalPort 9224`.
- **No embeds despite studies being visible** → Prolific changed their DOM;
  check the `_EXTRACT_JS` selector in `scraper.py` against the live page.
