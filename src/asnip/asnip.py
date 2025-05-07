# Copyright (C) 2024 Akita Engineering <contact@akitaengineering.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
Akita Sensor Network Integration Plugin (ASNIP) for Meshtastic.

This plugin broadcasts sensor data read from a configurable set of sensors
and logs received sensor data from other nodes.
"""

import meshtastic
import meshtastic.plugin
import meshtastic.util
from meshtastic.mesh_interface import MeshInterface
from meshtastic.protobuf import mesh_pb2, portnums_pb2

import argparse
import json
import logging
import os
import queue
import random
import threading
import time
import subprocess # For a potential custom script sensor

# Attempt to import BME280 library, but don't fail if not present
# The actual usage will be guarded by checks or try-except blocks in the reader methods
try:
    import board
    import busio
    import adafruit_bme280
    BME280_AVAILABLE = True
except ImportError:
    BME280_AVAILABLE = False
    # logger is not yet defined here, so we can't log this yet.
    # We'll log it in __init__ if BME280 sensors are configured but lib is missing.


# Standard logger for the plugin
logger = logging.getLogger(__name__)

# Define a unique port number for ASNIP data
ASNIP_PORTNUM = portnums_pb2.PortNum.PRIVATE_APP_1 

# Default values
DEFAULT_LOG_FILE = "sensor_log.json"
DEFAULT_BROADCAST_INTERVAL = 30  # seconds
DEFAULT_SENSOR_CONFIG_FILE = "sensors.json" # Default name for sensor config

class ASNIP(meshtastic.plugin.Plugin):
    """
    Akita Sensor Network Integration Plugin with configurable sensors.
    """

    def __init__(self, interface: MeshInterface, args):
        super().__init__(interface, args) 

        if not interface:
            logger.critical("ASNIP initialized without a valid Meshtastic interface. Plugin will not function.")
            self.iface = None
            self.args = args 
            return 
        
        self.iface = interface 
        self.args = args 

        if not logger.handlers: # Configure logger if not already configured by Meshtastic
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO) 

        logger.info("ASNIP Plugin initializing...")
        if not BME280_AVAILABLE:
            logger.info("Adafruit BME280 library not found. BME280 sensor types will not be available unless the library is installed.")


        self.log_file_path = getattr(self.args, 'log', DEFAULT_LOG_FILE)
        self.broadcast_interval = getattr(self.args, 'interval', DEFAULT_BROADCAST_INTERVAL)
        self.sensor_config_file_path = getattr(self.args, 'sensor_config', DEFAULT_SENSOR_CONFIG_FILE)
        
        if self.broadcast_interval < 5:
            logger.warning(f"Broadcast interval {self.broadcast_interval}s is very short. Setting to 5s minimum.")
            self.broadcast_interval = 5

        logger.info(f"Log file: {self.log_file_path}")
        logger.info(f"Broadcast interval: {self.broadcast_interval} seconds")
        logger.info(f"Sensor configuration file: {self.sensor_config_file_path}")

        self.message_queue = queue.Queue()
        self.sensor_log_data = []
        self._load_log_data()

        self.sensor_configurations = []
        
        # Map sensor types from config to actual methods
        self.sensor_reader_map = {
            "simulated_temperature": self._read_simulated_temperature,
            "simulated_humidity": self._read_simulated_humidity,
            "random_value": self._read_random_value,
            "static_value": self._read_static_value,
            "custom_script": self._read_custom_script_value,
            "bme280_temperature": self._read_bme280_temperature,
            "bme280_humidity": self._read_bme280_humidity,
            "bme280_pressure": self._read_bme280_pressure,
            # Add more mappings here for new sensor reader functions
        }
        
        self._load_sensor_configurations() # Load after sensor_reader_map is defined for validation

        # BME280 specific initialization (if configured and available)
        self.bme280_sensor = None # Initialize to None
        self._initialize_bme280_if_needed()


        self.running = threading.Event()
        self.running.set() 

        self.broadcast_thread = None
        self.queue_processor_thread = None
        logger.info("ASNIP Plugin initialized.")

    def setup_args(self, parser: argparse.ArgumentParser):
        parser.add_argument(
            "--log",
            type=str,
            default=DEFAULT_LOG_FILE,
            help=f"Specifies the sensor data log file name (default: {DEFAULT_LOG_FILE})"
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=DEFAULT_BROADCAST_INTERVAL,
            help=f"Specifies the sensor broadcast interval in seconds (default: {DEFAULT_BROADCAST_INTERVAL}, min: 5)"
        )
        parser.add_argument(
            "--sensor-config",
            type=str,
            default=DEFAULT_SENSOR_CONFIG_FILE,
            help=f"Path to the sensor configuration JSON file (default: {DEFAULT_SENSOR_CONFIG_FILE})"
        )
        logger.debug("ASNIP arguments added to parser.")

    def _initialize_bme280_if_needed(self):
        """Initializes the BME280 sensor object if configured and library is available."""
        if not BME280_AVAILABLE:
            # Log if any BME280 type sensor is enabled in config but library is missing
            for conf in self.sensor_configurations:
                if conf.get("enabled") and conf.get("type", "").startswith("bme280_"):
                    logger.warning("BME280 sensor configured but Adafruit BME280 library is not installed. This sensor will not work.")
                    break # Log once
            return

        # Check if any BME280 sensor is enabled in the configuration
        bme280_configured_and_enabled = any(
            conf.get("enabled") and conf.get("type", "").startswith("bme280_")
            for conf in self.sensor_configurations
        )

        if bme280_configured_and_enabled and not self.bme280_sensor:
            try:
                # Create library object using our Bus I2C port
                # Users might need to change board.SCL and board.SDA depending on their hardware.
                # These are common defaults for Raspberry Pi, etc.
                i2c = busio.I2C(board.SCL, board.SDA)
                # The BME280 library can also take an address argument if non-default (e.g., adafruit_bme280.Adafruit_BME280_I2C(i2c, address=0x76))
                self.bme280_sensor = adafruit_bme280.Adafruit_BME280_I2C(i2c)
                # You can also configure sea_level_pressure for more accurate altitude.
                # self.bme280_sensor.sea_level_pressure = 1013.25 (hPa)
                logger.info("BME280 sensor initialized successfully.")
            except ValueError as e: # busio.I2C can raise ValueError if pins are invalid
                 logger.error(f"ValueError initializing BME280. Check I2C pins (SCL, SDA) and sensor connection: {e}", exc_info=True)
                 self.bme280_sensor = None # Ensure it's None if init fails
            except RuntimeError as e: # Can occur if sensor not found at address
                logger.error(f"RuntimeError initializing BME280. Sensor not found or communication error: {e}", exc_info=True)
                self.bme280_sensor = None
            except Exception as e:
                logger.error(f"Failed to initialize BME280 sensor: {e}", exc_info=True)
                self.bme280_sensor = None


    def _load_sensor_configurations(self):
        """Loads sensor definitions from the JSON configuration file."""
        try:
            if not os.path.exists(self.sensor_config_file_path):
                logger.warning(f"Sensor configuration file '{self.sensor_config_file_path}' not found. No sensors will be read.")
                self.sensor_configurations = []
                self._create_default_sensor_config()
                return

            with open(self.sensor_config_file_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                if "sensors" in config_data and isinstance(config_data["sensors"], list):
                    loaded_configs = config_data["sensors"]
                    logger.info(f"Loaded {len(loaded_configs)} sensor configurations from '{self.sensor_config_file_path}'.")
                    
                    valid_configs = []
                    for sensor_conf in loaded_configs:
                        conf_name = sensor_conf.get('name', 'UnnamedSensor')
                        conf_type = sensor_conf.get('type')
                        if conf_name and conf_type:
                             if conf_type not in self.sensor_reader_map:
                                logger.warning(f"Sensor '{conf_name}' has unknown type '{conf_type}'. Skipping.")
                                continue
                             # Specific check for BME280 if library is missing
                             if conf_type.startswith("bme280_") and not BME280_AVAILABLE:
                                 logger.warning(f"Sensor '{conf_name}' type '{conf_type}' requires Adafruit BME280 library, which is not installed. Skipping.")
                                 continue
                             valid_configs.append(sensor_conf)
                        else:
                            logger.warning(f"Invalid sensor configuration entry (missing name or type): {sensor_conf}. Skipping.")
                    self.sensor_configurations = valid_configs
                    logger.info(f"Found {len(self.sensor_configurations)} valid and loadable sensor configurations.")

                else:
                    logger.error(f"Sensor configuration file '{self.sensor_config_file_path}' is malformed. Expected a 'sensors' list.")
                    self.sensor_configurations = []
        except json.JSONDecodeError:
            logger.error(f"Malformed JSON in sensor configuration file '{self.sensor_config_file_path}'.")
            self.sensor_configurations = []
        except IOError as e:
            logger.error(f"IOError loading sensor configuration file '{self.sensor_config_file_path}': {e}", exc_info=True)
            self.sensor_configurations = []
        except Exception as e:
            logger.error(f"Unexpected error loading sensor configurations: {e}", exc_info=True)
            self.sensor_configurations = []
            
    def _create_default_sensor_config(self):
        """Creates a default sensors.json file if it doesn't exist."""
        default_config = {
            "sensors": [
                {
                    "name": "cpu_temp_sim",
                    "type": "simulated_temperature",
                    "enabled": True,
                    "params": {"min_temp": 35.0, "max_temp": 65.0, "unit": "C"}
                },
                {
                    "name": "room_humidity_sim",
                    "type": "simulated_humidity",
                    "enabled": True,
                    "params": {"min_hum": 40.0, "max_hum": 60.0, "unit": "%"}
                },
                {
                    "name": "random_metric",
                    "type": "random_value",
                    "enabled": True,
                    "params": {"min_val": 0, "max_val": 100}
                },
                {
                    "name": "device_status",
                    "type": "static_value",
                    "enabled": True,
                    "params": {"value": "online"}
                },
                {
                    "name": "custom_script_output",
                    "type": "custom_script",
                    "enabled": False, 
                    "params": {"script_path": "echo 'hello_world'", "timeout": 5}
                },
                {
                    "name": "ambient_temp_bme280",
                    "type": "bme280_temperature",
                    "enabled": False, # Disabled by default, requires setup
                    "params": {"unit": "C"} 
                },
                {
                    "name": "ambient_humidity_bme280",
                    "type": "bme280_humidity",
                    "enabled": False,
                    "params": {"unit": "%"}
                },
                {
                    "name": "barometric_pressure_bme280",
                    "type": "bme280_pressure",
                    "enabled": False,
                    "params": {"unit": "hPa"}
                }
            ]
        }
        try:
            with open(self.sensor_config_file_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=4)
            logger.info(f"Created default sensor configuration file at '{self.sensor_config_file_path}'. Please review, install necessary libraries (e.g., adafruit-circuitpython-bme280 for BME280 sensors), and enable sensors as needed.")
        except IOError as e:
            logger.error(f"Could not create default sensor config file: {e}", exc_info=True)


    # --- Sensor Reader Method Examples ---
    def _read_simulated_temperature(self, params=None):
        p = params or {}
        min_temp = p.get("min_temp", 15.0)
        max_temp = p.get("max_temp", 30.0)
        return round(random.uniform(min_temp, max_temp), 2)

    def _read_simulated_humidity(self, params=None):
        p = params or {}
        min_hum = p.get("min_hum", 30.0)
        max_hum = p.get("max_hum", 70.0)
        return round(random.uniform(min_hum, max_hum), 2)

    def _read_random_value(self, params=None):
        p = params or {}
        min_val = p.get("min_val", 0)
        max_val = p.get("max_val", 100)
        return random.randint(min_val, max_val)

    def _read_static_value(self, params=None):
        p = params or {}
        return p.get("value", None) 

    def _read_custom_script_value(self, params=None):
        p = params or {}
        script_path = p.get("script_path")
        timeout = p.get("timeout", 5) 

        if not script_path:
            logger.error("Custom script sensor: 'script_path' not provided in params.")
            return None
        try:
            result = subprocess.run(script_path, shell=True, capture_output=True, text=True, timeout=timeout, check=False)
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                logger.error(f"Custom script '{script_path}' failed with code {result.returncode}: {result.stderr.strip()}")
                return None
        except subprocess.TimeoutExpired:
            logger.error(f"Custom script '{script_path}' timed out after {timeout} seconds.")
            return None
        except FileNotFoundError:
            logger.error(f"Custom script '{script_path}' not found.")
            return None
        except Exception as e:
            logger.error(f"Error running custom script '{script_path}': {e}", exc_info=True)
            return None

    # --- BME280 Sensor Reader Methods ---
    def _read_bme280_temperature(self, params=None):
        p = params or {}
        unit = p.get("unit", "C").upper() # Default to Celsius

        if not self.bme280_sensor:
            logger.warning("Attempted to read BME280 temperature, but sensor is not initialized (or library missing).")
            return None
        try:
            temp_c = self.bme280_sensor.temperature
            if unit == "F":
                return round((temp_c * 9/5) + 32, 2)
            elif unit == "K":
                return round(temp_c + 273.15, 2)
            return round(temp_c, 2) # Default Celsius
        except Exception as e:
            logger.error(f"Error reading BME280 temperature: {e}", exc_info=True)
            return None

    def _read_bme280_humidity(self, params=None):
        # p = params or {} # params currently not used for humidity unit
        if not self.bme280_sensor:
            logger.warning("Attempted to read BME280 humidity, but sensor is not initialized (or library missing).")
            return None
        try:
            return round(self.bme280_sensor.humidity, 2)
        except Exception as e:
            logger.error(f"Error reading BME280 humidity: {e}", exc_info=True)
            return None

    def _read_bme280_pressure(self, params=None):
        # p = params or {} # params currently not used for pressure unit (defaults to hPa from library)
        if not self.bme280_sensor:
            logger.warning("Attempted to read BME280 pressure, but sensor is not initialized (or library missing).")
            return None
        try:
            return round(self.bme280_sensor.pressure, 2) # hPa
        except Exception as e:
            logger.error(f"Error reading BME280 pressure: {e}", exc_info=True)
            return None
    # --- End Sensor Reader Method Examples ---

    def _get_sensor_data(self):
        """
        Gathers data from all configured and enabled sensors.
        """
        if not self.iface:
            logger.error("No Meshtastic interface available in _get_sensor_data.")
            return None
        
        collected_data = {}
        if not self.sensor_configurations:
            logger.debug("No sensor configurations loaded, skipping sensor data collection.")
        
        for sensor_conf in self.sensor_configurations:
            if not sensor_conf.get("enabled", False):
                # logger.debug(f"Sensor '{sensor_conf['name']}' is disabled. Skipping.") # Can be noisy
                continue

            sensor_name = sensor_conf["name"]
            sensor_type = sensor_conf["type"]
            sensor_params = sensor_conf.get("params", {})

            reader_method = self.sensor_reader_map.get(sensor_type)
            if reader_method:
                try:
                    value = reader_method(sensor_params)
                    if value is not None: 
                        collected_data[sensor_name] = value
                        logger.debug(f"Read sensor '{sensor_name}': {value}")
                    else:
                        logger.info(f"Sensor '{sensor_name}' (type: {sensor_type}) returned None. Not included in payload.")
                except Exception as e:
                    logger.error(f"Error reading sensor '{sensor_name}' (type: {sensor_type}): {e}", exc_info=True)
            # No 'else' here because unknown types are already filtered during _load_sensor_configurations
        
        node_info = self.iface.getMyNodeInfo()
        local_node_id_num = node_info.get("myNodeNum") if node_info else None
        local_node_name = node_info.get("longName") if node_info else "Unknown Local Node"

        sensor_payload = {
            "source_node_num": local_node_id_num, 
            "source_node_name": local_node_name,
            "timestamp": time.time(), 
            "data": collected_data 
        }
        
        if not collected_data and self.sensor_configurations: # Log if configs exist but no data collected
             logger.info("No sensor data successfully collected in this cycle (all sensors failed, returned None, or disabled). Broadcasting basic node info.")
        elif not self.sensor_configurations: # Log if no configs at all
            logger.info("No sensors configured. Broadcasting basic node info.")


        logger.debug(f"Aggregated sensor payload for broadcast: {sensor_payload}")
        return sensor_payload

    def _load_log_data(self):
        try:
            if os.path.exists(self.log_file_path):
                with open(self.log_file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if not content.strip(): 
                        self.sensor_log_data = []
                        logger.info(f"Log file '{self.log_file_path}' is empty. Initializing with empty list.")
                        return
                    self.sensor_log_data = json.loads(content)
                    if not isinstance(self.sensor_log_data, list):
                        logger.warning(f"Log file '{self.log_file_path}' does not contain a JSON array. Resetting.")
                        self.sensor_log_data = []
                        self._save_log_data([]) 
                    else:
                        logger.info(f"Loaded {len(self.sensor_log_data)} records from '{self.log_file_path}'.")
            else:
                logger.info(f"Log file '{self.log_file_path}' not found. Will be created on first save.")
                self.sensor_log_data = []
        except json.JSONDecodeError:
            logger.error(f"Malformed JSON in '{self.log_file_path}'. Resetting log file.")
            self.sensor_log_data = []
            self._save_log_data([]) 
        except IOError as e:
            logger.error(f"IOError loading log file '{self.log_file_path}': {e}", exc_info=True)
            self.sensor_log_data = []

    def _save_log_data(self, data_to_save=None):
        data = data_to_save if data_to_save is not None else self.sensor_log_data
        try:
            with open(self.log_file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            logger.debug(f"Sensor data saved to '{self.log_file_path}'. Total records: {len(data)}")
        except IOError as e:
            logger.error(f"Error saving log file '{self.log_file_path}': {e}", exc_info=True)
        except TypeError as e:
            logger.error(f"TypeError during JSON serialization for log file: {e}", exc_info=True)


    def _broadcast_sensor_data_loop(self):
        if not self.iface: return 
        logger.info("Sensor data broadcast thread started.")
        while self.running.is_set():
            try:
                sensor_payload_to_broadcast = self._get_sensor_data() 
                if sensor_payload_to_broadcast: # Will always be a dict, even if data is empty
                    log_entry_self = {
                        "log_timestamp": time.time(), 
                        "type": "self",
                        "source_node_num": sensor_payload_to_broadcast.get("source_node_num"),
                        "source_node_hex": f"!{sensor_payload_to_broadcast.get('source_node_num'):08x}" if sensor_payload_to_broadcast.get('source_node_num') is not None else None,
                        "rssi": None, 
                        "snr": None,  
                        "payload": sensor_payload_to_broadcast 
                    }
                    self.sensor_log_data.append(log_entry_self)
                    self._save_log_data() 

                    self.message_queue.put(sensor_payload_to_broadcast) 
                    logger.debug(f"Queued self-generated sensor payload for broadcast: {sensor_payload_to_broadcast}")
                
                for _ in range(self.broadcast_interval):
                    if not self.running.is_set():
                        break
                    time.sleep(1) 
            except Exception as e:
                logger.error(f"Exception in broadcast loop: {e}", exc_info=True)
                time.sleep(5) # Avoid rapid error looping if something is persistently failing
        logger.info("Sensor data broadcast thread stopped.")


    def _process_message_queue_loop(self):
        if not self.iface: return 
        logger.info("Message queue processing thread started.")
        while self.running.is_set():
            try:
                full_sensor_payload = self.message_queue.get(timeout=1) 
                if full_sensor_payload: 
                    try:
                        data_bytes = json.dumps(full_sensor_payload).encode('utf-8')
                        
                        self.iface.sendData(
                            data_bytes,
                            portNum=ASNIP_PORTNUM,
                            wantAck=False, 
                        )
                        logger.info(f"Sent sensor payload: {full_sensor_payload.get('data', {}).keys() or 'basic node info'}") # Log keys of data or placeholder
                    except meshtastic.MeshtasticException as me:
                        logger.error(f"Meshtastic error sending data: {me}", exc_info=True)
                    except Exception as e:
                        logger.error(f"Error sending data from queue: {e}", exc_info=True)
                    finally:
                        self.message_queue.task_done()
            except queue.Empty:
                continue # Normal, just means queue was empty
            except Exception as e:
                logger.error(f"Exception in queue processing loop: {e}", exc_info=True)
                time.sleep(1) 
        logger.info("Message queue processing thread stopped.")


    def onReceive(self, packet, interface: MeshInterface): 
        if not self.iface: 
            logger.error("No Meshtastic interface in onReceive.")
            super().onReceive(packet, interface) 
            return

        decoded_packet = packet.get('decoded')
        if decoded_packet and decoded_packet.get('portnum') == ASNIP_PORTNUM:
            try:
                payload_bytes = decoded_packet.get('payload')
                if not payload_bytes:
                    logger.warning("Received ASNIP packet with no payload.")
                    return 

                received_full_payload = json.loads(payload_bytes.decode('utf-8'))
                
                from_node_id_hex = packet.get('fromId') 
                rssi = packet.get('rxRssi')
                snr = packet.get('rxSnr')

                logger.info(f"Received sensor payload from {from_node_id_hex} (RSSI:{rssi}, SNR:{snr}): {received_full_payload.get('data', {}).keys() or 'basic node info'}")

                log_entry_remote = {
                    "log_timestamp": time.time(), 
                    "type": "remote",
                    "source_node_hex": from_node_id_hex,
                    "source_node_num": meshtastic.util.nodeNumFromString(from_node_id_hex) if from_node_id_hex else None,
                    "rssi": rssi,
                    "snr": snr,
                    "payload": received_full_payload 
                }
                self.sensor_log_data.append(log_entry_remote)
                self._save_log_data()
                return # Packet handled by ASNIP

            except json.JSONDecodeError:
                logger.warning(f"Received malformed JSON on ASNIP port from {packet.get('fromId')}: {payload_bytes}", exc_info=True)
            except UnicodeDecodeError:
                logger.warning(f"Could not decode payload as UTF-8 on ASNIP port from {packet.get('fromId')}", exc_info=True)
            except Exception as e:
                logger.error(f"Error processing received ASNIP packet: {e}", exc_info=True)
        
        super().onReceive(packet, interface) # Pass to other plugins if not for ASNIP or error


    def start(self):
        if not self.iface:
            logger.error("ASNIP cannot start: Meshtastic interface not available.")
            return

        logger.info("ASNIP Plugin starting...")
        self._load_sensor_configurations() 
        self._initialize_bme280_if_needed() # Re-initialize BME280 in case config changed
        self.running.set()

        self.broadcast_thread = threading.Thread(target=self._broadcast_sensor_data_loop, daemon=True)
        self.broadcast_thread.start()

        self.queue_processor_thread = threading.Thread(target=self._process_message_queue_loop, daemon=True)
        self.queue_processor_thread.start()
        
        logger.info("ASNIP Plugin started threads.")

    def stop(self):
        logger.info("ASNIP Plugin stopping...")
        self.running.clear() 

        if self.queue_processor_thread: 
            try:
                self.message_queue.put(None) # Unblock queue.get() if it's waiting
            except Exception as e: # Ignore errors if queue is already closed etc.
                logger.debug(f"Minor error putting None to queue on stop: {e}")

        if self.broadcast_thread and self.broadcast_thread.is_alive():
            logger.debug("Waiting for broadcast thread to join...")
            self.broadcast_thread.join(timeout=5) # Wait up to 5 seconds
            if self.broadcast_thread.is_alive():
                logger.warning("Broadcast thread did not join in time.")
        
        if self.queue_processor_thread and self.queue_processor_thread.is_alive():
            logger.debug("Waiting for queue processor thread to join...")
            self.queue_processor_thread.join(timeout=5) # Wait up to 5 seconds
            if self.queue_processor_thread.is_alive():
                logger.warning("Queue processor thread did not join in time.")

        if self.iface: # Only try to save if plugin was properly initialized
            self._save_log_data()
        logger.info("ASNIP Plugin stopped.")


