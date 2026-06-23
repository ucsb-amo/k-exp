"""
PyQt6 GUI for K-Exp Remote Control
Polls Gmail for SMS/email commands, shows poll status, logs, and whitelist editor.
"""

import logging
import sys
import threading

from waxx.util.guis.als.als_gui_client import ALSGuiClient
from waxx.util.guis.precilaser.precilaser_gui_client import PrecilaserGuiClient

from PyQt6.QtCore import QObject, QThread, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dark mode stylesheet
# ---------------------------------------------------------------------------

_DARK_STYLESHEET = """
QWidget {
    background-color: #2b2b2b;
    color: #e0e0e0;
}
QGroupBox {
    border: 1px solid #555;
    border-radius: 4px;
    margin-top: 14px;
    color: #e0e0e0;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 2px 6px;
}
QGroupBox[title=""] {
    border: none;
    margin-top: 0;
}
QPushButton {
    background-color: #444;
    color: #e0e0e0;
    border: 1px solid #666;
    border-radius: 4px;
    padding: 3px 8px;
}
QPushButton:hover {
    background-color: #555;
}
QPushButton:pressed {
    background-color: #333;
}
QPushButton:disabled {
    background-color: #383838;
    color: #888;
    border-color: #555;
}
QPlainTextEdit {
    background-color: #1e1e1e;
    color: #d4d4d4;
    border: 1px solid #555;
}
QTableWidget {
    background-color: #1e1e1e;
    color: #e0e0e0;
    gridline-color: #444;
}
QTableWidget::item:selected {
    background-color: #3a5a8a;
}
QHeaderView::section {
    background-color: #3c3c3c;
    color: #e0e0e0;
    border: 1px solid #555;
    padding: 2px 4px;
}
QDialog {
    background-color: #2b2b2b;
}
QLabel {
    color: #e0e0e0;
}
QLineEdit {
    background-color: #1e1e1e;
    color: #e0e0e0;
    border: 1px solid #555;
    border-radius: 3px;
    padding: 2px 4px;
}
QScrollBar:vertical {
    background: #2b2b2b;
    width: 10px;
    border: none;
}
QScrollBar::handle:vertical {
    background: #555;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background: #2b2b2b;
    height: 10px;
    border: none;
}
QScrollBar::handle:horizontal {
    background: #555;
    border-radius: 4px;
    min-width: 20px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}
QDialogButtonBox QPushButton {
    min-width: 60px;
}
"""


# ---------------------------------------------------------------------------
# Logging bridge: Python logging → Qt signal → QPlainTextEdit
# ---------------------------------------------------------------------------

class LogEmitter(QObject):
    message_logged = pyqtSignal(str)


class QtLogHandler(logging.Handler):
    def __init__(self, emitter: LogEmitter):
        super().__init__()
        self.emitter = emitter

    def emit(self, record: logging.LogRecord):
        self.emitter.message_logged.emit(self.format(record))


# ---------------------------------------------------------------------------
# Background polling thread
# ---------------------------------------------------------------------------

class PollingThread(QThread):
    """Runs the email-polling loop in a background thread and emits status signals."""

    poll_completed = pyqtSignal(bool)   # True = success, False = error

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._stop_requested = False

    def run(self):
        self._stop_requested = False
        self._controller.run_continuous(
            on_poll_complete=self._on_poll,
            stop_flag=lambda: self._stop_requested,
        )

    def _on_poll(self, success: bool):
        self.poll_completed.emit(success)

    def stop(self):
        self._stop_requested = True


# ---------------------------------------------------------------------------
# Whitelist editor dialog
# ---------------------------------------------------------------------------

