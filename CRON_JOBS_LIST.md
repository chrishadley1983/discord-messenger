# Clawdbot Cron Jobs - Complete List

**Generated:** 2026-01-29 16:12 UTC  
**Total Jobs:** 12 active + disabled/test jobs

---

## 📅 Recurring Jobs (Active)

### 1. **Claude Platform Balance Check**
- **ID:** `9be692df-d4b8-4edd-b511-8ec3990619aa`
- **Schedule:** `0 * * * *` (Every hour, UTC)
- **Model:** Moonshot Kimi K2
- **Target:** Discord #peter-chat (1415741789758816369)
- **Status:** ✅ ENABLED
- **Last Run:** 2026-01-29 10:00 (error)
- **What it does:** Checks Claude API balance (Supabase) + Moonshot Kimi balance (REST API), posts combined summary

---

### 2. **Hydration & Steps Check-in**
- **ID:** `f425d01e-78c7-402a-8988-32733c2e463f`
- **Schedule:** `0 9,11,13,15,17,19,21 * * *` (Every 2h, 9am-9pm, Europe/London)
- **Model:** Moonshot Kimi K2
- **Target:** Discord #food-log (1465294449038069912)
- **Status:** ✅ ENABLED
- **Last Run:** 2026-01-29 09:00 (error)
- **What it does:** Posts water intake + step count vs targets (3,500ml water, 15,000 steps)

---

### 3. **Arbitrage False Positive Cleanup**
- **ID:** `6f91a8be-a343-4276-b5c1-287d07ef2fe5`
- **Schedule:** `0 6 * * *` (6:00 AM daily, Europe/London)
- **Model:** Claude Haiku
- **Target:** Discord #hb-app-health (1465286105137025119)
- **Status:** ✅ ENABLED
- **Last Run:** 2026-01-28 06:00 (OK)
- **What it does:** Runs FP detector to auto-exclude bad eBay matches from arbitrage watchlist

---

### 4. **AI Morning Briefing** ⚠️
- **ID:** `a41dc5c3-7908-44cd-9c60-9fc8bb410e4e`
- **Schedule:** `30 6 * * *` (6:30 AM daily, UTC)
- **Model:** Moonshot Kimi K2
- **Target:** Discord #ai-briefings (1465277483866788037)
- **Status:** ✅ ENABLED but ⚠️ showing errors
- **Last Run:** 2026-01-29 08:11 (error, 140,646ms)
- **What it does:** Daily AI news briefing (Claude news, community buzz, Moltbot corner, video of day)

---

### 5. **Morning Health Digest** ⚠️
- **ID:** `c5825d5d-8e11-445a-accc-6cb345a20363`
- **Schedule:** `0 7 * * *` (7:00 AM daily, Europe/London)
- **Model:** Moonshot Kimi K2
- **Target:** Discord #peter-chat (1415741789758816369)
- **Status:** ✅ ENABLED but ⚠️ showing errors
- **Last Run:** 2026-01-29 07:00 (error, 163,029ms)
- **What it does:** Health digest (Japan countdown, weather, weight, nutrition, activity, sleep, PT verdict)

---

### 6. **Hadley Bricks Cron Health Check** ⚠️
- **ID:** `485acdd9-c6ec-40d7-8898-ed5c90e3c05d`
- **Schedule:** `30 7 * * *` (7:30 AM daily, Europe/London)
- **Model:** Moonshot Kimi K2
- **Target:** Discord #hb-app-health (1465286105137025119)
- **Status:** ✅ ENABLED but ⚠️ showing errors
- **Last Run:** 2026-01-29 07:30 (error, 175,289ms)
- **What it does:** Monitors arbitrage sync job health (stuck jobs, failures, status summary)

---

### 7. **Hadley Bricks Morning Sync** ⚠️
- **ID:** `1ce8655c-d4e4-453f-9696-9a729239a443`
- **Schedule:** `0 8 * * *` (8:00 AM daily, Europe/London)
- **Model:** Moonshot Kimi K2
- **Target:** Discord #peter-chat (1415741789758816369)
- **Status:** ✅ ENABLED but ⚠️ showing errors
- **Last Run:** 2026-01-29 08:00 (error, 303,540ms)
- **What it does:** Syncs Hadley Bricks app, gets picking lists, eBay auto-offer stats, posts to Discord + WhatsApp

---

### 8. **School Run Traffic Report** ✅
- **ID:** `5e8f1844-041c-441a-9cc3-e6d8d8118c7d`
- **Schedule:** `15 8 * * 1-5` (8:15 AM weekdays only, Europe/London)
- **Model:** Moonshot Kimi K2
- **Target:** WhatsApp (Abby + Chris, delivery disabled for now)
- **Status:** ✅ ENABLED
- **Last Run:** 2026-01-29 08:15 (OK, 92,376ms)
- **What it does:** School run report (real Google Maps traffic, weather, uniform requirements) → WhatsApp

