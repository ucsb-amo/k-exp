from waxx.base import Monitor
import os
from kexp.config.ip import MONITOR_SERVER_IP, MONITOR_STATE_FILEPATH

from waxx.util.device_state.monitor_controller import MonitorController

from waxx.util.guis.HMR_magnetometer.hmr_magnetometer_client import HMRClient
from kexp.config.ip import MAGNETOMETER_SERVER_IP, MAGNETOMETER_SERVER_PORT, MONITOR_STATE_FILEPATH
from kexp.config.ip import LIVEOD_SERVER_IP, LIVEOD_SERVER_PORT
from kexp.util.live_od.live_od_client import LiveODClient

magnetometer_client = HMRClient(MAGNETOMETER_SERVER_IP,MAGNETOMETER_SERVER_PORT)
monitor_controller = MonitorController(MONITOR_STATE_FILEPATH) if os.path.isfile(MONITOR_STATE_FILEPATH) else None

class Clients():
    def __init__(self, suppress_live_od=False):
        self.monitor = Monitor(self,
                        monitor_server_ip=MONITOR_SERVER_IP,
                        device_state_json_path=MONITOR_STATE_FILEPATH)

        self.magnetometer = magnetometer_client

        if not suppress_live_od:
            self.live_od_client = LiveODClient(LIVEOD_SERVER_IP, LIVEOD_SERVER_PORT)