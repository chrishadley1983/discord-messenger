# AI Morning Briefing - Complete Job Extraction

**Job ID:** `a41dc5c3-7908-44cd-9c60-9fc8bb410e4e`  
**Name:** AI Morning Briefing  
**Created:** 2026-01-26  
**Last Updated:** 2026-01-28  
**Status:** ✅ ENABLED (but recently had errors)

---

## 📋 Job Overview

Automated daily AI news briefing that aggregates:
- **News headlines** (Anthropic/Claude, OpenAI, Google, Meta, etc.)
- **Community buzz** (X/Twitter & Reddit discussions, memes, hot takes)
- **Moltbot ecosystem** (updates, integrations, community mentions)
- **Video of the day** (interesting AI video from past 24-48h)

Runs **6:30 AM daily** (UTC) and posts to **Discord #ai-briefings** channel.

---

## ⚙️ Job Configuration

### Schedule
```
Cron Expression: 30 6 * * *
Timezone: UTC
Time: 6:30 AM daily (every day)
```

### Execution Details
```
Agent: main
Session Target: isolated
Wake Mode: now
Model: moonshot/kimi-k2-0905-preview (Moonshot Kimi K2)
Delivery: Enabled (deliver: true)
Output Channel: Discord
Target Channel: #ai-briefings (channel ID: 1465277483866788037)
```

---

## 🔧 Full Prompt Code

```
☀️ Time for the daily AI briefing!

**PART 1: NEWS HEADLINES (Web Search)**
- Section 1: Anthropic/Claude news (3-5 stories) - INCLUDE LINKS
- Section 2: Broader AI news - OpenAI, Google, Meta, etc (3-5 stories) - INCLUDE LINKS

**PART 2: COMMUNITY BUZZ (X / Reddit)**
- Use last30days skill to trawl X (Twitter) and Reddit for trending discussions
- Focus on AI community conversations, memes, hot takes, ecosystem chatter
- Include 3-5 most interesting community mentions - INCLUDE LINKS to posts/threads

**PART 3: MOLTBOT CORNER**
- Find Moltbot-specific news, updates, ecosystem developments
- Community mentions, integrations, anything related to our world
- INCLUDE LINKS to all sources

**PART 4: VIDEO OF THE DAY**
- Find one interesting AI video from past 24-48 hours
- INCLUDE LINK to video

Format for Discord (use > blockquotes, wrap links in <https://example.com>).
Every story/mention must have a link.
Post to Discord #ai-briefings (target: 1465277483866788037) using message tool.
```

---

## 🔌 Dependencies

### 1. **Web Search** (Web Search Tool)
- Used for news headlines
- Searches: "Anthropic Claude news", "OpenAI news", "Google AI news", "Meta AI news"
- Returns: Titles, URLs, snippets

### 2. **last30days Skill** (Custom Skill)
- **Purpose:** Research tool for X (Twitter) & Reddit trending discussions
- **Location:** `/root/clawd/skills/last30days/`
- **What it does:** Aggregates trending AI community conversations, hot takes, memes
- **API Used:** xAI Grok API
- **API Key:** `/etc/profile.d/xai.sh` (GROK_API_KEY)
- **Cost:** Paid API (set reminder to check spending)

