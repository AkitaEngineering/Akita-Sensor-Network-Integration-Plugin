# Akita Sensor Network Integration Plugin (ASNIP)

ASNIP is a Meshtastic plugin designed to integrate sensor data into the Meshtastic network. It allows users to broadcast sensor readings from a configurable set of sensors and receive/log data from other sensor nodes.

**Organization:** Akita Engineering  
**Repository:** AkitaEngineering/Akita-Sensor-Network-Integration-Plugin  
**License:** GPLv3

## Features

* **Configurable Sensor Integration:** Define sensors to read via an external JSON configuration file (`sensors.json`).
* **Extensible Sensor Types:** Easily add new Python methods to read from various hardware or data sources.
* **Sensor Data Broadcast:** Periodically broadcasts aggregated sensor data over the Meshtastic network using a dedicated port number.
* **Sensor Data Logging:** Logs all locally generated and remotely received sensor data to a JSON file.
* **Configurable Intervals & Files:** Adjust broadcast frequency, log file, and sensor configuration file via command-line arguments.
* **Robust Error Handling:** Includes error handling for file I/O, network operations, sensor configuration, and sensor data retrieval.
* **Respects TX Delay:** Uses a message queue for outgoing data, allowing Meshtastic to manage LoRa transmission timing.
* **Graceful Shutdown:** Handles keyboard interrupts for clean plugin termination.
* **Example Sensor Readers:** Includes built-in readers for simulated data, static values, custom external scripts, and BME280 environmental sensors (temperature, humidity, pressure).

## Installation

1. **Place Plugin File:** Copy `src/asnip/asnip.py` from this repository to your Meshtastic plugins directory (e.g., `~/.config/meshtastic/plugins/asnip.py` or the equivalent on your system).
2. **Install Meshtastic Python API:**
    ```bash
    pip install meshtastic
    ```
3. **Install Sensor Libraries (if needed):**
    * If you plan to use the BME280 sensor examples or add other hardware sensors, you'll need to install their respective Python libraries. For BME280:
        ```bash
        pip install adafruit-circuitpython-bme280
        ```
    * Ensure system dependencies like `python3-pip` and I2C tools are installed if working with hardware like the BME280 on a Raspberry Pi.
4. **Create Sensor Configuration File:**
    * ASNIP looks for a `sensors.json` file by default in the same directory as `asnip.py` (or where Meshtastic runs from). You can specify a different path using the `--sensor-config` argument.
    * If `sensors.json` is not found, a default one with examples will be created. **You MUST review and edit this file** to enable and configure your desired sensors.
5. **Enable Plugin in Meshtastic:** Run Meshtastic with the plugin enabled. This varies by how you use Meshtastic (CLI, GUI, etc.). For the CLI, it might involve `--set plugin_name.enabled true` or similar.

## Usage

* Once configured and enabled, ASNIP automatically reads from sensors defined in `sensors.json` at the configured interval.
* Aggregated sensor data is broadcast over the mesh.
* Locally generated and received sensor data are logged to the specified log file (default: `sensor_log.json`).
* Use `Ctrl+C` to stop the Meshtastic client and the plugin gracefully.

## Command-Line Arguments

When starting Meshtastic, you can pass these arguments (the exact method depends on your Meshtastic client):

* `--log <filename>`: Specifies the sensor data log file name (default: `sensor_log.json`).
* `--interval <seconds>`: Specifies the sensor broadcast interval in seconds (default: 30, min: 5).
* `--sensor-config <path/to/sensors.json>`: Path to the sensor configuration JSON file (default: `sensors.json`).

## Sensor Configuration (`sensors.json`)

This JSON file defines the sensors ASNIP will attempt to read. It should contain a single key `"sensors"` with a list of sensor objects.

Each sensor object has the following structure:

* `name` (string, required): A unique name for this sensor reading. This will be the key in the output data.
* `type` (string, required): The type of sensor reader to use. This must match a key in ASNIP's internal `sensor_reader_map`.
* `enabled` (boolean, required): Set to `true` to enable reading this sensor, `false` to disable.
* `params` (object, optional): A dictionary of parameters specific to the sensor `type`.

**Example `sensors.json`:**

```json
{
  "sensors": [
    {
      "name": "cpu_temp_sim",
      "type": "simulated_temperature",
      "enabled": true,
      "params": {"min_temp": 35.0, "max_temp": 65.0, "unit": "C"}
    },
    {
      "name": "room_humidity_sim",
      "type": "simulated_humidity",
      "enabled": true,
      "params": {"min_hum": 40.0, "max_hum": 60.0, "unit": "%"}
    },
    {
      "name": "ambient_temp_bme280",
      "type": "bme280_temperature",
      "enabled": true,
      "params": {"unit": "C"}
    },
    {
      "name": "ambient_humidity_bme280",
      "type": "bme280_humidity",
      "enabled": true,
      "params": {}
    },
    {
      "name": "barometric_pressure_bme280",
      "type": "bme280_pressure",
      "enabled": true,
      "params": {}
    },
    {
      "name": "device_label",
      "type": "static_value",
      "enabled": true,
      "params": { "value": "AkitaNode-Alpha" }
    },
    {
      "name": "custom_script_output",
      "type": "custom_script",
      "enabled": false,
      "params": { "script_path": "echo 'hello_world'", "timeout": 5 }
    }
  ]
}
```

**Built-in Sensor Types:**

- `simulated_temperature`: Generates a random temperature.  
  Params: `min_temp`, `max_temp`, `unit` (C/F/K)  
- `simulated_humidity`: Generates a random humidity value.  
  Params: `min_hum`, `max_hum`, `unit`  
- `random_value`: Generates a random integer.  
  Params: `min_val`, `max_val`  
- `static_value`: Outputs a predefined static value.  
  Params: `value` (string, number, boolean)  
- `custom_script`: Executes an external script and returns output.  
  Params: `script_path`, `timeout`  
- `bme280_temperature`: Reads from BME280 sensor.  
  Params: `unit` ("C", "F", or "K")  
- `bme280_humidity`: Reads humidity from BME280.  
- `bme280_pressure`: Reads pressure (in hPa) from BME280.  

## Adding New Hardware Sensors

1. **Install Python Library** for your sensor.
2. **Write Reader Method** in `src/asnip/asnip.py`:
```python
def _read_my_new_sensor(self, params=None):
    try:
        # logic to read sensor
        return value
    except Exception as e:
        logger.error(f"Error reading MyNewSensor: {e}", exc_info=True)
        return None
```
3. **Update `sensor_reader_map`**:
```python
self.sensor_reader_map = {
    # existing...
    "my_new_sensor_type_name": self._read_my_new_sensor,
}
```
4. **Add Entry in `sensors.json`** using the new `type`.

(Optional) Add global init logic in `__init__()` if needed.

## Custom Script Security

**WARNING:** `custom_script` uses `shell=True`. Avoid using unsanitized input in `script_path`.

### Security Best Practices:

- Restrict access to `sensors.json`
- Use fixed script paths
- Write secure scripts
- Run with least privilege
- (Advanced) Use `shell=False` and pass commands as a list

## Project Structure

```
Akita-Sensor-Network-Integration-Plugin/
├── .github/
│   └── ...
├── src/
│   └── asnip/
│       ├── __init__.py
│       └── asnip.py
├── .gitignore
├── LICENSE
├── README.md
├── requirements.txt
└── sensors.json
```
