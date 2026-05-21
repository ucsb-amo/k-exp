from waxx.base import Monitor
import os
from kexp.config.ip import MONITOR_STATE_FILEPATH

from waxx.util.device_state.monitor_controller import MonitorController

from waxx.util.guis.HMR_magnetometer.hmr_magnetometer_client import HMRClient
from kexp.util.live_od.live_od_client import LiveODClient

monitor_controller = MonitorController(MONITOR_STATE_FILEPATH) if os.path.isfile(MONITOR_STATE_FILEPATH) else None

class Clients():
    def __init__(self, suppress_live_od=False):
        try:
            self.monitor = Monitor(self,
                        device_state_json_path=MONITOR_STATE_FILEPATH)
        except Exception as e:
            print(f"Failed to connect to Monitor: {e}")

        self.magnetometer = HMRClient()

        if not suppress_live_od:
            try:
                self.live_od_client = LiveODClient()
            except Exception as e:
                raise RuntimeError(
                    f"[LiveOD] Could not connect to LiveOD server: {e}\n"
                    "Check that the LiveOD server window is running on the control PC.\n"
                    "To run without a LiveOD server, pass suppress_live_od=True "
                    "(and setup_camera=False) to Base.__init__."
                ) from e