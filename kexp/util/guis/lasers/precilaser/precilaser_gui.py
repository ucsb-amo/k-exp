import sys

from PyQt6.QtWidgets import QApplication

from waxx.util.guis.precilaser.precilaser_control_gui import PrecilaserControlGUI
from kexp.config.ip import PRECILASER_SERVER_IP, PRECILASER_SERVER_PORT


def main() -> None:
    """Launch the remote Precilaser GUI frontend."""
    app = QApplication(sys.argv)

    gui = PrecilaserControlGUI(
        ip=PRECILASER_SERVER_IP,
        port=PRECILASER_SERVER_PORT,
    )
    gui.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