### 3. **Message Tool** (Discord)
- **Action:** send
- **Channel:** #ai-briefings
- **Channel ID:** 1465277483866788037
- **Format:** Discord markdown (blockquotes > , link wrapping <https://...>)

---

## 📊 Structure

### Part 1: News Headlines
**Claude/Anthropic News:**
- 3-5 recent stories with links
- Format: `> **Title** <https://link.com>`

**Broader AI News:**
- 3-5 stories from: OpenAI, Google, Meta, others
- Same format with links

### Part 2: Community Buzz
**X/Twitter Discussion:**
- 3-5 trending posts/threads from AI community
- Format: `> **Username** · **Topic** <https://twitter.com/...>`

**Reddit:**
- 3-5 trending threads from r/MachineLearning, r/OpenAI, etc.
- Format: `> **Subreddit** · **Title** <https://reddit.com/r/.../>`

### Part 3: Moltbot Corner
- Moltbot-specific updates, community mentions, integrations
- Any ecosystem news related to Moltbot world
- 2-4 items with links

### Part 4: Video of the Day
- One interesting AI video from past 24-48h
- Platforms: YouTube, TikTok, etc.
- Format: `> **Video Title** <https://youtube.com/...>`

---

## 📤 Output Example

```
**☀️ AI Morning Briefing — Jan 29, 2026**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**📰 NEWS HEADLINES**

**Claude/Anthropic:**
> **Anthropic releases Claude 3.2 with improved reasoning** <https://...>
> **New Claude model shows 40% improvement on coding tasks** <https://...>
> **Anthropic announces Constitutional AI safety framework** <https://...>

**Broader AI:**
> **OpenAI's o1 model achieving superhuman performance on benchmarks** <https://...>
> **Google releases Gemini 2.5 with multimodal capabilities** <https://...>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**💬 COMMUNITY BUZZ**

**X/Twitter Hot Takes:**
> **@ylecun** · Claude vs o1 reasoning comparison getting heated in replies <https://twitter.com/...>
> **@eliseAI** · New meme format: "AI that can code" <https://twitter.com/...>

**Reddit Trending:**
> **r/MachineLearning** · Discussion: Is AGI still 10 years away? <https://reddit.com/r/...>
> **r/OpenAI** · o1 model reviews pouring in from users <https://reddit.com/r/...>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**🤖 MOLTBOT CORNER**

> **Moltbot v2.1 released with improved context handling** <https://...>
> **New @ClawdBot plugin ecosystem reaching 50+ community skills** <https://...>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**🎥 VIDEO OF THE DAY**

> **"Building an AI Agent in 10 Minutes" — Andreas Mueller** <https://youtube.com/...>
```

---

## 🔧 Execution Flow

1. **Cron Trigger** (6:30 AM UTC)
   - Gateway checks schedule
   - Spawns isolated Kimi agent session

2. **Part 1: Web Search** (~10-15 sec)
   - Search for Claude news (3-5 results)
   - Search for broader AI news (3-5 results)
   - Extract URLs and snippets

3. **Part 2: Community Buzz** (~30-45 sec)
   - Call last30days skill
   - Aggregates X/Twitter trending AI discussions
   - Aggregates Reddit trending AI threads
   - 3-5 best from each platform

4. **Part 3: Moltbot Corner** (~5-10 sec)
   - Search for Moltbot-specific updates
   - Look for community integrations/mentions
   - Extract links

5. **Part 4: Video Search** (~5-10 sec)
   - Search for recent AI videos
   - Find one interesting one from 24-48h window
   - Extract YouTube/TikTok link

6. **Format & Post** (~5 sec)
   - Build Discord message with blockquotes
   - Wrap all links in `<https://...>`
   - Send via message tool to #ai-briefings

**Total Runtime:** ~60-90 seconds

---

## 🎯 Key Requirements

### CRITICAL: Link Every Item
- Every headline must have a link
- Every community mention must have a link
- Every video must have a link
- **No links = incomplete briefing**

### Format for Discord
- Use `>` for blockquotes (Discord style)
- Wrap links in angle brackets: `<https://example.com>`
- Bold titles: `**Title Here**`
- No generic descriptions — actual news content

### Timeframe for Content
- News: Past 24-48 hours
- Community buzz: Trending in last 24h
- Videos: Last 24-48 hours
- Moltbot: Latest ecosystem updates

---

## 🔐 API Keys & Secrets

### xAI Grok API (for last30days skill)
- **File:** `/etc/profile.d/xai.sh`
- **Env var:** `GROK_API_KEY`
- **Cost:** Paid API
- **Status:** Check spending reminder set for Feb 2, 2026
- **Why:** Powers the Twitter/Reddit community buzz aggregation

### Discord Channel
- **No API key needed** (uses Clawdbot message tool)
- **Channel ID:** 1465277483866788037 (#ai-briefings)
- **Auth:** Handled by Clawdbot bot account

---

## 📊 Recent Status

### Current Issues (as of 2026-01-29)
- ⚠️ Job showing `lastStatus: error` in cron list
- Last run: 2026-01-29 08:11:09 UTC
- Duration: 140,646 ms (~2.3 minutes)
- Error likely due to: API timeout, network issue, or skill failure

### Last Successful Run
- Unknown (need to check cron logs)
- Model: Moonshot Kimi K2
- Output format: Discord blockquotes with links

---

## 🚀 Testing Checklist

- [ ] Run manually at 6:30 AM to verify output
- [ ] Verify all links are included (no generic descriptions)
- [ ] Check Discord formatting (blockquotes, links wrapped)
- [ ] Confirm 3-5 items per section minimum
- [ ] Verify Moltbot corner appears (ecosystem section)
- [ ] Test last30days skill works (xAI API key valid)
- [ ] Validate videos are from past 24-48h
- [ ] Check message posts to correct Discord channel

---

## 🎯 Success Criteria

**Briefing is working if:**
1. Posts daily at 6:30 AM UTC
2. Contains 4 distinct sections (news, buzz, Moltbot, video)
3. Every item has a clickable link
4. Claude news is featured (at least 3 stories)
5. Community buzz includes both Twitter and Reddit
6. Moltbot section exists with ecosystem updates
7. Video is recent (past 48h)
8. Discord formatting is clean (blockquotes, proper link wrapping)
9. Total content: ~30-50 items across all sections

---

## 📋 Improvements & Fixes

### Current Problems
- [ ] Job showing errors — debug cron logs
- [ ] May need retry mechanism if last30days skill fails
- [ ] xAI API spending needs monitoring

### Potential Enhancements
- [ ] Add image previews for video of the day
- [ ] Add reaction counts (which tweets/videos trending most)
- [ ] Add category filtering (only show relevant AI communities)
- [ ] Cache results if APIs timeout (fallback to yesterday's briefing)
- [ ] Add morning/evening variant (customize for different time zones)

---

## 🔍 Debugging

### If briefing doesn't post:
1. Check cron job status: `clawdbot cron list | grep "AI Morning Briefing"`
2. Check for errors: Look at `state.lastError` field
3. Manually test: Spawn an agent and run the prompt
4. Check last30days skill: Verify xAI API key works
5. Check Discord channel: Verify bot has permission to #ai-briefings

### If links are missing:
- Job likely cut short due to timeout
- Increase timeout in cron config
- Simplify search queries (fewer results per section)

### If content is generic:
- Skills not returning real data
- last30days skill may be failing
- Fall back to web search only

---

**Last Updated:** 2026-01-29  
**Status:** ⚠️ Needs debugging (recent errors)  
**Model:** Moonshot Kimi K2  
**Schedule:** 6:30 AM UTC daily
