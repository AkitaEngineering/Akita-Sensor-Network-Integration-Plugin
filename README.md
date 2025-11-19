# Akita Sensor Network Integration Plugin (ASNIP)

ASNIP is a Meshtastic plugin designed to integrate sensor data into the Meshtastic network. It allows users to broadcast sensor readings from a configurable set of sensors and receive/log data from other sensor nodes.

**Organization:** Akita Engineering  
**License:** GPLv3

---

## Features

- Broadcast: Periodically sends sensor data over the mesh using a private port.  
- Logging: Logs local and remote sensor data to a JSON file.  
- Flexible Config: All settings (interval, log file, sensors) are controlled via sensors.json.  
- Extensible: Easily add Python functions to read new sensors.  
- Smart Loading: Automatically detects configuration files in standard locations or via environment variables.

---

## Installation

### 1. Place Plugin File

Copy `src/asnip/asnip.py` into your Meshtastic plugins directory.

Typical locations:

- Linux / Raspberry Pi: `~/.meshtastic/plugins/`
- Or inside the Meshtastic source directory, depending on install method.

### 2. Install Dependencies

pip install meshtastic  
pip install adafruit-circuitpython-bme280  
(only required if using BME280 sensors)

---

## Configuration Setup

ASNIP requires a sensors.json configuration file.  
It is searched in the following order (highest priority first):

1. Environment variable: `ASNIP_CONFIG`
2. Current working directory: `./sensors.json`
3. Plugin directory: next to `asnip.py`

If no file is found, the plugin will generate a default config.

---

## Usage

### Edit Configuration

Create or modify `sensors.json`.

### Enable Plugin

meshtastic --set-plugin asnip.enabled true

Note: Do not use unsupported flags such as `--sensor-config` or `--interval`.

---

## Example sensors.json

{
  "settings": {
    "log_file": "sensor_log.json",
    "broadcast_interval": 30
  },
  "sensors": [
    {
      "name": "cpu_temp_sim",
      "type": "simulated_temperature",
      "enabled": true,
      "params": {
        "min_temp": 35.0,
        "max_temp": 65.0,
        "unit": "C"
      }
    },
    {
      "name": "my_bme280_temp",
      "type": "bme280_temperature",
      "enabled": false,
      "params": { "unit": "C" }
    },
    {
      "name": "external_script",
      "type": "custom_script",
      "enabled": false,
      "params": {
        "script_path": "/usr/local/bin/get_battery_level.sh",
        "timeout": 2
      }
    }
  ]
}

---

## Available Sensor Types

- simulated_temperature / simulated_humidity — random simulated test data  
- random_value — random integer (min_val, max_val)  
- static_value — fixed value  
- custom_script — runs an external script  
- bme280_temperature / humidity / pressure — hardware sensor support  

---

## Security Note on Custom Scripts

The `custom_script` type uses `subprocess.run(shell=True)`.

**Risk:** If sensors.json is modified by an attacker, they can run arbitrary commands.  
**Mitigation:** Ensure sensors.json is only writable by trusted users. Avoid risky scripts.

---

## Troubleshooting

### 1. Error: “Unrecognized argument: --sensor-config”

Use the environment variable instead:

export ASNIP_CONFIG=/path/to/config.json  
meshtastic

---

### 2. Plugin regenerates default config

Likely cannot find your file in the current directory.  
Set the full path in ASNIP_CONFIG.

---

### 3. Permission denied writing log or config

Change `log_file` to a writable location, such as `/tmp/sensor_log.json`.

---

### 4. BME280 returns None

- Ensure the library is installed  
- Verify wiring  
- Ensure I2C is enabled (raspi-config)
