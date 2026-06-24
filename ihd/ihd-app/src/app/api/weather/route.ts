import { NextResponse } from "next/server";

// Tonbridge, Kent
const LAT = 51.1959;
const LON = 0.2729;

// WMO Weather codes → emoji + description
const WEATHER_CODES: Record<number, { icon: string; desc: string }> = {
  0: { icon: "☀️", desc: "Clear sky" },
  1: { icon: "🌤️", desc: "Mainly clear" },
  2: { icon: "⛅", desc: "Partly cloudy" },
  3: { icon: "☁️", desc: "Overcast" },
  45: { icon: "🌫️", desc: "Foggy" },
  48: { icon: "🌫️", desc: "Rime fog" },
  51: { icon: "🌦️", desc: "Light drizzle" },
  53: { icon: "🌦️", desc: "Drizzle" },
  55: { icon: "🌦️", desc: "Heavy drizzle" },
  61: { icon: "🌧️", desc: "Light rain" },
  63: { icon: "🌧️", desc: "Rain" },
  65: { icon: "🌧️", desc: "Heavy rain" },
  66: { icon: "🌧️", desc: "Freezing rain" },
  67: { icon: "🌧️", desc: "Heavy freezing rain" },
  71: { icon: "🌨️", desc: "Light snow" },
  73: { icon: "🌨️", desc: "Snow" },
  75: { icon: "🌨️", desc: "Heavy snow" },
  77: { icon: "🌨️", desc: "Snow grains" },
  80: { icon: "🌦️", desc: "Light showers" },
  81: { icon: "🌧️", desc: "Showers" },
  82: { icon: "🌧️", desc: "Heavy showers" },
  85: { icon: "🌨️", desc: "Snow showers" },
  86: { icon: "🌨️", desc: "Heavy snow showers" },
  95: { icon: "⛈️", desc: "Thunderstorm" },
  96: { icon: "⛈️", desc: "Thunderstorm + hail" },
  99: { icon: "⛈️", desc: "Thunderstorm + heavy hail" },
};

function weatherFromCode(code: number) {
  return WEATHER_CODES[code] || { icon: "🌡️", desc: "Unknown" };
}

export async function GET() {
  try {
    const url =
      `https://api.open-meteo.com/v1/forecast?latitude=${LAT}&longitude=${LON}` +
      `&current=temperature_2m,apparent_temperature,weather_code,precipitation_probability` +
      `&hourly=temperature_2m,weather_code,precipitation_probability` +
      `&daily=temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max` +
      `&forecast_days=5&timezone=Europe%2FLondon`;

    const res = await fetch(url, { next: { revalidate: 600 } });
    const data = await res.json();

    const current = data.current;
    const code = current.weather_code ?? 0;
    const weather = weatherFromCode(code);

    // Build hourly lookup grouped by date (YYYY-MM-DD)
    const hourlyByDate: Record<string, { hour: string; temp: number; icon: string; rainChance: number }[]> = {};
    if (data.hourly) {
      for (let i = 0; i < data.hourly.time.length; i++) {
        const hCode = data.hourly.weather_code[i] ?? 0;
        const hw = weatherFromCode(hCode);
        const dateKey = data.hourly.time[i].slice(0, 10); // YYYY-MM-DD
        if (!hourlyByDate[dateKey]) hourlyByDate[dateKey] = [];
        hourlyByDate[dateKey].push({
          hour: new Date(data.hourly.time[i]).getHours().toString().padStart(2, "0") + ":00",
          temp: Math.round(data.hourly.temperature_2m[i]),
          icon: hw.icon,
          rainChance: data.hourly.precipitation_probability[i] ?? 0,
        });
      }
    }

    // Today's hourly (from current hour, next 12 hours)
    const nowHour = new Date().getHours();
    const todayKey = new Date().toISOString().slice(0, 10);
    const hourly = (hourlyByDate[todayKey] || []).slice(nowHour, nowHour + 12);

    // Daily forecast (next 5 days) with their hourly data attached
    const daily = [];
    if (data.daily) {
      for (let i = 0; i < data.daily.time.length; i++) {
        const dCode = data.daily.weather_code[i] ?? 0;
        const dw = weatherFromCode(dCode);
        const date = new Date(data.daily.time[i]);
        const dateKey = data.daily.time[i];
        daily.push({
          date: dateKey,
          dayName: date.toLocaleDateString("en-GB", { weekday: "short" }),
          high: Math.round(data.daily.temperature_2m_max[i]),
          low: Math.round(data.daily.temperature_2m_min[i]),
          icon: dw.icon,
          desc: dw.desc,
          rainChance: data.daily.precipitation_probability_max[i] ?? 0,
          hourly: hourlyByDate[dateKey] || [],
        });
      }
    }

    return NextResponse.json({
      temp: Math.round(current.temperature_2m),
      feelsLike: Math.round(current.apparent_temperature),
      rainChance: current.precipitation_probability ?? 0,
      icon: weather.icon,
      description: weather.desc,
      location: "Tonbridge",
      hourly,
      daily,
    });
  } catch {
    return NextResponse.json(
      { error: "Failed to fetch weather" },
      { status: 500 }
    );
  }
}
