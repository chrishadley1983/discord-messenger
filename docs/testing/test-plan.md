# Peter Channel Architecture — Test Plan

## Overview

Comprehensive test plan covering the channel migration, fallback paths, resilience, and ongoing operation. Tests are grouped by priority — CRITICAL tests must pass before holiday, HIGH tests should pass, MEDIUM tests are nice-to-have.

---

## 1. Channel Sessions — Core Functionality

### 1.1 Discord Channel (CRITICAL)

| # | Test | Steps | Expected | Status |
|---|------|-------|----------|--------|
| D1 | Basic message → reply | Send "hello" in #peterbot | Peter H replies with greeting | |
| D2 | Multi-channel routing | Send messages in #peterbot, #food-log, #ai-briefings | Peter H replies in correct channel each time | |
| D3 | Channel name in context | Send "what channel am I in?" in #food-log | Reply references food-log, not peterbot | |
| D4 | Image attachments | Send a photo in #peterbot with text | Peter H acknowledges the attachment | |
| D5 | Multi-turn context | Ask a question, then "what did I just ask?" | Correctly recalls previous message | |
| D6 | Long response chunking | Ask for a detailed guide (500+ words) | Response split into ≤2000 char messages | |
| D7 | Second Brain capture | Send a message, check /brain/search for it | Conversation captured with facts/concepts | |
| D8 | Tool use (curl) | Ask "what time is it?" | Peter calls GET /time and returns UK time | |
| D9 | MCP tool use | Ask "what's my net worth?" | Peter uses financial-data MCP or /finance/net-worth API | |
| D10 | No response to bots | Have another bot post in #peterbot | Peter H ignores it (no reply) | |
| D11 | Non-admin user rejected | Have someone else send in #peterbot (if possible) | Message silently dropped | |

### 1.2 WhatsApp Channel (CRITICAL)

| # | Test | Steps | Expected | Status |
|---|------|-------|----------|--------|
| W1 | Basic text → reply | Send WhatsApp DM to Peter | Text reply arrives on WhatsApp | |
| W2 | Voice note → text + audio reply | Send voice note on WhatsApp | Transcribed text processed, text reply + voice note sent back | |
| W3 | Multi-turn context | Send two messages, then "what was my first message?" | Recalls correctly from session context | |
| W4 | Water logging | Send "500ml water" on WhatsApp | Water logged via /nutrition/log-water, confirmed with totals | |
| W5 | Second Brain capture | Send a message, check capture log | /response/capture returns 200 | |
| W6 | Nag acknowledgment | Create a nag, then reply "done" on WhatsApp | Nag acknowledged via API, confirmation sent | |
| W7 | Group message | Send in WhatsApp group | Peter responds in group context | |
| W8 | Admin gate | Check is_admin=true in channel meta for Chris | Verified via app log | |

### 1.3 Jobs Channel (CRITICAL)

| # | Test | Steps | Expected | Status |
|---|------|-------|----------|--------|
| J1 | Manual skill trigger | `POST /schedule/run/system-health` | Job executes via channel, output posted to Discord | |
| J2 | NO_REPLY suppression | Trigger system-health when all green | Returns "NO_REPLY", no Discord post | |
| J3 | Synchronous response | Check jobs-channel app log for timing | Response returned to scheduler, duration logged | |
| J4 | Job queuing | Trigger two jobs simultaneously | Second job waits for first, both complete | |
| J5 | Pre-fetched data | Trigger nutrition-summary (has data fetcher) | Pre-fetched nutrition data included in skill context | |
| J6 | Job history recording | Check job_history.db after trigger | Execution recorded with duration, success, output | |
| J7 | Timeout handling | Trigger a long-running skill | Job times out gracefully, error recorded | |
| J8 | Cron-triggered job | Wait for next scheduled job (check SCHEDULE.md) | Job fires on schedule, executes via channel | |

---

## 2. Fallback & Resilience (HIGH)

### 2.1 Discord Fallback

| # | Test | Steps | Expected | Status |
|---|------|-------|----------|--------|
| F1 | Peter H offline detection | Kill peter-channel tmux session | bot.py detects Peter H offline, falls back to router_v2 | |
| F2 | Router_v2 responds | With peter-channel down, send message in #peterbot | Original Peter bot responds (not Peter H) | |
| F3 | Channel restart recovery | Restart peter-channel tmux session | Peter H comes back online, handles messages again | |
| F4 | Manual fallback switch | Set PETERBOT_USE_CHANNEL=0, restart DiscordBot | All Discord messages go through router_v2 | |

### 2.2 WhatsApp Fallback

| # | Test | Steps | Expected | Status |
|---|------|-------|----------|--------|
| F5 | Channel unreachable | Kill whatsapp-channel tmux session | Webhook forwarder retries on port 8101 (bot.py handler) | |
| F6 | Fallback response | With whatsapp-channel down, send WhatsApp message | Reply arrives (via bot.py fallback) | |
| F7 | Manual fallback switch | Set WHATSAPP_USE_CHANNEL=0, restart HadleyAPI | WhatsApp routes through bot.py handler | |

### 2.3 Jobs Fallback

| # | Test | Steps | Expected | Status |
|---|------|-------|----------|--------|
| F8 | Channel unreachable | Kill jobs-channel tmux session | Scheduler falls back to claude -p automatically | |
| F9 | CLI fallback executes | With jobs-channel down, trigger a job | Job runs via router_v2, output posted to Discord | |
| F10 | Manual fallback switch | Set JOBS_USE_CHANNEL=0, restart DiscordBot | All jobs go through claude -p | |

### 2.4 Session Lifecycle

