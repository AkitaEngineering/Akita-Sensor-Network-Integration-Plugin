# ASNIP Documentation

This folder contains documentation for configuring and running the
Akita Sensor Network Integration Plugin (ASNIP).

## Configuration (sensors.json)

The `sensors.json` file contains two top-level keys:

- `settings`: global plugin settings
  - `log_file`: path to JSON file where sensor logs are stored
  - `broadcast_interval`: how often (seconds) to sample and broadcast
- `sensors`: an array of sensor definitions. Each sensor object contains:
  - `name` (string): a short, unique sensor name
  - `type` (string): one of the supported sensor types (see below)
  - `enabled` (bool): whether to read and broadcast this sensor
  - `params` (object): optional sensor-specific parameters

Example:

```json
{
  "settings": { "log_file": "sensor_log.json", "broadcast_interval": 30 },
  "sensors": [
    { "name": "cpu_temp_sim", "type": "simulated_temperature", "enabled": true, "params": { "min_temp": 35, "max_temp": 65 } }
  ]
}
```

## Supported sensor `type` values

- `simulated_temperature`, `simulated_humidity`
- `random_value`
- `static_value`
- `custom_script` — executes an external command; returns stdout (string)
- `bme280_temperature`, `bme280_humidity`, `bme280_pressure` — require
  `adafruit-circuitpython-bme280` and hardware

## BME280 Setup (Hardware & Software)

If you plan to use BME280 sensors for temperature/humidity/pressure readings,
follow these steps.

Hardware
- Connect the BME280 to I2C: `SDA` -> SDA pin, `SCL` -> SCL pin, `VCC` -> 3.3V,
  `GND` -> GND. On Raspberry Pi these are typically pins 3 (SDA) and 5 (SCL).

Software
- Install the driver (only required if using BME280 types):

```bash
pip install adafruit-circuitpython-bme280
```

- Ensure I2C is enabled on your device (for Raspberry Pi use `raspi-config`).
- The plugin initializes the BME280 only if any configured sensor uses a
  `bme280_` type and the library is available; if initialization fails an
  error is logged and the sensor readings will return `None`.

Troubleshooting
- If you see `None` for BME280 values: verify wiring, confirm I2C address
  (some modules support 0x76 or 0x77), and check for permission issues when
  accessing the I2C bus.

## Security & Hardening Guidance

`custom_script` executes an external command and currently runs via the
shell (`subprocess.run(..., shell=True)`) to allow more flexible script
invocations. This increases risk: an attacker who can modify `sensors.json`
may execute arbitrary commands.

Recommendations
- Restrict write permissions on `sensors.json` to trusted users only:

```bash
chown root:root sensors.json
chmod 600 sensors.json
```

- Prefer wrapper scripts with limited functionality rather than letting
  arbitrary commands be placed directly in the config.
- Consider replacing `shell=True` with a safer execution model (list args)
  and validate script paths against an allowlist.
- Run the plugin under a dedicated, minimally-privileged user account.

## Example Configurations

1) Minimal example (simulated sensor):

```json
{
  "settings": {"log_file": "sensor_log.json", "broadcast_interval": 30},
  "sensors": [
    {"name": "cpu_temp_sim", "type": "simulated_temperature", "enabled": true, "params": {"min_temp": 35, "max_temp": 65}}
  ]
}
```

2) BME280 example (hardware):

```json
{
  "settings": {"log_file": "sensor_log.json", "broadcast_interval": 60},
  "sensors": [
    {"name": "ambient_temp", "type": "bme280_temperature", "enabled": true, "params": {"unit": "C"}},
    {"name": "ambient_hum", "type": "bme280_humidity", "enabled": true}
  ]
}
```

3) Custom script example (use with caution):

```json
{
  "settings": {"log_file": "sensor_log.json", "broadcast_interval": 120},
  "sensors": [
    {"name": "battery", "type": "custom_script", "enabled": true, "params": {"script_path": "/usr/local/bin/get_battery_level.sh", "timeout": 3}}
  ]
}
```

## Best Practices

- Keep `broadcast_interval` reasonably high (>5s) to avoid network congestion.
- Log files may grow — consider log rotation or storing logs in a writable
  but limited location.
- Test `custom_script` commands manually before adding them to the
  configuration file.

---

For more help or to propose an enhancement, open an issue on the project.
