"""BME280 sensor API for Raspberry Pi.

Reads temperature, humidity, and pressure from BME280 via I2C.
Run with: uvicorn main:app --host 0.0.0.0 --port 5000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Dashboard Sensor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

BME280_ADDRESS = 0x76
I2C_PORT = 1


def read_bme280():
    """Read BME280 sensor data via smbus2 + RPi.bme280."""
    import smbus2
    import bme280

    bus = smbus2.SMBus(I2C_PORT)
    calibration_params = bme280.load_calibration_params(bus, BME280_ADDRESS)
    data = bme280.sample(bus, BME280_ADDRESS, calibration_params)
    bus.close()

    return {
        "temp": round(data.temperature, 1),
        "humidity": round(data.humidity, 1),
        "pressure": round(data.pressure, 1),
    }


@app.get("/sensor")
def get_sensor():
    try:
        data = read_bme280()
        return {**data, "status": "ok"}
    except Exception as e:
        return {"status": "error", "error": str(e), "temp": None, "humidity": None, "pressure": None}


@app.get("/health")
def health():
    return {"status": "ok"}
