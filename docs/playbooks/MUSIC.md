# Music Playbook

READ THIS when Chris asks about music, Spotify, playback control, or anything audio-related.

## Data Source Routing (IMPORTANT)

Use sources in this order — do NOT lead with the claude.ai Spotify connector:

1. **Listening history** ("what have I listened to", "have I played X") → **Second Brain** (`listening_history` items, seeded nightly — see Listening History section below)
2. **Playback, devices, playlists, now-playing** → **Hadley API `/spotify/*`** (tables below; uses its own OAuth, independent of claude.ai)
3. **claude.ai Spotify connector** (`mcp__claude_ai_Spotify__*` tools) → LAST resort only, for things the above can't do

**If a claude.ai connector returns an auth error** ("requires re-authorization" / "token expired"):
1. Do NOT stop or just apologise — fall back to Second Brain / `/spotify/*` and answer from there
2. Tell Chris once, briefly: the connector needs re-auth at claude.ai → Settings → Connectors
3. Surface it to #alerts (throttled, safe to fire on every occurrence):
   ```bash
   curl -s -X POST "http://172.19.64.1:8100/alert" -H "x-api-key: $HADLEY_AUTH_KEY" \
     -H "Content-Type: application/json" \
     -d '{"message": "claude.ai Spotify connector token expired — re-auth at claude.ai > Settings > Connectors", "source": "connector-auth"}'
   ```

This applies to ALL claude.ai connectors (Spotify, Gmail, Calendar, Audible…), not just Spotify — adjust the message accordingly.

## Spotify API — Base URL: `http://172.19.64.1:8100`

### Playback Control

| Action | Method | Endpoint | Body |
|--------|--------|----------|------|
| What's playing | GET | `/spotify/now-playing` | — |
| Play (search) | POST | `/spotify/play` | `{"query": "...", "type": "track\|album\|artist\|playlist"}` |
| Play URI | POST | `/spotify/play-uri` | `{"uri": "spotify:album:..."}` |
| Play playlist by name | POST | `/spotify/play-playlist` | `{"query": "focus music"}` |
| Queue a track | POST | `/spotify/queue` | `{"query": "Yellow Coldplay"}` |
| Pause | POST | `/spotify/pause` | — |
| Resume | POST | `/spotify/resume` | — |
| Skip | POST | `/spotify/skip` | — |
| Previous | POST | `/spotify/previous` | — |
| Volume | POST | `/spotify/volume` | `{"level": 50}` |
| Seek | POST | `/spotify/seek` | `{"position_ms": 30000}` |
| Shuffle | POST | `/spotify/shuffle` | `{"state": true}` |
| Repeat | POST | `/spotify/repeat` | `{"state": "off\|track\|context"}` |

### Devices & Transfer

| Action | Method | Endpoint | Body |
|--------|--------|----------|------|
| List devices | GET | `/spotify/devices` | — |
| Transfer playback | POST | `/spotify/transfer` | `{"device": "Max Room"}` |

