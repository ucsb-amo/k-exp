import sys

import pyqtgraph as pg
from pyqtgraph.Qt import QtWidgets

from waxx.util.guis.HMR_magnetometer.hmr_magnetometer_server import MagnetometerServer
from kexp.config.ip import (
    MAGNETOMETER_COM,
    MAGNETOMETER_REFERENCE_CSV_PATH,
)

DEFAULT_SERIAL_PORT = MAGNETOMETER_COM
DEFAULT_REFERENCE_CSV_PATH = MAGNETOMETER_REFERENCE_CSV_PATH

def main():
    server = MagnetometerServer(
        serial_port=DEFAULT_SERIAL_PORT,
        reference_csv_path=DEFAULT_REFERENCE_CSV_PATH,
    )
    try:
        server.run()
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted — shutting down.")
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
