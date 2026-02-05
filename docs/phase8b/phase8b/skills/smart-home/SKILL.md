# Smart Home (Alexa)

## Purpose
Control smart home devices via Alexa integration - lights, heating, routines.

## Triggers
- "turn on/off {device}", "lights on/off"
- "set heating to {temp}"
- "run {routine} routine"
- "is the {device} on?"
- "smart home status"

## Schedule
None (conversational only)

## Data Source
Alexa Smart Home API / Home Assistant
- Options: 
  1. Alexa API (requires Alexa skill + account linking)
  2. Home Assistant API (if HA installed)
  3. Direct device APIs (Hue, Nest, etc.)

## Devices (Configure per household)
```python
SMART_DEVICES = {
    "living_room_lights": {"type": "light", "alexa_name": "Living Room"},
    "bedroom_lights": {"type": "light", "alexa_name": "Bedroom"},
    "heating": {"type": "thermostat", "alexa_name": "Heating"},
    "tv": {"type": "media", "alexa_name": "Living Room TV"},
    # Add actual devices here
}
```

## Output Format

**Device Control:**
```
💡 Living room lights turned ON

Current smart home status:
• Living room: 💡 On (75%)
• Bedroom: 💡 Off
• Heating: 🌡️ 19°C (target: 20°C)
```

**Status Check:**
```
🏠 **Smart Home Status**

**Lights:**
• Living room: 💡 On (75%)
• Bedroom: 💡 Off
• Kitchen: 💡 Off

**Climate:**
• Heating: 🌡️ 19°C → 20°C target
• Mode: Auto schedule

**Media:**
• Living Room TV: Off
```

**Routine Execution:**
```
🏠 Running "Goodnight" routine...

✓ Living room lights off
✓ Bedroom lights dimmed to 20%
✓ Heating set to 17°C
✓ Front door locked

Goodnight! 🌙
```

## Commands

**Lights:**
- "Turn on living room lights"
- "Dim bedroom to 50%"
- "All lights off"

**Heating:**
- "Set heating to 20 degrees"
- "Turn heating off"
- "What's the temperature?"

**Routines:**
- "Run goodnight routine"
- "Run movie time"
- "Activate away mode"

**Queries:**
- "Is the heating on?"
- "What lights are on?"
- "Smart home status"

## Guidelines
- Confirm actions with current state
- Group related changes (e.g., "goodnight" = multiple actions)
- Warn about unusual requests ("heating to 30°C? That's quite high")
- Don't control devices without explicit request (safety)

## Conversational
Yes - follow-ups:
- "Actually make it warmer"
- "Turn off all the lights"
- "What routines do I have?"

## Safety Considerations
- **Locks:** Require confirmation before unlocking
- **Heating:** Warn if setting very high (>25°C) or very low (<15°C)
- **All off:** Confirm before turning everything off

## Common Routines
Suggest configuring:
- "Good morning" - lights on, heating up, news briefing
- "Goodnight" - lights off, doors locked, heating down
- "Away" - all off, security mode
- "Movie time" - dim lights, TV on
