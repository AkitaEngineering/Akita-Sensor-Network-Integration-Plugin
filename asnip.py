import meshtastic
import time
import json
import threading
import os
import argparse
import logging
from meshtastic.util import get_lora_config
import queue

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ASNIP:
    def __init__(self, interface, log_file="sensor_log.json", sensor_interval=30):
        self.interface = interface
        self.sensor_data = {}
        self.sensor_thread = None
        self.user_id = interface.meshtastic.getMyNodeInfo()['num']
        self.lora_config = get_lora_config(interface.meshtastic)
        self.sensor_interval = sensor_interval
        self.log_file = log_file
        self.sensor_data_source = self._get_sensor_data
        self.running = True
        self.message_queue = queue.Queue()
        self.publish_thread = threading.Thread(target=self._publish_from_queue)
        self.publish_thread.daemon = True
        self.publish_thread.start()

    def _get_sensor_data(self):
        try:
            import random
            return {
                "temperature": random.uniform(15, 30),
                "humidity": random.uniform(40, 70),
            }
        except Exception as e:
            logging.error(f"Error getting sensor data: {e}")
            return {}

    def start_sensor_broadcast(self):
        self.sensor_thread = threading.Thread(target=self._send_sensor_broadcast)
        self.sensor_thread.start()
        logging.info("Sensor broadcast started.")

    def stop_sensor_broadcast(self):
        self.running = False
        if self.sensor_thread:
            self.sensor_thread.join()
            logging.info("Sensor broadcast stopped.")

    def _send_sensor_broadcast(self):
        while self.running:
            try:
                sensor_values = self.sensor_data_source()
                self.sensor_data = {
                    "type": "sensor",
                    "user_id": self.user_id,
                    "sensor_values": sensor_values,
                    "timestamp": time.time(),
                }
                self.message_queue.put(self.sensor_data)
                time.sleep(self.sensor_interval)
            except Exception as e:
                logging.error(f"Error sending sensor broadcast: {e}")
                time.sleep(10)

    def _publish_from_queue(self):
        while self.running:
            try:
                message = self.message_queue.get(timeout=1)
                self.interface.sendData(message, portNum=meshtastic.constants.DATA_APP)
                time.sleep(self.lora_config.tx_delay / 1000)
            except queue.Empty:
                pass
            except Exception as e:
                logging.error(f"Error in publish thread: {e}")

    def handle_incoming(self, packet, interface):
        if packet['decoded']['portNum'] == meshtastic.constants.DATA_APP:
            decoded = packet['decoded']['payload']
            if decoded.get("type") == "sensor":
                logging.info(f"Sensor data received: {decoded}")
                self.log_sensor_data(decoded)

    def log_sensor_data(self, data):
        try:
            if not os.path.exists(self.log_file):
                with open(self.log_file, 'w') as f:
                    f.write('[]')

            with open(self.log_file, 'r+') as f:
                try:
                    file_data = json.load(f)
                except json.JSONDecodeError:
                    file_data = []
                file_data.append(data)
                f.seek(0)
                json.dump(file_data, f, indent=4)
        except Exception as e:
            logging.error(f"Error logging sensor data: {e}")

    def onConnection(self, interface, connected):
        if connected:
            logging.info("ASNIP: Meshtastic connected.")
            self.start_sensor_broadcast()
        else:
            logging.info("ASNIP: Meshtastic disconnected.")
            self.stop_sensor_broadcast()

def onReceive(packet, interface):
    asnip.handle_incoming(packet, interface)

def onConnection(interface, connected):
    asnip.onConnection(interface, connected)

def main():
    parser = argparse.ArgumentParser(description="Akita Sensor Network Integration Plugin")
    parser.add_argument("--log", default="sensor_log.json", help="Log file name")
    parser.add_argument("--interval", type=int, default=30, help="Sensor broadcast interval in seconds")
    args = parser.parse_args()

    interface = meshtastic.SerialInterface()
    global asnip
    asnip = ASNIP(interface, args.log, args.interval)
    interface.addReceiveCallback(onReceive)
    interface.addConnectionCallback(onConnection)

    try:
        while asnip.running:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("ASNIP: Stopping...")
        asnip.stop_sensor_broadcast()
        logging.info("ASNIP: Stopped")

if __name__ == '__main__':
    main()
