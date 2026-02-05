# Weather Forecast

## Purpose
Get multi-day weather forecast for planning ahead.

## Triggers
- "forecast", "weather this week", "weather tomorrow"
- "what's the weather like on {day}"
- "will it rain on Saturday"
- "weekend weather"
- "weather for my run on {day}"

## Schedule
- 18:00 Sun UK (weekly forecast preview)

## Data Source
Open-Meteo API (free, no key required)
- Endpoint: `https://api.open-meteo.com/v1/forecast`
- Parameters: `daily` for 7-day forecast

## Pre-fetcher
`get_weather_forecast_data()` - fetches:
- 7-day forecast
- Daily: high/low temp, condition, precip probability, sunrise/sunset
- Hourly data for next 24h (for specific time questions)

## Output Format

**Weekly Overview:**
```
🌤️ **Tonbridge - 7 Day Forecast**

Mon: ☀️ 12°/6° - Clear
Tue: ⛅ 14°/8° - Partly cloudy
Wed: 🌧️ 11°/7° - Rain likely (75%)
Thu: 🌧️ 10°/5° - Showers
Fri: ⛅ 13°/7° - Clearing up
Sat: ☀️ 15°/8° - Sunny ✓
Sun: ☀️ 16°/9° - Sunny ✓

Best days for outdoor activities: Sat, Sun
```

**Specific Day:**
```
🌤️ **Saturday 8th February**

Morning: ☀️ 8°C - Clear, light wind
Afternoon: ☀️ 15°C - Sunny
Evening: ⛅ 12°C - Partly cloudy

🌅 Sunrise: 07:23 | Sunset: 17:12
💧 Rain chance: 5%

Great day for a run! 🏃
```

## Guidelines
- Highlight best days for outdoor activities
- For running queries, note conditions (wind, rain, temp)
- Weekend weather gets special attention
- Include sunrise/sunset for early morning or evening plans

## Conversational
Yes - follow-ups:
- "What about the afternoon?"
- "Is Sunday better than Saturday?"
- "When's the next dry day?"
- "Best day for a long run?"

## Running-Specific Advice
When user asks about running weather:
- Ideal: 8-15°C, low wind, no rain
- Too hot: >20°C - "Go early morning"
- Too cold: <3°C - "Layer up, watch for ice"
- Windy: >20mph - "Tough conditions, consider treadmill"
- Rain: "Embrace it or reschedule?"
