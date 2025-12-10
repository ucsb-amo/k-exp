import sys
from PyQt6.QtWidgets import QApplication

from waxx.util.guis.monitor_server_gui import MonitorServerGUI

from kexp.config.monitor_config import MONITOR_SERVER_IP, MONITOR_SERVER_PORT, MONITOR_EXPT_PATH

def main():
    app = QApplication(sys.argv)
    gui = MonitorServerGUI(monitor_server_ip=MONITOR_SERVER_IP,
                           monitor_server_port=MONITOR_SERVER_PORT,
                           monitor_expt_path=MONITOR_EXPT_PATH)
    gui.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()