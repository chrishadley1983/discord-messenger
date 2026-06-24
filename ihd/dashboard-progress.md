# Family Kitchen Dashboard — Setup Summary
*Last updated: 10 March 2026*

---

## Hardware

### Core
| Item | Status |
|------|--------|
| Raspberry Pi 5 (4GB) | ✅ Running |
| Waveshare 13.3" 1920×1080 touchscreen | ✅ Working |
| Official Pi 5 Case (red/white, built-in fan) | Pending — fit after sensors done |
| 27W USB-C PSU | ✅ In use |

### Sensors (on breadboard)
| Sensor | Purpose | Status |
|--------|---------|--------|
| AZDelivery BME280 | Temp / Humidity / Pressure | ⚠️ Needs rewire — worked earlier |
| Adafruit BH1750 | Light level (lux) for auto-brightness | 🔧 Partially wired |
| HC-SR501 PIR | Motion detection / screen wake | ⏳ Not yet wired |

### Zigbee
| Item | Status |
|------|--------|
| Sonoff ZBDongle-E (USB, via 2m extension) | ✅ Running on /dev/ttyUSB0 |
| Sonoff S60ZBTPG Smart Plug | ✅ Paired — link quality 232 |

---

## Software

### Pi OS
- Raspberry Pi OS 64-bit
- Hostname: `dashboard`
- Username: `chrishadley1983`
- SSH enabled
- IP: `192.168.0.110`

### Installed
| Software | Status | Notes |
|----------|--------|-------|
| I2C | ✅ Enabled | `/dev/i2c-1` confirmed |
| smbus2 + RPi.bme280 | ✅ Installed | Python libraries for BME280 |
| Node.js v22 | ✅ Installed | Required for Zigbee2MQTT |
| pnpm | ✅ Installed | Required for Zigbee2MQTT build |
| Mosquitto MQTT broker | ✅ Running + auto-start |
| Zigbee2MQTT v2.9.1 | ✅ Running + auto-start on boot | Frontend: `http://192.168.0.110:8080` |

---

## Wiring Reference

### GPIO Pins in Use
```
Pin 1  · 3.3V     → BME280 VIN (via red power rail)
Pin 3  · GPIO2    → BME280 SDA + BH1750 SDA
Pin 5  · GPIO3    → BME280 SCL + BH1750 SCL
Pin 6  · GND      → Blue power rail
Pin 9  · GND      → spare GND
Pin 17 · 3.3V     → spare 3.3V

Reserved for PIR:
Pin 2  · 5V       → PIR VCC
Pin 11 · GPIO17   → PIR signal
Pin 14 · GND      → PIR GND
```

### Breadboard Layout
- BME280 pins in column D, rows 1–4
- Jumper wires in column C, rows 1–4
- Red (+) and blue (–) power rails in use
- BH1750 to be placed rows 8–13

---

## Zigbee Devices
| Device | Zigbee ID | Type | Signal |
|--------|-----------|------|--------|
| Sonoff S60ZBTPG Smart Plug | 0xa4c13805b774ffff | Router | 232 |

### Planned Zigbee Devices
- Candeo Zigbee PIR sensor (hallway / security alerts)
- Candeo Zigbee door contact sensor (front door arrivals/departures)

---

## Next Steps

### Immediate (hardware)
- [ ] Fix BME280 wiring (fresh eyes — loose connection suspected)
- [ ] Wire and test BH1750 light sensor
- [ ] Wire and test PIR motion sensor
- [ ] Fit Pi into Official Case once all sensors working

### Dashboard (Next.js)
- [ ] Create Next.js project (develop on Windows, deploy to Pi)
- [ ] Google Calendar integration (service account, 10-min polling)
- [ ] BME280 sensor API endpoint
- [ ] BH1750 auto-brightness control
- [ ] PIR motion — screen wake/sleep
- [ ] Zigbee2MQTT integration (smart plug control on dashboard)
- [ ] Security alert notifications (Pushover or email)

### Future Zigbee Devices
- [ ] Candeo PIR sensors (rooms + security)
- [ ] Candeo door contact sensor (front door)
- [ ] Smart bulbs or switches
- [ ] Smart curtain motor (eyelet rail compatible)

---

## Architecture

```
Raspberry Pi 5
├── Zigbee2MQTT (port 8080) ←→ Sonoff ZBDongle-E ←→ Zigbee devices
├── Mosquitto MQTT broker (localhost)
├── Next.js Dashboard (port 3000) — to be built
│   ├── Google Calendar API
│   ├── BME280 sensor data
│   ├── BH1750 light level → screen brightness
│   ├── PIR motion → screen wake/sleep
│   └── Zigbee2MQTT MQTT → device control
└── GPIO
    ├── I2C bus → BME280 + BH1750
    └── GPIO17 → PIR
```

---

## Useful Commands

```bash
# SSH in
ssh -o ServerAliveInterval=60 chrishadley1983@192.168.0.110

# Check sensors
sudo i2cdetect -y 1
python3 test_bme280.py

# Zigbee2MQTT
sudo systemctl status zigbee2mqtt
sudo systemctl restart zigbee2mqtt

# Zigbee2MQTT frontend
http://192.168.0.110:8080
```