| # | Test | Steps | Expected | Status |
|---|------|-------|----------|--------|
| R1 | Restart loop | Kill a channel's Claude Code process | launch.sh restart loop restarts within 10s | |
| R2 | Auto-start on boot | Restart DiscordBot service (simulates reboot) | All three tmux sessions created by _launch_channel_sessions | |
| R3 | Restart via API | `POST /channels/restart/peter-channel` | Session killed and relaunched | |
| R4 | Restart all via API | `POST /channels/restart-all` | All three sessions restarted | |
| R5 | Channel status API | `GET /channels/status` | Returns up/down + restart count for all three | |

---

## 3. API Endpoints (HIGH)

### 3.1 New Endpoints

| # | Test | Steps | Expected | Status |
|---|------|-------|----------|--------|
| A1 | GET /time | `curl http://localhost:8100/time` | Returns UK date, time, day, timezone | |
| A2 | POST /response/capture | POST with text + user_message | Returns {status: "capturing"} | |
| A3 | GET /channels/status | `curl http://localhost:8100/channels/status` | Returns status for all three channels | |
| A4 | POST /channels/restart/{name} | Restart peter-channel | Returns {status: "restarting"} | |
| A5 | POST /services/restart/{name} | Restart HadleyAPI | Service restarts, returns success | |
| A6 | POST /services/restart/invalid | Try restarting unknown service | Returns 403 with allowed list | |
| A7 | GET /finance/net-worth | `curl http://localhost:8100/finance/net-worth` | Returns formatted net worth data | |
| A8 | GET /finance/budget | `curl http://localhost:8100/finance/budget` | Returns budget status | |
| A9 | GET /finance/health | `curl http://localhost:8100/finance/health` | Returns comprehensive financial overview | |

### 3.2 Existing Endpoints (Regression)

| # | Test | Steps | Expected | Status |
|---|------|-------|----------|--------|
| A10 | GET /health | `curl http://localhost:8100/health` | Returns {status: "ok"} | |
| A11 | GET /nutrition/today | `curl http://localhost:8100/nutrition/today` | Returns today's nutrition data | |
| A12 | POST /whatsapp/send | Send test message via API | Message delivered to WhatsApp | |
| A13 | GET /gmail/search | Search for recent email | Returns email results | |
| A14 | GET /brain/search | Search Second Brain | Returns knowledge items | |

---

## 4. Governance & Self-Modification (MEDIUM)

| # | Test | Steps | Expected | Status |
|---|------|-------|----------|--------|
| G1 | is_admin=true for Chris (Discord) | Check channel notification meta in app log | is_admin=true when Chris sends | |
| G2 | is_admin=false for others | Check meta for non-Chris sender | is_admin=false | |
| G3 | Peter appends to Notes | Tell Peter "add a note about X" on Discord | Appended to Peter's Notes in CLAUDE.md | |
| G4 | Peter edits code (admin) | Tell Peter "add a /test endpoint" on Discord | Code created, git committed, WhatsApp notification | |
| G5 | Peter refuses edit (non-admin) | Have non-admin user request code change | Peter declines | |
| G6 | Service restart by Peter | Tell Peter "restart HadleyAPI" | Peter calls /services/restart/HadleyAPI | |

---

## 5. Dashboard (MEDIUM)

| # | Test | Steps | Expected | Status |
|---|------|-------|----------|--------|
| DH1 | Channel status cards | Open dashboard, check services section | Shows peter-channel, whatsapp-channel, jobs-channel with up/down | |
| DH2 | File viewer | Click "Discord Channel" in files | Shows peter-channel/src/index.ts content | |
| DH3 | Health history | Check health history for channel services | Channel health checks recorded over time | |
| DH4 | Job executions | Check jobs page | Shows recent job executions with duration, status | |

---

## 6. Holiday Readiness (CRITICAL)

| # | Test | Steps | Expected | Status |
|---|------|-------|----------|--------|
| H1 | 24-hour soak test | Leave all channels running for 24 hours | No crashes, all jobs execute, messages handled | |
| H2 | Multiple concurrent messages | Send Discord + WhatsApp messages simultaneously | Both handled independently, no interference | |
| H3 | Machine sleep/wake | Let machine sleep, then wake | Channels recover (restart loop), WSL clock checked via /time | |
| H4 | Full service restart | Restart DiscordBot (simulates machine reboot) | All three channels auto-start, messages flow within 60s | |
| H5 | Morning briefing cycle | Wait for 07:01 morning briefing | Executes via jobs-channel, posts to Discord | |
| H6 | Quiet hours respected | Check no jobs fire between 23:00-06:00 | Jobs suppressed during quiet hours | |

---

## Test Execution Priority

### Before Holiday (Must Pass)
1. All CRITICAL tests (D1-D11, W1-W8, J1-J8)
2. Fallback tests F1, F5, F8 (verify auto-recovery works)
3. Holiday readiness H1, H4, H5

### Nice to Have
4. All HIGH tests (API endpoints, remaining fallback)
5. Governance tests
6. Dashboard tests

---

## Test Environment

| Component | Details |
|---|---|
| Machine | Windows 11, WSL2 Ubuntu |
| Claude Code | v2.1.85 (WSL) |
| Model | claude-opus-4-6 |
| Discord Bot | Peter H (Application ID 1487089363757043893) |
| Channel Sessions | tmux: peter-channel, whatsapp-channel, jobs-channel |
| Hadley API | port 8100 (NSSM) |
| WhatsApp Channel | port 8102 |
| Jobs Channel | port 8103 |
| Dashboard | port 5000 (NSSM) |
