import smbus2, bme280
bus = smbus2.SMBus(1)
cal = bme280.load_calibration_params(bus, 0x76)
data = bme280.sample(bus, 0x76, cal)
print(f'Temp: {data.temperature:.1f}°C')
print(f'Humidity: {data.humidity:.1f}%')
print(f'Pressure: {data.pressure:.1f}hPa')
