import sys
from PyQt6.QtWidgets import QApplication

from waxx.util.guis.device_control_gui import DeviceStateGUI

from kexp.config.ip import MONITOR_SERVER_IP, MONITOR_SERVER_PORT, MONITOR_STATE_FILEPATH

from kexp import dds_frame
from kexp.config.dac_id import dac_frame
from kexp.config.expt_params import ExptParams

def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle('Fusion')

    p = ExptParams()
    dac = dac_frame(expt_params=p)
    dds = dds_frame(dac_frame_obj=dac,
                    expt_params=p)
    
    # Create and show main window
    window = DeviceStateGUI(monitor_server_ip=MONITOR_SERVER_IP,
                            monitor_server_port=MONITOR_SERVER_PORT,
                            device_state_json_path=MONITOR_STATE_FILEPATH,
                            dds_frame=dds,
                            dac_frame=dac)
    window.show()
    
    # Run application
    sys.exit(app.exec())

if __name__ == "__main__":
    main()