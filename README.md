# Akita Sensor Network Integration Plugin (ASNIP)

ASNIP is a Meshtastic plugin designed to integrate sensor data into the Meshtastic network. It allows users to broadcast sensor readings and receive data from other sensor nodes.

## Features

-   **Sensor Data Broadcast:** Periodically broadcasts sensor data over the Meshtastic network.
-   **Sensor Data Logging:** Logs all received sensor data to a JSON file.
-   **Configurable Sensor Interval:** Allows users to adjust the frequency of sensor data broadcasts via command-line arguments.
-   **Extensible Sensor Data Source:** Provides a placeholder for integrating various sensor data retrieval methods.
-   **Configurable Log File:** Allows users to specify the log file name via command-line arguments.
-   **Robust Error Handling:** Includes error handling for file I/O and network operations.
-   **Respects TX Delay:** The plugin will respect the TX delay of the LoRa configuration.

## Installation

1.  Place `asnip.py` in your Meshtastic plugins directory.
2.  Replace the `_get_sensor_data()` function with your actual sensor data retrieval logic.
3.  Run Meshtastic with the plugin enabled.

## Usage

-   Sensor data is automatically broadcast at the configured interval.
-   Received sensor data is logged in the specified log file (default: `sensor_log.json`).
-   Modify `sensor_interval` to change the broadcast frequency.
-   Modify `_get_sensor_data` to read from real sensors.

## Command-Line Arguments

-   `--log`: Specifies the log file name (default: `sensor_log.json`).
-   `--interval`: Specifies the sensor broadcast interval in seconds (default: 30).

## Dependencies

-   Meshtastic Python API

## Akita Engineering
