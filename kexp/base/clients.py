from kexp.config.ip import MONITOR_SERVER_IP, MONITOR_STATE_FILEPATH
from waxx.base import Monitor

class Clients():
    def __init__(self):
        self.monitor = Monitor(self,
                        monitor_server_ip=MONITOR_SERVER_IP,
                        device_state_json_path=MONITOR_STATE_FILEPATH)