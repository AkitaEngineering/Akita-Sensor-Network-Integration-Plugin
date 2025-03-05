# asnip.py - Akita Sensor Network Integration Plugin
import meshtastic
import time
import json
import threading
import os
from meshtastic.util import generate_random_id
from meshtastic.util import get_lora_config

class ASNIP:
    def __init__(self, interface):
        self.interface = interface
        self.sensor_data = {}
        self.sensor_thread = None
        self.user_id = interface.meshtastic.getMyNodeInfo()['num']
        self.lora_config = get_lora_config(interface.meshtastic)
        self.sensor_interval = 30  # Send sensor data every 30 seconds (adjust as needed)
        self.sensor_data_source = self._get_sensor_data  # Placeholder for sensor data retrieval

    def _get_sensor_data(self):
        # Placeholder: Replace with actual sensor data retrieval logic
        # Example: Simulating temperature and humidity data
        import random
        return {
            "temperature": random.uniform(15, 30),
            "humidity": random.uniform(40, 70),
        }

    def start_sensor_broadcast(self):
        self.sensor_thread = threading.Thread(target=self._send_sensor_broadcast)
        self.sensor_thread.start()
        print("Sensor broadcast started.")

    def stop_sensor_broadcast(self):
        if self.sensor_thread:
            self.sensor_thread.join(timeout=2)
            print("Sensor broadcast stopped.")

    def _send_sensor_broadcast(self):
        while True:
            sensor_values = self.sensor_data_source()
            self.sensor_data = {
                "type": "sensor",
                "user_id": self.user_id,
                "sensor_values": sensor_values,
                "timestamp": time.time(),
            }
            self.interface.sendData(self.sensor_data, portNum=meshtastic.constants.DATA_APP)
            time.sleep(self.sensor_interval)

    def handle_incoming(self, packet, interface):
        if packet['decoded']['portNum'] == meshtastic.constants.DATA_APP:
            decoded = packet['decoded']['payload']
            if decoded.get("type") == "sensor":
                print(f"Sensor data received: {decoded}")
                self.log_sensor_data(decoded)

    def log_sensor_data(self, data):
        filename = f"sensor_log_{time.strftime('%Y%m%d')}.json"
        if not os.path.exists(filename):
            with open(filename, 'w') as f:
                f.write('[]')

        with open(filename, 'r+') as f:
            file_data = json.load(f)
            file_data.append(data)
            f.seek(0)
            json.dump(file_data, f, indent=4)

    def onConnection(self, interface, connected):
        if connected:
            print("ASNIP: Meshtastic connected.")
            self.start_sensor_broadcast()
        else:
            print("ASNIP: Meshtastic disconnected.")
            self.stop_sensor_broadcast()

def onReceive(packet, interface):
    asnip.handle_incoming(packet, interface)

def onConnection(interface, connected):
    asnip.onConnection(interface, connected)

def main():
    interface = meshtastic.SerialInterface()
    global asnip
    asnip = ASNIP(interface)
    interface.addReceiveCallback(onReceive)
    interface.addConnectionCallback(onConnection)

if __name__ == '__main__':
    main()
