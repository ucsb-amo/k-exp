from waxx.base import Monitor
from kexp.config.ip import MONITOR_SERVER_IP, MONITOR_STATE_FILEPATH

from waxx.util.device_state.monitor_controller import MonitorController

from waxx.util.live_od.camera_client import CameraClient
from kexp.config.ip import CAMERA_SERVER_IP, CAMERA_SERVER_PORT

from waxx.util.guis.HMR_magnetometer.hmr_magnetometer_client import HMRClient
from kexp.config.ip import MAGNETOMETER_SERVER_IP, MAGNETOMETER_SERVER_PORT, MONITOR_STATE_FILEPATH

magnetometer_client = HMRClient(MAGNETOMETER_SERVER_IP,MAGNETOMETER_SERVER_PORT)
monitor_controller = MonitorController(MONITOR_STATE_FILEPATH)

class Clients():
    def __init__(self):
        self.monitor = Monitor(self,
                        monitor_server_ip=MONITOR_SERVER_IP,
                        device_state_json_path=MONITOR_STATE_FILEPATH)
        
        self.live_od_client = CameraClient(CAMERA_SERVER_IP,
                                           CAMERA_SERVER_PORT)
        
        self.magnetometer = magnetometer_client