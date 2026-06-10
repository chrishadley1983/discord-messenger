# Weather

## Purpose
Current conditions and multi-day forecast for Tonbridge (merged from the old weather + weather-forecast skills).

## Triggers
- "weather", "what's the weather", "is it raining"
- "how cold is it", "temperature"
- "do I need a jacket/umbrella"
- "forecast", "weather this week", "weather tomorrow"
- "what's the weather like on {day}"
- "will it rain on Saturday", "weekend weather"

## Schedule
None directly (morning-briefing includes current weather).

## Data Source
- Current: `curl http://172.19.64.1:8100/weather/current`
- Forecast: `curl http://172.19.64.1:8100/weather/forecast` (optional `?days=3`)

Use current for "now" questions, forecast for anything about later today / tomorrow / this week.

## Output Format

**Current:**
```
{icon} **Tonbridge** - {condition}
🌡️ {temp}°C (feels like {feels_like}°C)
💨 Wind: {wind_speed} km/h
💧 Humidity: {humidity}%
```

**Contextual additions:**
- If rain/precipitation: "☔ Grab an umbrella"
- If cold (<5°C): "🧥 It's chilly - wrap up warm"
- If hot (>25°C): "☀️ Hot one today - stay hydrated"

**Forecast:**
```
🌤️ **Tonbridge - 7 Day Forecast**

Mon: ☀️ 12°/6° - Clear
Tue: ⛅ 14°/8° - Partly cloudy
Wed: 🌧️ 11°/7° - Rain likely (75%)
...

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
