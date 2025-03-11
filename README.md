# Akita Sensor Network Integration Plugin (ASNIP)

ASNIP is a Meshtastic plugin designed to integrate sensor data into the Meshtastic network. It allows users to broadcast sensor readings and receive data from other sensor nodes.

## Features

* **Sensor Data Broadcast:** Periodically broadcasts sensor data over the Meshtastic network.
* **Sensor Data Logging:** Logs all received sensor data to a JSON file.
* **Configurable Sensor Interval:** Allows users to adjust the frequency of sensor data broadcasts via command-line arguments.
* **Extensible Sensor Data Source:** Provides a placeholder for integrating various sensor data retrieval methods.
* **Configurable Log File:** Allows users to specify the log file name via command-line arguments.
* **Robust Error Handling:** Includes error handling for file I/O, network operations, and sensor data retrieval.
* **Respects TX Delay:** The plugin respects the TX delay of the LoRa configuration using a message queue.
* **Graceful Shutdown:** Handles keyboard interrupts for clean plugin termination.
* **Message Queueing:** Uses a message queue to buffer sensor data before transmission.
* **JSON Error Handling:** Handles malformed json log files.

## Installation

1.  Place `asnip.py` in your Meshtastic plugins directory.
2.  Install the Meshtastic Python API if not already installed.
3.  Run Meshtastic with the plugin enabled.

## Usage

* Sensor data is automatically broadcast at the configured interval.
* Received sensor data is logged in the specified log file (default: `sensor_log.json`).
* Use Ctrl+C to stop the plugin gracefully.
* Modify the `_get_sensor_data()` function to integrate your actual sensor data retrieval logic.

## Command-Line Arguments

* `--log`: Specifies the log file name (default: `sensor_log.json`).
* `--interval`: Specifies the sensor broadcast interval in seconds (default: 30).

## Dependencies

* Meshtastic Python API

## Configuration

The plugin is configured via command-line arguments.

## Logging

The plugin uses the Python `logging` module for detailed logging.

## Sensor Log File

The sensor log file is a JSON file that stores received sensor data. If the file does not exist, it will be created. If the file is malformed, it will be reset to an empty array.

## Sensor Data Source

The `_get_sensor_data()` function is a placeholder for your sensor data retrieval logic. Replace the example code with your actual sensor integration.

## Akita Engineering

This project is developed and maintained by Akita Engineering. We are dedicated to creating innovative solutions for LoRa and Meshtastic networks.
