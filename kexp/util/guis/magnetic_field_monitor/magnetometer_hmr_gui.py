import sys

import pyqtgraph as pg
from pyqtgraph.Qt import QtWidgets

from waxx.util.guis.HMR_magnetometer.hmr_magnetometer_gui import MagnetometerGUI
from kexp.config.ip import (
    MAGNETOMETER_REFERENCE_CSV_PATH,
    MAGNETOMETER_SERVER_IP,
    MAGNETOMETER_SERVER_PORT,
)

def main():
    app = QtWidgets.QApplication(sys.argv)
    pg.setConfigOptions(antialias=True, background="w", foreground="k")

    window = MagnetometerGUI(server_host=MAGNETOMETER_SERVER_IP,
                              server_port=MAGNETOMETER_SERVER_PORT,
                              reference_csv_path=MAGNETOMETER_REFERENCE_CSV_PATH)
    window.show()

    try:
        return app.exec()
    except Exception:
        window.shutdown()
        raise

if __name__ == "__main__":
    sys.exit(main())