# Weather Forecast

## Purpose
Get multi-day weather forecast for planning ahead.

## Triggers
- "forecast", "weather this week", "weather tomorrow"
- "what's the weather like on {day}"
- "will it rain on Saturday"
- "weekend weather"

## Schedule
- 18:00 Sun UK (weekly forecast preview)

## Data Source
Hadley API: `curl http://172.19.64.1:8100/weather/forecast`
Optional: `curl "http://172.19.64.1:8100/weather/forecast?days=3"` for shorter forecast

## Output Format

**Weekly Overview:**
```
🌤️ **Tonbridge - 7 Day Forecast**

Mon: ☀️ 12°/6° - Clear
Tue: ⛅ 14°/8° - Partly cloudy
Wed: 🌧️ 11°/7° - Rain likely (75%)
Thu: 🌧️ 10°/5° - Showers
Fri: ⛅ 13°/7° - Clearing up
Sat: ☀️ 15°/8° - Sunny
Sun: ☀️ 16°/9° - Sunny

Best days for outdoor activities: Sat, Sun
```

## Guidelines
- **Never show raw JSON** - only present the formatted human-readable output
- Highlight best days for outdoor activities
- For running queries, note conditions (wind, rain, temp)
- Weekend weather gets special attention

## Conversational
Yes - follow-ups:
- "What about the afternoon?"
- "Is Sunday better than Saturday?"
- "When's the next dry day?"
