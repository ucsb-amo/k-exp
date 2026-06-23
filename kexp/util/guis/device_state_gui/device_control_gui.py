import sys
from PyQt6.QtWidgets import QApplication

from waxx.util.guis.device_control_gui import DeviceStateGUI

from kexp.config.dds_id import dds_frame, dac_frame

def main():
    """Main application entry point"""
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('weldlab.kexp.gui.device_control')
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle('Fusion')
    
    dac = dac_frame()
    dds = dds_frame(dac_frame_obj=dac)
    # Create and show main window
    window = DeviceStateGUI(dds_frame=dds,
                            dac_frame=dac)
    window.show()
    
    # Run application
    sys.exit(app.exec())

if __name__ == "__main__":
    main()