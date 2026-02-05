# Weather

## Purpose
Get current weather conditions for Tonbridge.

## Triggers
- "weather", "what's the weather", "is it raining"
- "how cold is it", "temperature"
- "do I need a jacket/umbrella"

## Schedule
- 08:00 UK daily (part of morning-briefing)

## Data Source
Hadley API: `curl http://172.19.64.1:8100/weather/current`

## Output Format

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

## Guidelines
- **Never show raw JSON** - only present the formatted human-readable output
- Default to Tonbridge (configured location)
- Use UK units (Celsius)
- Keep it concise
- Add practical advice (umbrella, jacket)

## Conversational
Yes - follow-ups:
- "What about tomorrow?" → use /weather/forecast
- "Will it rain this afternoon?"
- "Is it good for a run?"
