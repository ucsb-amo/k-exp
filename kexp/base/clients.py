from waxx.base import Monitor
from kexp.config.ip import MONITOR_SERVER_IP, MONITOR_STATE_FILEPATH

from waxx.util.guis.HMR_magnetometer.hmr_magnetometer_client import HMRClient
from kexp.config.ip import MAGNETOMETER_SERVER_IP, MAGNETOMETER_SERVER_PORT

class Clients():
    def __init__(self):
        self.monitor = Monitor(self,
                        monitor_server_ip=MONITOR_SERVER_IP,
                        device_state_json_path=MONITOR_STATE_FILEPATH)
        
        self.magnetometer = HMRClient(MAGNETOMETER_SERVER_IP,
                                       MAGNETOMETER_SERVER_PORT)