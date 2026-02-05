# Peter Dashboard

Web UI for monitoring the Peterbot Discord bot system.

## Features

- **Service Status**: Real-time status of Hadley API, Discord Bot, Claude-mem, and Peterbot tmux session
- **Tmux Sessions**: View all tmux sessions and capture their screen content
- **Context Viewer**: See the context.md being sent to Claude Code with each message
- **Screen Captures**: View raw screen captures for debugging response parsing
- **Memory Browser**: Browse recent memory observations from claude-mem
- **Key Files**: View and browse key configuration files (CLAUDE.md, SCHEDULE.md, etc.)
- **API Endpoints**: List all 100+ Hadley API endpoints
- **Service Control**: Restart services (Hadley API, Discord Bot, Peterbot session)
- **WebSocket Updates**: Real-time status updates every 5 seconds

## Quick Start

```bash
cd peter_dashboard
python -m uvicorn app:app --host 0.0.0.0 --port 5000
```

Or double-click `start.bat`

Then open http://localhost:5000

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Dashboard HTML |
| `GET /health` | Health check |
| `GET /api/status` | System status (all services) |
| `GET /api/files` | List key files |
| `GET /api/file/{type}/{name}` | Get file content |
| `GET /api/context` | Current context.md |
| `GET /api/captures` | Recent screen captures |
| `GET /api/screen/{session}` | Tmux screen capture |
| `GET /api/memory/recent` | Recent memory observations |
| `GET /api/hadley/endpoints` | Hadley API endpoint list |
| `POST /api/restart/{service}` | Restart a service |
| `WS /ws` | WebSocket for real-time updates |

## Services Monitored

- **Hadley API** (port 8100): REST API for Gmail, Calendar, Weather, etc.
- **Discord Bot**: Python bot.py process
- **Claude-mem** (port 37777): Memory system worker
- **Peterbot Session**: tmux claude-peterbot session running Claude Code

## Requirements

```
fastapi>=0.100.0
uvicorn>=0.23.0
httpx>=0.24.0
websockets>=11.0
```
