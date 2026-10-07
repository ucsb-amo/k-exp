import sys

from PyQt6.QtWidgets import QApplication

from waxx.util.guis.precilaser.precilaser_control_gui import PrecilaserControlGUI


def main() -> None:
    """Launch the remote Precilaser GUI frontend."""
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('weldlab.kexp.gui.precilaser')
    from waxa.taskbar import group_console
    group_console()  # console joins the shared terminals taskbar button
    app = QApplication(sys.argv)

    gui = PrecilaserControlGUI()
    gui.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
