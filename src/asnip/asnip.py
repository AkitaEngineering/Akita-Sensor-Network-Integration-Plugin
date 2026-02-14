# Copyright (C) 2024 Akita Engineering <info@akitaengineering.com>
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

# Meshtastic imports are optional at import-time so the module can be
# imported for unit tests or static analysis in environments where the
# Meshtastic package is not installed. At runtime (on-device) the real
# package will be used.
try:
    import meshtastic
    import meshtastic.plugin
    import meshtastic.util
    from meshtastic.mesh_interface import MeshInterface
    from meshtastic.protobuf import mesh_pb2, portnums_pb2
except Exception:  # pragma: no cover - fallback for non-device environments
    # Provide minimal runtime-compatible stubs so the module can be imported
    # in environments where the Meshtastic package isn't available (tests,
    # static analysis, CI, etc.).
    class _StubPluginBase:
        def __init__(self, interface=None, args=None):
            self._iface = interface

        def onReceive(self, packet, interface):
            return None

    class _StubMeshtasticModule:
        plugin = type("plugin", (), {"Plugin": _StubPluginBase})
        util = None

    meshtastic = _StubMeshtasticModule()

    class MeshInterface:  # type: ignore
        """Lightweight stand-in for type annotations only."""
        pass

    class _DummyPortNum:
        PRIVATE_APP_1 = 100

    class portnums_pb2:  # type: ignore
        PortNum = _DummyPortNum


import argparse
import json
import logging
import os
import queue
import random
import threading
import time
import subprocess

# Attempt to import BME280 library
try:
    import board
    import busio
    import adafruit_bme280
    BME280_AVAILABLE = True
except ImportError:
    BME280_AVAILABLE = False

# Standard logger for the plugin
logger = logging.getLogger(__name__)

# Define a unique port number for ASNIP data
ASNIP_PORTNUM = portnums_pb2.PortNum.PRIVATE_APP_1 

# Default filenames
DEFAULT_CONFIG_FILENAME = "sensors.json"
DEFAULT_LOG_FILENAME = "sensor_log.json"
DEFAULT_INTERVAL = 30

