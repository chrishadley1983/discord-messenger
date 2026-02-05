# Phase 8b Configuration

## .env additions

```bash
# Open-Meteo (no key required - free API)
WEATHER_LAT=51.1952
WEATHER_LON=0.2739
WEATHER_LOCATION_NAME=Tonbridge

# Ohme EV Charger
OHME_EMAIL=your_ohme_email
OHME_PASSWORD=your_ohme_password

# Ring (unofficial API)
RING_EMAIL=your_ring_email
RING_PASSWORD=your_ring_password
RING_2FA_TOKEN=your_2fa_token  # Or use refresh token

# Alexa / Smart Home
# Option 1: Home Assistant
HOME_ASSISTANT_URL=http://homeassistant.local:8123
HOME_ASSISTANT_TOKEN=your_long_lived_access_token

# Option 2: Direct Alexa (complex, requires skill setup)
# ALEXA_CLIENT_ID=...
# ALEXA_CLIENT_SECRET=...

# Google Maps Routes
GOOGLE_MAPS_API_KEY=your_google_maps_api_key

# Saved locations
HOME_ADDRESS=Your home address, Tonbridge, Kent
SCHOOL_ADDRESS=School address
STATION_ADDRESS=Tonbridge Station, Kent
```

## config.py additions

```python
# === PHASE 8b: Smart Home ===

# Weather (Open-Meteo - no key needed)
WEATHER_LAT = float(os.getenv("WEATHER_LAT", "51.1952"))
WEATHER_LON = float(os.getenv("WEATHER_LON", "0.2739"))
WEATHER_LOCATION_NAME = os.getenv("WEATHER_LOCATION_NAME", "Tonbridge")

# Ohme EV
OHME_EMAIL = os.getenv("OHME_EMAIL")
OHME_PASSWORD = os.getenv("OHME_PASSWORD")

# Ring
RING_EMAIL = os.getenv("RING_EMAIL")
RING_PASSWORD = os.getenv("RING_PASSWORD")
RING_2FA_TOKEN = os.getenv("RING_2FA_TOKEN")

# Home Assistant (for smart home control)
HOME_ASSISTANT_URL = os.getenv("HOME_ASSISTANT_URL")
HOME_ASSISTANT_TOKEN = os.getenv("HOME_ASSISTANT_TOKEN")

# Google Maps
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

# Saved locations
HOME_ADDRESS = os.getenv("HOME_ADDRESS", "Tonbridge, Kent")
SCHOOL_ADDRESS = os.getenv("SCHOOL_ADDRESS")
STATION_ADDRESS = os.getenv("STATION_ADDRESS", "Tonbridge Station, Kent")

# Saved routes for traffic checks
SAVED_ROUTES = {
    "school": {
        "origin": HOME_ADDRESS,
        "destination": SCHOOL_ADDRESS,
        "typical_time": 12
    },
    "station": {
        "origin": HOME_ADDRESS,
        "destination": STATION_ADDRESS,
        "typical_time": 8
    }
}
```

## API Notes

### Open-Meteo (Weather)
- **Free:** No API key required
- **Rate limit:** Generous, non-commercial use
- **Docs:** https://open-meteo.com/en/docs

### Ohme
- **Auth:** Email/password → session token
- **Unofficial:** No public API, reverse-engineered
- **Library:** `ohme-api` npm package or similar Python implementation
- **Docs:** Community maintained

### Ring
- **Auth:** Email/password + 2FA → refresh token
- **Unofficial:** No public API
- **Library:** `ring-client-api` (Node) or `ring_doorbell` (Python)
- **Note:** Ring may block unofficial access; use carefully

### Home Assistant (recommended for smart home)
- **Auth:** Long-lived access token
- **Official API:** Well documented
- **Docs:** https://developers.home-assistant.io/docs/api/rest/
- **Benefit:** Unifies all smart devices (Alexa, Hue, Nest, etc.)

### Google Maps Routes API
- **Auth:** API key
- **Cost:** $5 per 1000 requests (first $200/month free)
- **Enable:** Google Cloud Console → APIs → Routes API
- **Docs:** https://developers.google.com/maps/documentation/routes

## Setup Priority

1. **Open-Meteo** - Works immediately, no setup
2. **Google Maps** - Just needs API key
3. **Ohme** - If you have Ohme charger
4. **Home Assistant** - If already running HA
5. **Ring** - Unofficial, may be flaky
