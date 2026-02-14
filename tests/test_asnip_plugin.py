import os
import sys
import tempfile
import threading
import time

# Make src/ available on sys.path so tests can import the package directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from asnip.asnip import ASNIP


class FakeInterface:
    def __init__(self, node_num=42, long_name="fake-node"):
        self._node_info = {"myNodeNum": node_num, "longName": long_name}
        self.sent = []

    def getMyNodeInfo(self):
        return self._node_info

    def sendData(self, payload, portNum=None, wantAck=False):
        # store sent payload for assertions
        self.sent.append((payload, portNum, wantAck))


def test_create_default_config_and_load(tmp_path, monkeypatch):
    cfg_path = str(tmp_path / "sensors.json")
    monkeypatch.setenv("ASNIP_CONFIG", cfg_path)

    iface = FakeInterface()
    plugin = ASNIP(iface)

    # default config should have been created
    assert os.path.exists(cfg_path)
    assert isinstance(plugin.sensor_configurations, list)
    assert len(plugin.sensor_configurations) >= 1


def test_get_sensor_data_handles_nodeinfo_variants():
    # dict-style node info
    iface = FakeInterface(node_num=99, long_name="dict-node")
    plugin = ASNIP(iface)
    plugin.sensor_configurations = [
        {"name": "s1", "type": "simulated_temperature", "enabled": True, "params": {"min_temp": 1, "max_temp": 2}}
    ]

    data = plugin._get_sensor_data()
    assert data["source_node_num"] == 99
    assert data["source_node_name"] == "dict-node"
    assert "s1" in data["data"]

    # object-style node info
    class ObjInfo:
        myNodeNum = 7
        longName = "obj-node"

    class ObjIface(FakeInterface):
        def getMyNodeInfo(self):
            return ObjInfo()

    plugin2 = ASNIP(ObjIface())
    plugin2.sensor_configurations = plugin.sensor_configurations
    d2 = plugin2._get_sensor_data()
    assert d2["source_node_num"] == 7
    assert d2["source_node_name"] == "obj-node"


def test_start_and_stop_threads_do_not_hang(monkeypatch):
    iface = FakeInterface()
    plugin = ASNIP(iface)

    # Ensure threads can start and stop quickly
    plugin.start()
    # allow threads to spin up
    time.sleep(0.1)
    plugin.stop(timeout=1.0)

    # threads should be stopped (either None or not alive)
    bt = plugin.broadcast_thread
    qt = plugin.queue_processor_thread
    assert bt is None or not bt.is_alive()
    assert qt is None or not qt.is_alive()