Device names are fuzzy-matched. Known devices: DESKTOP-PVKHLEQ (Chris's PC), Emmie's Device, Everywhere, Max Room.

### Discovery & Recommendations

| Action | Method | Endpoint | Body |
|--------|--------|----------|------|
| Recommendations | GET | `/spotify/recommend` | — (based on current track) |
| Play similar | POST | `/spotify/play-similar` | — (auto-plays recs) |
| List playlists | GET | `/spotify/playlists?limit=20` | — |

## Natural Language Mapping

| Chris says | Action |
|-----------|--------|
| "play X" / "put X on" | POST `/spotify/play` with search |
| "play some focus music" / "play something chill" | POST `/spotify/play-playlist` |
| "queue X" / "add X to queue" | POST `/spotify/queue` |
| "pause" / "stop the music" | POST `/spotify/pause` |
| "resume" / "carry on" | POST `/spotify/resume` |
| "skip" / "next" / "skip this" | POST `/spotify/skip` |
| "go back" / "previous" | POST `/spotify/previous` |
| "turn it up" / "louder" | POST `/spotify/volume` with +10 from current |
| "turn it down" / "quieter" | POST `/spotify/volume` with -10 from current |
| "volume X" / "set volume to X" | POST `/spotify/volume` with exact level |
| "what's playing" / "what's on" / "what song is this" | GET `/spotify/now-playing` |
| "move to X" / "play on X" | POST `/spotify/transfer` |
| "play something like this" / "more like this" | POST `/spotify/play-similar` |
| "shuffle" / "shuffle on" | POST `/spotify/shuffle` with state=true |
| "my playlists" / "what playlists do I have" | GET `/spotify/playlists` |

## Listening History (Second Brain)

Spotify listening data is imported daily into Second Brain by the seed adapter. This means you CAN answer questions about what Chris has listened to.

**To find listening history, search Second Brain:**
```
curl -s "http://172.19.64.1:8100/brain/search?query=spotify+listening&limit=10"
```

Or use the `search_knowledge` MCP tool with queries like:
- "spotify listening" — daily track summaries
- "spotify top tracks" — monthly top artists/tracks summaries

**Data available:**
- Daily listening summaries (tracks played, artists, duration) — source URLs: `spotify://daily/YYYY-MM-DD`
- Monthly top tracks & artists — source URLs: `spotify://top/YYYY-MM`
- Each item includes track counts, unique artists, and full track listings

| Chris asks | Action |
|-----------|--------|
| "what have I listened to recently" | Search Second Brain for `spotify listening` |
| "what are my top tracks/artists" | Search Second Brain for `spotify top tracks` |
| "what did I listen to on Saturday" | Search Second Brain for `spotify listening YYYY-MM-DD` |
| "how much have I been listening" | Search Second Brain for `spotify listening` and summarise track counts |

## Audiobooks & Podcasts on Spotify

Spotify's recently-played API only returns music, so audiobook/podcast data has its own paths:

| Question | Action |
|----------|--------|
| "what audiobooks do I have on Spotify" | GET `/spotify/audiobooks` (saved library, live) |
| "have I listened to [book] on Spotify" | Search Second Brain for `spotify audiobook [title]` |
| "what podcasts have I been listening to" | Search Second Brain for `spotify podcast` |

**Second Brain audiobook/podcast data:**
- `Spotify Audiobook Listening: <title>` items — total hours, chapters, date range (full history back to 2010, from data export backfill, `spotify://export/audiobook/...`)
- `Spotify Podcasts & Audiobooks — YYYY-MM-DD` daily items — from the 5-min playback poller (live going forward, includes progress position, `spotify://playback/...`)
- `Spotify Audiobook: <title>` items — saved library snapshot
- Music history: monthly summaries 2010→now (`spotify://export/music/YYYY-MM`) + daily/weekly items

**Gotcha:** a book appearing with ~0.0h hours was just browsed/sampled, not listened to. Real listens have meaningful hours (e.g. 12h = a full book).

## Response Style

- Keep responses short and natural: "Playing Parachutes by Coldplay" not a wall of JSON
- For now-playing, format like: "**Yellow** by Coldplay — from *Parachutes* — on your PC at 66%"
- For volume changes, confirm: "Volume set to 50%"
- If no device is active, tell Chris to open Spotify on a device first
- The now-playing endpoint includes mood data (valence, energy, danceability) — use this contextually, don't dump raw numbers

## Smart Behaviours

- For "turn it up/down" without a number: fetch current volume first via `/spotify/now-playing`, then adjust by +/- 10
- For ambiguous queries like "play Coldplay": default to type=artist (plays their top tracks)
- For "play X album": set type=album
- For "play X song/track": set type=track
- When Chris says a playlist name, try `/spotify/play-playlist` first (searches his playlists), falls back to global search
