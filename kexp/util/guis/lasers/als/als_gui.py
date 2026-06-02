import sys
from PyQt6.QtWidgets import QApplication
from waxx.util.guis.als.als_control_gui import ALSControlGUI

def main():
    """Launch the remote ALS GUI frontend."""
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('weldlab.kexp.gui.als_control')
    app = QApplication(sys.argv)

    gui = ALSControlGUI()
    gui.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()