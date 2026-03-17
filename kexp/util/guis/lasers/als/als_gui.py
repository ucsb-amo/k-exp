import sys
from PyQt6.QtWidgets import QApplication
from waxx.util.guis.als.als_control_gui import ALSControlGUI

from kexp.config.ip import ALS_SERVER_IP, ALS_SERVER_PORT

def main():
    """Launch the remote ALS GUI frontend."""
    app = QApplication(sys.argv)

    gui = ALSControlGUI(
        ip=ALS_SERVER_IP,
        port=ALS_SERVER_PORT,
    )
    gui.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()