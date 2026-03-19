import sys

import pyqtgraph as pg
from pyqtgraph.Qt import QtWidgets

from waxx.util.guis.HMR_magnetometer.hmr_magnetometer_server import MagnetometerServer
from kexp.config.ip import (
    MAGNETOMETER_COM,
    MAGNETOMETER_REFERENCE_CSV_PATH,
    MAGNETOMETER_SERVER_IP,
    MAGNETOMETER_SERVER_PORT,
)

DEFAULT_SERIAL_PORT = MAGNETOMETER_COM
DEFAULT_SERVER_HOST = MAGNETOMETER_SERVER_IP
DEFAULT_SERVER_PORT = MAGNETOMETER_SERVER_PORT
DEFAULT_REFERENCE_CSV_PATH = MAGNETOMETER_REFERENCE_CSV_PATH

def main():
    server = MagnetometerServer(
        serial_port=DEFAULT_SERIAL_PORT,
        server_host=MAGNETOMETER_SERVER_IP,
        server_port=MAGNETOMETER_SERVER_PORT,
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
