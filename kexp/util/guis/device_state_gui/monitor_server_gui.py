import sys
from PyQt6.QtWidgets import QApplication

from waxx.util.guis.monitor_server_gui import MonitorServerGUI

from kexp.config.ip import MONITOR_EXPT_PATH

def main():
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('weldlab.kexp.gui.monitor_server')
    app = QApplication(sys.argv)
    app.setStyle('Windows')
    gui = MonitorServerGUI(monitor_expt_path=MONITOR_EXPT_PATH)
    gui.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()