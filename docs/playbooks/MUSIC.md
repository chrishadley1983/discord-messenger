# Music Playbook

READ THIS when Chris asks about music, Spotify, playback control, or anything audio-related.

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
