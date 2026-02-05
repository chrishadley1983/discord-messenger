# Weather

## Purpose
Get current weather conditions for Tonbridge or specified location.

## Triggers
- "weather", "what's the weather", "is it raining"
- "how cold is it", "temperature"
- "do I need a jacket/umbrella"
- "weather in {location}"

## Schedule
- 08:00 UK daily (part of morning-briefing)

## Data Source
Open-Meteo API (free, no key required)
- Endpoint: `https://api.open-meteo.com/v1/forecast`
- Default location: Tonbridge (51.1952°N, 0.2739°E)

## Pre-fetcher
`get_weather_data()` - fetches:
- Current temperature, feels like
- Weather condition (sunny, cloudy, rain, etc.)
- Precipitation probability
- Wind speed
- Humidity

## Output Format

```
🌤️ **Tonbridge** - {condition}
🌡️ {temp}°C (feels like {feels_like}°C)
💨 Wind: {wind_speed} mph {direction}
💧 Humidity: {humidity}%
🌧️ Rain chance: {precip_prob}%
```

**Contextual additions:**
- If rain likely: "☔ Grab an umbrella - {precip_prob}% chance of rain"
- If cold (<5°C): "🧥 It's chilly - wrap up warm"
- If hot (>25°C): "☀️ Hot one today - stay hydrated"

## Guidelines
- Default to Tonbridge if no location specified
- Use UK units (Celsius, mph)
- Keep it concise for scheduled runs
- Add practical advice (umbrella, jacket, sunscreen)

## Conversational
Yes - follow-ups:
- "What about tomorrow?"
- "Will it rain this afternoon?"
- "Weather in London?"
- "Is it good for a run?"

## Weather Codes (Open-Meteo)
Map codes to friendly descriptions:
- 0: Clear sky ☀️
- 1-3: Partly cloudy ⛅
- 45-48: Foggy 🌫️
- 51-55: Drizzle 🌦️
- 61-65: Rain 🌧️
- 71-77: Snow ❄️
- 80-82: Showers 🌧️
- 95-99: Thunderstorm ⛈️
