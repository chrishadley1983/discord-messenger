# Phase 8b Implementation Guide

## Overview

Phase 8b adds Smart Home integrations to Peterbot: Weather, EV Charging, Ring, Smart Home (Alexa/HA), and Traffic/Directions.

**Skills Added:** 7 new skills
**APIs:** Open-Meteo (free), Ohme, Ring, Home Assistant, Google Maps
**Scheduled Jobs:** 2-3 new entries (weather in morning-briefing, weekly forecast)

---

## Skills Summary

| Skill | Type | API | Cost |
|-------|------|-----|------|
| `weather` | Scheduled + Conv | Open-Meteo | FREE |
| `weather-forecast` | Scheduled + Conv | Open-Meteo | FREE |
| `ev-charging` | Scheduled + Conv | Ohme | FREE |
| `ring-status` | Conversational | Ring (unofficial) | FREE |
| `smart-home` | Conversational | Home Assistant | FREE |
| `traffic-check` | Scheduled + Conv | Google Maps | ~FREE* |
| `directions` | Conversational | Google Maps | ~FREE* |

*Google Maps: First $200/month free (~40k requests)

---

## Implementation Priority

### Tier 1: Works Immediately (No Setup)
1. **Weather** - Open-Meteo needs no API key
2. **Weather Forecast** - Same

### Tier 2: Just Needs API Key
3. **Traffic Check** - Google Maps API key
4. **Directions** - Same key

### Tier 3: Needs Account Setup  
5. **EV Charging** - Ohme credentials
6. **Smart Home** - Home Assistant token
7. **Ring** - Ring credentials + 2FA

---

## Setup Steps

### Step 1: Weather (Immediate)

Just set your location in `.env`:
```bash
WEATHER_LAT=51.1952
WEATHER_LON=0.2739
WEATHER_LOCATION_NAME=Tonbridge
```

Test: `!skill weather`

### Step 2: Google Maps Traffic

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create project or select existing
3. Enable "Routes API"
4. Create API key
5. Add to `.env`:
```bash
GOOGLE_MAPS_API_KEY=your_key_here
HOME_ADDRESS=Your full home address
SCHOOL_ADDRESS=School full address
```

Test: `!skill traffic-check`

### Step 3: Ohme EV (If Applicable)

Add credentials:
```bash
OHME_EMAIL=your_email
OHME_PASSWORD=your_password
```

Note: Ohme API is unofficial - may need adjustment.

### Step 4: Home Assistant (If Running)

1. Generate long-lived access token in HA
2. Add to `.env`:
```bash
HOME_ASSISTANT_URL=http://homeassistant.local:8123
HOME_ASSISTANT_TOKEN=your_token
```

### Step 5: Ring (Optional)

Ring's unofficial API can be flaky. Setup:
```bash
pip install ring_doorbell
```

Add credentials:
```bash
RING_EMAIL=your_email
RING_PASSWORD=your_password
```

Note: May require handling 2FA interactively first time.

---

## File Checklist

### New Skill Files
```
skills/
├── weather/SKILL.md           ← NEW
├── weather-forecast/SKILL.md  ← NEW
├── ev-charging/SKILL.md       ← NEW
├── ring-status/SKILL.md       ← NEW
├── smart-home/SKILL.md        ← NEW
├── traffic-check/SKILL.md     ← NEW
├── directions/SKILL.md        ← NEW
```

### Config Updates
- `.env` - Add all new credentials
- `config.py` - Import new env vars
- `data_fetchers.py` - Add 7 fetcher functions

### CLAUDE.md
- Add Phase 8b autonomous tool usage guidance

---

## Schedule Additions

```markdown
| Job Name | Skill | Schedule | Channel | Needs Data |
|----------|-------|----------|---------|------------|
| Weather | weather | 08:00 UK | #general | yes |
| Weekly Forecast | weather-forecast | 18:00 Sun UK | #general | yes |
```

**Note:** Weather and traffic should be integrated into `morning-briefing` rather than separate jobs.

---

## Updating Morning Briefing

The `morning-briefing` skill should now include:

```
Morning Briefing (08:00):
1. Weather for today ← Phase 8b
2. Schedule today ← Phase 8a
3. Email summary ← Phase 8a
4. Notion todos ← Phase 8a
5. Health digest (existing)
6. School run traffic ← Phase 8b (school days only)
7. Car charge status ← Phase 8b (if plugged in)
```

Update `skills/morning-briefing/SKILL.md` to call these data sources.

---

## Integration with Existing Skills

### School Run Enhancement
Update `school-run` skill to include:
- Weather conditions
- Traffic status
- EV charge level (if relevant)

### School Pickup Enhancement  
Update `school-pickup` skill to include:
- Traffic for pickup time
- Weather (outdoor activities?)

---

## Testing Checklist

- [ ] `!skill weather` returns current conditions
- [ ] "Will it rain tomorrow?" triggers forecast
- [ ] "Traffic to school" returns route info
- [ ] "How do I get to X?" returns directions
- [ ] EV charging status (if configured)
- [ ] Smart home status (if configured)
- [ ] Ring events (if configured)
- [ ] Morning briefing includes weather
- [ ] School run includes traffic

---

## Questions for You

1. **Do you have an Ohme charger?** If not, skip EV integration
2. **Running Home Assistant?** If not, smart home control will be limited
3. **Ring doorbell?** If not, skip Ring integration
4. **Actual addresses** - I'll need these for saved routes:
   - Home address
   - School address
   - Any other regular destinations
