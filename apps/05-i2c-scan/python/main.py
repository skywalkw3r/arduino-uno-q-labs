"""Bring-up step 5 — find out what's actually on the I2C buses.

The UNO Q has two. Wiring a Qwiic sensor and then scanning the header bus is the
classic way to conclude "the sensor is dead" when it's fine. This scans both and
tells you which bus answered.

    Wire   -> I2C1, D20 (SDA) / D21 (SCL), UNO-style header
    Wire1  -> I2C4, Qwiic connector (Modulino nodes live here)

⚠️ The Qwiic connector is 3.3 V only. Don't attach 5 V devices.

Rescans every few seconds and only logs when something changes, so you can hot-
plug a Qwiic cable and watch it appear.
"""

import logging
import time

from arduino.app_utils import App, Bridge, Logger

logger = Logger("I2CScan", level=logging.INFO)

SCAN_INTERVAL_S = 3.0

# Common addresses, to turn a bare number into a starting point for a search.
# I2C addresses are not unique to a part, so these are hints, not identification.
KNOWN_ADDRESSES = {
    0x0C: "Modulino Knob / AK8963 magnetometer",
    0x10: "VEML7700 / VEML6030 light",
    0x18: "Modulino Movement / LIS3DH accelerometer",
    0x19: "LIS3DH / LSM303 accelerometer",
    0x1C: "LIS2MDL / MMA8451 accelerometer",
    0x1E: "HMC5883L / LSM303 magnetometer",
    0x20: "MCP23017 / PCF8574 GPIO expander",
    0x21: "Modulino Buttons / PCF8574",
    0x27: "PCF8574 LCD backpack",
    0x28: "Modulino Pixels / BNO055 IMU",
    0x29: "VL53L0X / VL53L4CD ToF (Modulino Distance)",
    0x36: "MAX17048 fuel gauge",
    0x39: "APDS-9960 gesture / TSL2561 light",
    0x3C: "SSD1306 / SH1106 OLED",
    0x3D: "SSD1306 OLED (alt address)",
    0x40: "INA219 current / Si7021 / HTU21D humidity",
    0x44: "SHT31 / SHT4x temp+humidity",
    0x48: "ADS1115 ADC / LM75 temp",
    0x4A: "Modulino Thermo / ADS1115 (alt)",
    0x53: "ADXL345 accelerometer",
    0x57: "MAX30105 pulse oximeter",
    0x58: "SGP30 air quality",
    0x5A: "CCS811 air quality / MLX90614 IR temp",
    0x60: "MCP4725 DAC / Si5351 clock",
    0x62: "SCD40 / SCD41 CO2",
    0x68: "DS3231 RTC / MPU-6050 IMU",
    0x69: "MPU-6050 (alt) / ICM-20948",
    0x6A: "LSM6DS3 / LSM6DSOX IMU",
    0x6B: "LSM6DS3 (alt)",
    0x70: "TCA9548A I2C multiplexer / HT16K33",
    0x76: "BMP280 / BME280 / BME680 environmental",
    0x77: "BMP180 / BME280 (alt) / BME680 (alt)",
}

last_seen: tuple[tuple[int, ...], tuple[int, ...]] | None = None
scan_count = 0


def describe(addr: int) -> str:
    hint = KNOWN_ADDRESSES.get(addr)
    return f"0x{addr:02X}  {hint}" if hint else f"0x{addr:02X}  (unrecognised)"


def report_bus(label: str, pins: str, devices: list[int]) -> None:
    if devices:
        logger.info("%s (%s): %d device(s)", label, pins, len(devices))
        for addr in devices:
            logger.info("    %s", describe(addr))
    else:
        logger.info("%s (%s): nothing found", label, pins)


def scan_result(header_devices: list[int], qwiic_devices: list[int]) -> None:
    """Called by the sketch once per scan, with both buses' results."""
    global last_seen

    current = (tuple(header_devices), tuple(qwiic_devices))
    if current == last_seen:
        return  # unchanged — stay quiet so hot-plug events stand out
    last_seen = current

    logger.info("═" * 64)
    logger.info("I2C scan #%d", scan_count)
    report_bus("Wire  — header", "D20 SDA / D21 SCL", header_devices)
    report_bus("Wire1 — Qwiic ", "3.3 V only", qwiic_devices)

    if not header_devices and not qwiic_devices:
        logger.warning(
            "Both buses empty. Check power, the cable, and that the device is 3.3 V."
        )
    logger.info("═" * 64)


Bridge.provide("scan_result", scan_result)


def loop() -> None:
    global scan_count

    scan_count += 1
    Bridge.call("request_scan")
    time.sleep(SCAN_INTERVAL_S)


logger.info("Scanning both I2C buses every %.0fs. Hot-plug a Qwiic device to see it appear.", SCAN_INTERVAL_S)
App.run(user_loop=loop)