---

### 9. **Hadley Bricks Afternoon Sync** ⚠️
- **ID:** `ac71acff-d0c3-4b65-bd7b-8ae4805e4cb2`
- **Schedule:** `0 14 * * *` (2:00 PM daily, Europe/London)
- **Model:** Moonshot Kimi K2
- **Target:** Discord #peter-chat (1415741789758816369)
- **Status:** ✅ ENABLED but ⚠️ showing errors
- **Last Run:** 2026-01-29 14:00 (error, 289,315ms)
- **What it does:** Afternoon sync of Hadley Bricks (triggers "Sync All", checks orders, generates picking lists)

---

### 10. **Weekly Health Summary**
- **ID:** `99164203-4a35-4644-97e2-dff01a00f8e0`
- **Schedule:** `0 9 * * 0` (9:00 AM every Sunday, Europe/London)
- **Model:** Moonshot Kimi K2
- **Target:** Discord #peter-chat (1415741789758816369)
- **Status:** ✅ ENABLED
- **Last Run:** Not yet (next: 2026-02-02)
- **What it does:** Weekly health review (weight trend, nutrition avg, activity, sleep, heart rate, PT grade)

---

### 11. **Monthly Health Summary**
- **ID:** `3bd07400-f367-446c-8368-5c0103048ab8`
- **Schedule:** `0 9 1 * *` (9:00 AM 1st of month, Europe/London)
- **Model:** Moonshot Kimi K2
- **Target:** Discord #peter-chat (1415741789758816369)
- **Status:** ✅ ENABLED
- **Last Run:** Not yet (next: 2026-02-01)
- **What it does:** Monthly health review (weight journey, nutrition overview, fitness, sleep, heart health)

---

## 🎯 One-Time/Test Jobs

### **Twilio Voice Setup**
- **ID:** `a476db31-9ab7-4acc-bd35-b178a062e7fd`
- **Schedule:** `0 9 2 2 *` (9:00 AM, Feb 2nd, once)
- **Status:** ✅ ENABLED (deleteAfterRun: true)
- **What it does:** Reminder to set up Twilio Voice for phone call integration

---

### **xAI Spending Check**
- **ID:** `6daa8ba9-980c-4c5a-8750-e5631d7ff2d3`
- **Schedule:** `at 2026-02-02 16:00 UTC` (one-time)
- **Status:** ✅ ENABLED (deleteAfterRun: true)
- **What it does:** Reminder to check xAI API spending (set when last30days skill was added)

---

## 📊 Summary by Status

### ✅ Working Well
- Arbitrage False Positive Cleanup
- School Run Traffic Report (new, but successful)
- Weekly/Monthly Health Summaries (not run yet)

### ⚠️ Showing Errors (Need Debugging)
- Claude Platform Balance Check
- Hydration & Steps Check-in
- AI Morning Briefing
- Morning Health Digest
- Hadley Bricks Cron Health Check
- Hadley Bricks Morning Sync
- Hadley Bricks Afternoon Sync

**Common Issue:** Most erroring jobs take 2-5 minutes to run and then fail. Suggests timeout or API issues.

---

## 🔍 Key Observations

### High Failure Rate
- 7 out of 11 active jobs showing errors
- Most are Discord posts
- Common pattern: Jobs complete but error during posting or data fetch

### Slowest Jobs
- Hadley Bricks Morning Sync: 303 seconds (5 min) ⚠️
- Hadley Bricks Afternoon Sync: 289 seconds (4.8 min) ⚠️
- Morning Health Digest: 163 seconds (2.7 min) ⚠️

### Fastest Jobs
- School Run Traffic Report: 92 seconds (most efficient)
- Arbitrage False Positive Cleanup: 52 seconds

---

## 🚨 Issues to Investigate

1. **Discord Channel Target Format** - Changed from `channel:` to `target:` but some jobs may still use old format
2. **API Timeouts** - Long-running jobs timing out (Hadley Bricks syncs)
3. **Isolated Session Issues** - Some jobs spawn isolated sessions that may be failing
4. **last30days Skill** - xAI API might be failing or slow (AI Briefing hangs)
5. **Garmin Session** - Health digest can't get Garmin data (session needs refresh)

---

## 📋 Next Steps

1. [ ] Debug why Discord posts are failing
2. [ ] Check Hadley Bricks API timeouts (increase timeout or optimize payload)
3. [ ] Verify xAI API key works (test last30days skill)
4. [ ] Refresh Garmin session if expired
5. [ ] Monitor job durations to identify bottlenecks

---

**Total Active Cron Jobs:** 11 recurring + 2 one-time = **13 total**  
**Success Rate:** ~27% (3/11 working)  
**Average Runtime:** 3-4 minutes  
**Most Reliable:** School Run Report ✅  
**Most Problematic:** Hadley Bricks syncs (slow + timeout)