class ASNIP(meshtastic.plugin.Plugin):
    """
    Akita Sensor Network Integration Plugin with configurable sensors.
    """

    def __init__(self, interface: MeshInterface, args=None):
        # Note: 'args' might be ignored if CLI doesn't pass them through, 
        # so we rely on file-based config.
        super().__init__(interface, args) 

        if not interface:
            logger.critical("ASNIP initialized without a valid Meshtastic interface. Plugin will not function.")
            self.iface = None
            return 
        
        self.iface = interface 

        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO) 

        logger.info("ASNIP Plugin initializing...")
        if not BME280_AVAILABLE:
            logger.info("Adafruit BME280 library not found. BME280 sensor types will not be available.")

        # --- Determine Configuration File Path ---
        # Priority: 
        # 1. Environment Variable 'ASNIP_CONFIG'
        # 2. 'sensors.json' in Current Working Directory
        # 3. 'sensors.json' in the same directory as this script
        
        self.config_file_path = os.environ.get("ASNIP_CONFIG")
        
        if not self.config_file_path:
            cwd_config = os.path.join(os.getcwd(), DEFAULT_CONFIG_FILENAME)
            if os.path.exists(cwd_config):
                self.config_file_path = cwd_config
            else:
                # Fallback to plugin directory
                plugin_dir = os.path.dirname(os.path.abspath(__file__))
                self.config_file_path = os.path.join(plugin_dir, DEFAULT_CONFIG_FILENAME)

        logger.info(f"Using configuration file: {self.config_file_path}")

        # Initialize defaults
        self.log_file_path = DEFAULT_LOG_FILENAME
        self.broadcast_interval = DEFAULT_INTERVAL
        self.sensor_configurations = []

        # Map sensor types
        self.sensor_reader_map = {
            "simulated_temperature": self._read_simulated_temperature,
            "simulated_humidity": self._read_simulated_humidity,
            "random_value": self._read_random_value,
            "static_value": self._read_static_value,
            "custom_script": self._read_custom_script_value,
            "bme280_temperature": self._read_bme280_temperature,
            "bme280_humidity": self._read_bme280_humidity,
            "bme280_pressure": self._read_bme280_pressure,
        }

        # Load Config (Settings + Sensors)
        self._load_configuration()
        
        # Initialize State
        self.message_queue = queue.Queue()
        self.sensor_log_data = []
        self._load_log_data()

        # BME280 Init
        self.bme280_sensor = None 
        self._initialize_bme280_if_needed()

        self.running = threading.Event()
        self.running.set() 

        self.broadcast_thread = None
        self.queue_processor_thread = None
        logger.info("ASNIP Plugin initialized.")

    # We no longer rely on setup_args since Meshtastic CLI likely won't pass them correctly
    # def setup_args(self, parser): ...

    def _initialize_bme280_if_needed(self):
        """Initializes the BME280 sensor object if configured and library is available."""
        if not BME280_AVAILABLE:
            return

        bme280_configured_and_enabled = any(
            conf.get("enabled") and conf.get("type", "").startswith("bme280_")
            for conf in self.sensor_configurations
        )

        if bme280_configured_and_enabled and not self.bme280_sensor:
            try:
                i2c = busio.I2C(board.SCL, board.SDA)
                self.bme280_sensor = adafruit_bme280.Adafruit_BME280_I2C(i2c)
                logger.info("BME280 sensor initialized successfully.")
            except Exception as e:
                logger.error(f"Failed to initialize BME280 sensor: {e}", exc_info=True)
                self.bme280_sensor = None

    def _load_configuration(self):
        """Loads settings and sensors from the JSON configuration file."""
        try:
            if not os.path.exists(self.config_file_path):
                logger.warning(f"Configuration file '{self.config_file_path}' not found. Creating default.")
                self._create_default_config()
                # Re-read after creating
                if not os.path.exists(self.config_file_path):
                     return # Should not happen

            with open(self.config_file_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                
                # 1. Load Global Settings
                settings = config_data.get("settings", {})
                self.log_file_path = settings.get("log_file", DEFAULT_LOG_FILENAME)
                self.broadcast_interval = settings.get("broadcast_interval", DEFAULT_INTERVAL)
                
                if self.broadcast_interval < 5:
                    logger.warning(f"Interval {self.broadcast_interval}s too short. Setting to 5s.")
                    self.broadcast_interval = 5

                logger.info(f"Log File: {self.log_file_path}")
                logger.info(f"Broadcast Interval: {self.broadcast_interval}s")

                # 2. Load Sensors
                if "sensors" in config_data and isinstance(config_data["sensors"], list):
                    loaded_configs = config_data["sensors"]
                    valid_configs = []
                    for sensor_conf in loaded_configs:
                        conf_name = sensor_conf.get('name', 'UnnamedSensor')
                        conf_type = sensor_conf.get('type')
                        if conf_name and conf_type:
                             if conf_type not in self.sensor_reader_map:
                                logger.warning(f"Sensor '{conf_name}' has unknown type '{conf_type}'. Skipping.")
                                continue
                             if conf_type.startswith("bme280_") and not BME280_AVAILABLE:
                                 logger.warning(f"Sensor '{conf_name}' requires BME280 lib. Skipping.")
                                 continue
                             valid_configs.append(sensor_conf)
                    self.sensor_configurations = valid_configs
                    logger.info(f"Loaded {len(self.sensor_configurations)} valid sensors.")
                else:
                    logger.warning("No 'sensors' list found in config.")
                    self.sensor_configurations = []

        except json.JSONDecodeError:
            logger.error(f"Malformed JSON in config file '{self.config_file_path}'. Using defaults.")
        except Exception as e:
            logger.error(f"Error loading config: {e}", exc_info=True)
            
    def _create_default_config(self):
        """Creates a default configuration file."""
        default_config = {
            "settings": {
                "log_file": DEFAULT_LOG_FILENAME,
                "broadcast_interval": DEFAULT_INTERVAL
            },
            "sensors": [
                {
                    "name": "cpu_temp_sim",
                    "type": "simulated_temperature",
                    "enabled": True,
                    "params": {"min_temp": 35.0, "max_temp": 65.0, "unit": "C"}
                },
                {
                    "name": "device_status",
                    "type": "static_value",
                    "enabled": True,
                    "params": {"value": "online"}
                }
            ]
        }
        try:
            with open(self.config_file_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=4)
            logger.info(f"Created default configuration at '{self.config_file_path}'.")
        except IOError as e:
            logger.error(f"Could not create default config file: {e}", exc_info=True)

    # ... [Sensor Reader Methods remain unchanged: _read_simulated_temperature, etc.] ...
    # ... [Include all sensor reading methods from previous version here] ...
    
    def _read_simulated_temperature(self, params=None):
        p = params or {}
        return round(random.uniform(p.get("min_temp", 15.0), p.get("max_temp", 30.0)), 2)

    def _read_simulated_humidity(self, params=None):
        p = params or {}
        return round(random.uniform(p.get("min_hum", 30.0), p.get("max_hum", 70.0)), 2)

    def _read_random_value(self, params=None):
        p = params or {}
        return random.randint(p.get("min_val", 0), p.get("max_val", 100))

    def _read_static_value(self, params=None):
        return (params or {}).get("value", None)

    def _read_custom_script_value(self, params=None):
        p = params or {}
        script_path = p.get("script_path")
        if not script_path: return None
        try:
            result = subprocess.run(script_path, shell=True, capture_output=True, text=True, timeout=p.get("timeout", 5), check=False)
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception as e:
            logger.error(f"Script error: {e}")
            return None

    def _read_bme280_temperature(self, params=None):
        if not self.bme280_sensor: return None
        return round(self.bme280_sensor.temperature, 2)

    def _read_bme280_humidity(self, params=None):
        if not self.bme280_sensor: return None
        return round(self.bme280_sensor.humidity, 2)

    def _read_bme280_pressure(self, params=None):
        if not self.bme280_sensor: return None
        return round(self.bme280_sensor.pressure, 2)

    # ... [_get_sensor_data, _load_log_data, _save_log_data remain unchanged] ...
    
    def _get_sensor_data(self):
        if not self.iface:
            return None

        collected_data: Dict[str, Any] = {}
        for sensor_conf in self.sensor_configurations:
            if not sensor_conf.get("enabled", False):
                continue
            reader = self.sensor_reader_map.get(sensor_conf["type"])
            if reader:
                try:
                    val = reader(sensor_conf.get("params", {}))
                    if val is not None:
                        collected_data[sensor_conf["name"]] = val
                except Exception:
                    # individual readers should log their own errors;
                    # don't let a single sensor break collection
                    logger.exception("Sensor reader failed for %s", sensor_conf.get("name"))

        # Be defensive: MeshInterface.getMyNodeInfo() may return a dict or an
        # object with attributes depending on Meshtastic version. Handle
        # both safely so the plugin is resilient to API shape changes.
        node_num = None
        node_name = "Unknown"
        try:
            node_info = None
            if hasattr(self.iface, "getMyNodeInfo"):
                try:
                    node_info = self.iface.getMyNodeInfo()
                except Exception as exc:  # defensive
                    logger.debug("getMyNodeInfo() raised: %s", exc)
                    node_info = None

            if isinstance(node_info, dict):
                node_num = node_info.get("myNodeNum")
                node_name = node_info.get("longName", node_name)
            else:
                node_num = getattr(node_info, "myNodeNum", None)
                node_name = (
                    getattr(node_info, "longName", None)
                    or getattr(node_info, "long_name", None)
                    or node_name
                )
        except Exception:
            logger.debug("Failed to read node info from interface", exc_info=True)

        return {
            "source_node_num": node_num,
            "source_node_name": node_name,
            "timestamp": time.time(),
            "data": collected_data,
        }

    def _load_log_data(self):
        # [Same logic as before using self.log_file_path]
        try:
            if os.path.exists(self.log_file_path):
                with open(self.log_file_path, 'r') as f:
                    c = f.read().strip()
                    self.sensor_log_data = json.loads(c) if c else []
            else: self.sensor_log_data = []
        except Exception:
             self.sensor_log_data = []

    def _save_log_data(self, data=None):
         # [Same logic as before using self.log_file_path]
         d = data if data is not None else self.sensor_log_data
         try:
            with open(self.log_file_path, 'w') as f: json.dump(d, f, indent=4)
         except Exception as e: logger.error(f"Save failed: {e}")

    def _broadcast_sensor_data_loop(self):
        if not self.iface: return 
        logger.info("Broadcast thread started.")
        while self.running.is_set():
            try:
                payload = self._get_sensor_data()
                if payload:
                    self.sensor_log_data.append({
                        "timestamp": time.time(), "type": "self", 
                        "source_node_num": payload.get("source_node_num"), "payload": payload
                    })
                    self._save_log_data()
                    self.message_queue.put(payload)
                
                # Interruptible sleep
                for _ in range(self.broadcast_interval):
                    if not self.running.is_set(): break
                    time.sleep(1)
            except Exception as e:
                logger.error(f"Broadcast error: {e}")
                time.sleep(5)

    def _process_message_queue_loop(self):
        if not self.iface: return 
        logger.info("Queue thread started.")
        while self.running.is_set():
            try:
                payload = self.message_queue.get(timeout=1)
                if payload:
                    self.iface.sendData(json.dumps(payload).encode('utf-8'), portNum=ASNIP_PORTNUM, wantAck=False)
                    logger.info(f"Sent payload with {len(payload.get('data', {}))} sensors")
                    self.message_queue.task_done()
            except queue.Empty: continue
            except Exception as e: logger.error(f"Send error: {e}")

    def onReceive(self, packet, interface):
        if not self.iface: 
            super().onReceive(packet, interface)
            return
        
        # Check portnum
        decoded = packet.get('decoded')
        if decoded and decoded.get('portnum') == ASNIP_PORTNUM:
            try:
                data = json.loads(decoded.get('payload').decode('utf-8'))
                self.sensor_log_data.append({
                    "timestamp": time.time(), "type": "remote",
                    "source_node_hex": packet.get('fromId'), "rssi": packet.get('rxRssi'), "payload": data
                })
                self._save_log_data()
                logger.info(f"Received ASNIP packet from {packet.get('fromId')}")
                return
            except Exception as e: logger.error(f"Rx error: {e}")
        
        super().onReceive(packet, interface)

    def start(self):
        if not self.iface: return
        self._load_configuration() # Reload config on start
        self._initialize_bme280_if_needed()
        self.running.set()
        self.broadcast_thread = threading.Thread(target=self._broadcast_sensor_data_loop, daemon=True)
        self.broadcast_thread.start()
        self.queue_processor_thread = threading.Thread(target=self._process_message_queue_loop, daemon=True)
        self.queue_processor_thread.start()

    def stop(self, timeout: float = 5.0):
        """Stop background threads and persist any pending log data.

        The timeout is applied to thread joins and is best-effort — threads
        are asked to stop via the `running` event and then joined.
        """
        self.running.clear()

        # Wait for threads to finish (non-blocking if they already stopped)
        try:
            if self.broadcast_thread and self.broadcast_thread.is_alive():
                self.broadcast_thread.join(timeout)
        except Exception:
            logger.debug("Error joining broadcast thread", exc_info=True)

        try:
            if self.queue_processor_thread and self.queue_processor_thread.is_alive():
                self.queue_processor_thread.join(timeout)
        except Exception:
            logger.debug("Error joining queue processor thread", exc_info=True)

        # Best-effort drain/cleanup of the message queue
        try:
            while not self.message_queue.empty():
                try:
                    self.message_queue.get_nowait()
                    self.message_queue.task_done()
                except Exception:
                    break
        except Exception:
            pass

        # Persist logs
        if self.iface:
            self._save_log_data()