class WhitelistEditor(QDialog):
    """Dialog for viewing and editing the phone/email whitelist."""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self._controller = controller
        self.setWindowTitle("Edit Whitelist")
        self.setMinimumSize(420, 400)
        self._build_ui()
        self._populate()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        info = QLabel(
            "Phones (10 digits) and email addresses that are allowed to send commands."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Type", "Value", "Label"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked | QTableWidget.EditTrigger.SelectedClicked)
        layout.addWidget(self._table)

        btn_row = QHBoxLayout()
        self._add_btn = QPushButton("Add…")
        self._remove_btn = QPushButton("Remove selected")
        btn_row.addWidget(self._add_btn)
        btn_row.addWidget(self._remove_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        layout.addWidget(buttons)

        self._add_btn.clicked.connect(self._add_entry)
        self._remove_btn.clicked.connect(self._remove_entry)
        self._table.cellChanged.connect(self._on_cell_changed)
        buttons.rejected.connect(self.accept)

    def _populate(self):
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        eh = self._controller.email_handler
        labels = getattr(self._controller, '_labels', {})
        rows = []
        for phone in sorted(eh.phone_whitelist):
            rows.append(("phone", phone, labels.get(phone, "")))
        for addr in sorted(eh.whitelist):
            if not addr.endswith("@txt.voice.google.com"):
                rows.append(("email", addr, labels.get(addr, "")))
        for kind, value, label in rows:
            row = self._table.rowCount()
            self._table.insertRow(row)
            type_item = QTableWidgetItem(kind)
            type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            value_item = QTableWidgetItem(value)
            value_item.setFlags(value_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            label_item = QTableWidgetItem(label)
            self._table.setItem(row, 0, type_item)
            self._table.setItem(row, 1, value_item)
            self._table.setItem(row, 2, label_item)
        self._table.blockSignals(False)

    def _on_cell_changed(self, row: int, col: int):
        if col != 2:
            return
        value_item = self._table.item(row, 1)
        label_item = self._table.item(row, 2)
        if value_item is None or label_item is None:
            return
        self._controller._labels[value_item.text()] = label_item.text().strip()
        self._controller.save_whitelist_to_file()

    def _add_entry(self):
        text, ok = QInputDialog.getText(
            self, "Add entry", "Enter a 10-digit phone number or email address:"
        )
        if not ok or not text.strip():
            return
        self._controller.add_to_whitelist(text.strip())
        self._controller.save_whitelist_to_file()
        self._populate()

    def _remove_entry(self):
        row = self._table.currentRow()
        if row < 0:
            return
        kind_item  = self._table.item(row, 0)
        value_item = self._table.item(row, 1)
        if kind_item is None or value_item is None:
            return
        kind  = kind_item.text()
        value = value_item.text()
        eh = self._controller.email_handler

        if kind == "phone":
            if value in eh.phone_whitelist:
                eh.phone_whitelist.remove(value)
            self._controller._labels.pop(value, None)
            from kexp.util.remote_control.email_handler import GVOICE_NUMBER
            gv_email = f"1{GVOICE_NUMBER}.1{value}.placeholder@txt.voice.google.com"
            if gv_email in eh.whitelist:
                eh.whitelist.remove(gv_email)
        elif kind == "email":
            lc = [a.lower() for a in eh.whitelist]
            if value.lower() in lc:
                eh.whitelist.pop(lc.index(value.lower()))
            self._controller._labels.pop(value, None)

        self._controller.save_whitelist_to_file()
        self._populate()


# ---------------------------------------------------------------------------
# Server connection status button  (click = toggle connect/disconnect)
# ---------------------------------------------------------------------------

class ServerStatusButton(QPushButton):
    """
    Button that reflects and toggles the serial-connection state of a
    remote laser server (ALS or Precilaser).

    Pass ``controller`` and ``attr_name`` (e.g. 'als_client') so that a
    successful re-discovery updates the shared client reference used by the
    command handlers too.

    - Green  = server reachable AND serial connected → click disconnects serial.
    - Orange = server reachable but serial not open   → click connects serial.
    - Red    = server not reachable (offline / not started) → click retries discovery.

    All blocking network calls (UDP discovery, TCP snapshot) run in a
    daemon thread so the UI is never frozen.
    """

    _STYLE_CONNECTED    = "background-color: #2ba363; color: white; border-radius: 4px; padding: 2px 6px; font-weight: 700;"
    _STYLE_DISCONNECTED = "background-color: #c87c1a; color: white; border-radius: 4px; padding: 2px 6px; font-weight: 700;"
    _STYLE_OFFLINE      = "background-color: #d03f37; color: white; border-radius: 4px; padding: 2px 6px; font-weight: 700;"

    # Signals must be class-level for PyQt6
    _poll_result  = pyqtSignal(str)   # "CONNECTED" | "DISCONNECTED" | "OFFLINE"
    _client_ready = pyqtSignal(object)  # new client instance, or None on failure

    def __init__(self, label: str, controller, attr_name: str,
                 client_factory, poll_interval_ms: int = 3000, parent=None):
        super().__init__(parent)
        self._label        = label
        self._controller   = controller
        self._attr_name    = attr_name
        self._factory      = client_factory   # () -> client; may block (UDP discovery)
        self._discovering  = False
        self._connection_state = "OFFLINE"

        self._poll_result.connect(self._on_poll_result)
        self._client_ready.connect(self._on_client_ready)
        self.clicked.connect(self._on_click)

        self._apply_state()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._start_poll)
        self._timer.start(poll_interval_ms)
        QTimer.singleShot(0, self._start_poll)   # immediate first probe

    # --- client property (shared with controller) ---

    @property
    def _client(self):
        return getattr(self._controller, self._attr_name)

    @_client.setter
    def _client(self, val):
        setattr(self._controller, self._attr_name, val)

    # --- background workers ---

    def _start_poll(self):
        """Kick off a background poll (non-blocking)."""
        client = self._client
        if client is None:
            # No client yet — attempt discovery
            if not self._discovering:
                self._discovering = True
                threading.Thread(target=self._discover_worker, daemon=True).start()
            return
        threading.Thread(target=self._poll_worker, args=(client,), daemon=True).start()

    def _poll_worker(self, client):
        """Runs in daemon thread: fetch snapshot and emit result."""
        try:
            snapshot = client.get_snapshot()
            state = str(
                snapshot.get("status", {}).get("connection_state", "DISCONNECTED")
            ).upper()
            self._poll_result.emit(state if state in ("CONNECTED", "DISCONNECTED") else "DISCONNECTED")
        except Exception:
            # Server went offline after being discovered — clear the client so
            # the next poll triggers re-discovery.
            self._client = None
            self._poll_result.emit("OFFLINE")

    def _discover_worker(self):
        """Runs in daemon thread: try to construct the client via UDP discovery."""
        try:
            new_client = self._factory()
            self._client_ready.emit(new_client)
        except Exception:
            self._client_ready.emit(None)

    # --- signal handlers (main thread) ---

    def _on_poll_result(self, state: str):
        self._connection_state = state
        self._apply_state()

    def _on_client_ready(self, client):
        self._discovering = False
        if client is not None:
            self._client = client
            # Immediately poll with the new client
            threading.Thread(target=self._poll_worker, args=(client,), daemon=True).start()
        # If None, stay OFFLINE; next timer tick will retry

    # --- visual state ---

    def _apply_state(self):
        self.setText(self._label)
        if self._connection_state == "CONNECTED":
            self.setStyleSheet(self._STYLE_CONNECTED)
        elif self._connection_state == "DISCONNECTED":
            self.setStyleSheet(self._STYLE_DISCONNECTED)
        else:
            self.setStyleSheet(self._STYLE_OFFLINE)

    # --- click handler ---

    def _on_click(self):
        if self._connection_state == "OFFLINE":
            # Retry discovery immediately
            if not self._discovering:
                self._discovering = True
                threading.Thread(target=self._discover_worker, daemon=True).start()
            return
        client = self._client
        if client is None:
            return
        try:
            if self._connection_state == "CONNECTED":
                client.disconnect_serial()
            else:
                client.connect_serial()
        except Exception as exc:
            logger.error("%s toggle connection failed: %s", self._label, exc)
        # Refresh state after a short delay
        QTimer.singleShot(400, self._start_poll)


# ---------------------------------------------------------------------------
# Status indicator widget
# ---------------------------------------------------------------------------

_STYLE_GRAY   = "background-color: #888; border-radius: 8px; min-width: 16px; max-width: 16px; min-height: 16px; max-height: 16px;"
_STYLE_GREEN  = "background-color: #2ba363; border-radius: 8px; min-width: 16px; max-width: 16px; min-height: 16px; max-height: 16px;"
_STYLE_RED    = "background-color: #d03f37; border-radius: 8px; min-width: 16px; max-width: 16px; min-height: 16px; max-height: 16px;"


class PollDot(QWidget):
    """Pill-shaped status indicator that updates on each poll."""

    _PILL_GRAY  = "background-color: #666; color: white; border-radius: 8px; padding: 2px 8px;"
    _PILL_GREEN = "background-color: #2ba363; color: white; border-radius: 8px; padding: 2px 8px;"
    _PILL_RED   = "background-color: #d03f37; color: white; border-radius: 8px; padding: 2px 8px;"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pill = QLabel("Waiting…")
        self._pill.setStyleSheet(self._PILL_GRAY)
        self._pill.setAlignment(Qt.AlignmentFlag.AlignCenter)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self._pill)
        row.addStretch()

    def on_poll(self, success: bool):
        if success:
            self._pill.setStyleSheet(self._PILL_GREEN)
            self._pill.setText("Poll OK")
        else:
            self._pill.setStyleSheet(self._PILL_RED)
            self._pill.setText("Poll error")


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class RemoteControlGUI(QMainWindow):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self._controller = controller
        self.setWindowTitle("K-Exp Remote Control")
        self.setMinimumSize(320, 200)

        self._set_window_icon()
        self._build_ui()
        self._setup_logging()
        self._start_polling()

        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(_DARK_STYLESHEET)

        self._apply_dark_titlebar()

    # --- Dark title bar (Windows only) ---

    def _apply_dark_titlebar(self):
        """Use DWM API to enable dark mode on the native Win32 title bar."""
        try:
            import ctypes
            import ctypes.wintypes
            hwnd = int(self.winId())
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            value = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
        except Exception:
            pass  # Non-Windows or unsupported version — silently ignore

    # --- Window icon ---

    def _set_window_icon(self):
        icon = QIcon()
        for size in (16, 24, 32, 48, 64, 128):
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            font = QFont("Segoe UI Emoji")
            font.setPixelSize(int(size * 0.8))
            painter.setFont(font)
            painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "📡")
            painter.end()
            icon.addPixmap(pixmap)
        self.setWindowIcon(icon)
        app = QApplication.instance()
        if app is not None:
            app.setWindowIcon(icon)

    # --- UI construction ---

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # ---- top bar: poll status + server conn badges + whitelist ----
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)
        self._poll_dot = PollDot()
        top.addWidget(self._poll_dot)

        self._als_btn = ServerStatusButton(
            "ALS", self._controller, "als_client",
            client_factory=ALSGuiClient, poll_interval_ms=3000,
        )
        top.addWidget(self._als_btn)

        self._preci_btn = ServerStatusButton(
            "Precilaser", self._controller, "precilaser_client",
            client_factory=PrecilaserGuiClient, poll_interval_ms=3000,
        )
        top.addWidget(self._preci_btn)

        top.addStretch(1)

        whitelist_btn = QPushButton("Edit Whitelist…")
        whitelist_btn.clicked.connect(self._open_whitelist_editor)
        top.addWidget(whitelist_btn)
        main_layout.addLayout(top)

        # ---- All ON / All OFF in a single groupbox row ----
        cmd_group = QGroupBox("Commands")
        cmd_layout = QHBoxLayout(cmd_group)
        cmd_layout.setContentsMargins(6, 4, 6, 4)
        cmd_layout.setSpacing(4)

        all_on_btn = QPushButton("All ON")
        all_on_btn.setStyleSheet(
            "background-color: #888; color: white; font-weight: bold;"
            " border-radius: 4px; padding: 2px 6px;"
        )
        all_on_btn.clicked.connect(self._all_on)
        cmd_layout.addWidget(all_on_btn)

        all_off_btn = QPushButton("All OFF")
        all_off_btn.setStyleSheet(
            "background-color: #888; color: white; font-weight: bold;"
            " border-radius: 4px; padding: 2px 6px;"
        )
        all_off_btn.clicked.connect(self._all_off)
        cmd_layout.addWidget(all_off_btn)

        main_layout.addWidget(cmd_group)

        # ---- log window (collapsed by default) ----
        try:
            from waxx.util.dashboard.widgets import CollapsibleGroupBox  # noqa: PLC0415
            log_group = CollapsibleGroupBox("Log", expanded=True)
            self._log_view = QPlainTextEdit()
            self._log_view.setReadOnly(True)
            self._log_view.setFont(QFont("Courier New", 9))
            self._log_view.setMaximumBlockCount(2000)
            log_group.addWidget(self._log_view)
            main_layout.addWidget(log_group, 1)
        except Exception:
            # Fallback to a plain GroupBox if waxx isn't importable here.
            log_group = QGroupBox("Log")
            log_layout = QVBoxLayout(log_group)
            log_layout.setContentsMargins(4, 4, 4, 4)
            log_layout.setSpacing(2)
            self._log_view = QPlainTextEdit()
            self._log_view.setReadOnly(True)
            self._log_view.setFont(QFont("Courier New", 9))
            self._log_view.setMaximumBlockCount(2000)
            log_layout.addWidget(self._log_view)
            main_layout.addWidget(log_group, 1)

    # --- Logging setup ---

    def _setup_logging(self):
        self._log_emitter = LogEmitter()
        self._log_emitter.message_logged.connect(self._append_log)

        handler = QtLogHandler(self._log_emitter)
        handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
                                               datefmt="%H:%M:%S"))

        # Attach to all remote-control module loggers
        for name in (
            "kexp.util.remote_control.remote_control",
            "kexp.util.remote_control.command_handler",
        ):
            logging.getLogger(name).addHandler(handler)

    def _append_log(self, text: str):
        self._log_view.appendPlainText(text)
        self._log_view.ensureCursorVisible()

    # --- Polling thread ---

    def _start_polling(self):
        self._poll_thread = PollingThread(self._controller, parent=self)
        self._poll_thread.poll_completed.connect(self._poll_dot.on_poll)
        self._poll_thread.start()

    # --- Manual command buttons ---

    def _all_on(self):
        reply = QMessageBox.question(
            self, "Confirm All ON",
            "Turn ON all systems (sources, ALS, Precilaser)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        result = self._controller.handle_all_command("on")
        logger.info(f"[Manual] All ON: {result}")

    def _all_off(self):
        reply = QMessageBox.question(
            self, "Confirm All OFF",
            "Turn OFF all systems (sources, ALS, Precilaser)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        result = self._controller.handle_all_command("off")
        logger.info(f"[Manual] All OFF: {result}")

    # --- Whitelist editor ---

    def _open_whitelist_editor(self):
        dlg = WhitelistEditor(self._controller, parent=self)
        dlg.exec()

    # --- Clean shutdown ---

    def closeEvent(self, event):
        self._poll_thread.stop()
        self._poll_thread.wait(3000)
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Standalone entry point (for direct execution of this module)
# ---------------------------------------------------------------------------

def main():
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
        'weldlab.kexp.gui.remote_control'
    )

    from kexp.util.remote_control.remote_control import RemoteControl

    app = QApplication(sys.argv)
    controller = RemoteControl()
    window = RemoteControlGUI(controller)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
