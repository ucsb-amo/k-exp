import sys
from PyQt6.QtWidgets import QApplication

from waxx.util.guis.mot_viewer.mot_viewer import BaslerCameraViewer

mot_basler_serial = "40277706"

def main():
    app = QApplication(sys.argv)
    viewer = BaslerCameraViewer(mot_basler_serial)
    viewer.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
