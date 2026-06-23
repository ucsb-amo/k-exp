import sys
import time
import logging
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QGroupBox, 
                             QMessageBox, QFrame, QDialog, QFormLayout,
                             QDialogButtonBox, QDoubleSpinBox)
from PyQt6.QtCore import QTimer, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QPalette, QColor, QIcon, QPixmap, QPainter, QBrush, QPen
from kexp.control.ethernet_relay import (EthernetRelay, SOURCE_RELAY_IDX,
                                          MAGNET_INHIBIT_IDX,
                                          ARTIQ_RESTART_TIME_S,
                                          ARTIQ_SATELLITE_MAIN_RESTART_OFFSET_S)

logger = logging.getLogger("kexp.dashboard.client.ethernet_relay")


class ArtiqRestartSettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ARTIQ Restart Settings")
        self.setModal(True)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.satellite_wait_input = self._create_time_input(
            settings['satellite_wait_s']
        )
        self.main_wait_input = self._create_time_input(
            settings['main_wait_s']
        )
        self.sequence_delay_input = self._create_time_input(
            settings['between_s']
        )

        form_layout.addRow("Satellite restart wait", self.satellite_wait_input)
        form_layout.addRow("Main restart wait", self.main_wait_input)
        form_layout.addRow("Satellite to main delay", self.sequence_delay_input)
        layout.addLayout(form_layout)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _create_time_input(self, value):
        input_box = QDoubleSpinBox()
        input_box.setDecimals(2)
        input_box.setRange(0.0, 60.0)
        input_box.setSingleStep(0.25)
        input_box.setSuffix(" s")
        input_box.setValue(value)
        return input_box

    def get_settings(self):
        return {
            'satellite_wait_s': self.satellite_wait_input.value(),
            'main_wait_s': self.main_wait_input.value(),
            'between_s': self.sequence_delay_input.value(),
        }

class RelayWorker(QThread):
    """Worker thread to handle relay operations without blocking the GUI"""
    finished = pyqtSignal(list)  # Signal to emit when operation is complete
    error = pyqtSignal(str)  # Signal to emit on error
    
    def __init__(self, relay: EthernetRelay, operation, settings=None):
        super().__init__()
        self.relay = relay
        self.operation = operation
        self.settings = settings or {}
        
    def run(self):
        try:
            if self.operation == 'source_on':
                self.relay.source_on()
            elif self.operation == 'source_off':
                self.relay.source_off()
            elif self.operation == 'toggle_artiq':
                self.relay.restart_artiq(
                    t_wait=self.settings['satellite_wait_s'],
                    t_between=self.settings['between_s']
                )
            elif self.operation == 'toggle_artiq_main':
                self.relay.toggle_artiq_main_power(
                    t_wait=self.settings['main_wait_s']
                )
            elif self.operation == 'toggle_artiq_satellites':
                self.relay.toggle_artiq_satellites_power(
                    t_wait=self.settings['satellite_wait_s']
                )
            elif self.operation == 'magnet_off':
                self.relay.kill_magnets()
            elif self.operation == 'magnet_on':
                self.relay.enable_magnets()
            elif self.operation == 'read_status':
                status = self.relay.read_relay_status()
                self.finished.emit(status)
                return
            
            self.finished.emit([True])
        except Exception as e:
            self.error.emit(str(e))

class EthernetRelayGUI(QMainWindow):
    BUTTON_HEIGHT = 22
    BUTTON_MIN_WIDTH = 70
    SUB_BUTTON_MIN_WIDTH = 62
    STATUS_MIN_WIDTH = 62
    SETTINGS_BUTTON_SIZE = 20

    def __init__(self):
        super().__init__()
        self.relay = EthernetRelay()
        self.source_status = False
        self.magnet_status = False
        self.operation_in_progress = False
        self.artiq_restart_settings = {
            'satellite_wait_s': ARTIQ_RESTART_TIME_S,
            'main_wait_s': ARTIQ_RESTART_TIME_S,
            'between_s': ARTIQ_SATELLITE_MAIN_RESTART_OFFSET_S,
        }
        self.init_ui()

        # Timer for periodic status updates
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(5000)  # Update every 5 seconds
        
        # Initial status check
        self.update_status()
    
    def create_ethernet_icon(self):
        """Create a simple ethernet connector icon"""
        size = 64
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw ethernet connector outline
        pen = QPen(QColor("#2196F3"), 2)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor("#E3F2FD")))
        
        # Main connector body (rectangle)
        painter.drawRect(12, 20, 40, 20)
        
        # Draw 4 pins/connectors at bottom
        pin_positions = [18, 26, 34, 42]
        for x in pin_positions:
            painter.drawRect(x - 2, 40, 4, 8)
        
        # Draw ethernet cable (curved lines from sides)
        cable_pen = QPen(QColor("#1976D2"), 1.5)
        painter.setPen(cable_pen)
        painter.drawLine(10, 30, 5, 45)  # Left cable
        painter.drawLine(54, 30, 59, 45)  # Right cable
        
        painter.end()
        return QIcon(pixmap)

    def artiq_button_style(self, muted=False):
        if muted:
            return """
                QPushButton {
                    background-color: #d59a4d;
                    color: white;
                    border: none;
                    padding: 4px 8px;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #c88b3d;
                }
                QPushButton:pressed {
                    background-color: #b57724;
                }
                QPushButton:disabled {
                    background-color: #cccccc;
                    color: #666666;
                }
            """

        return """
            QPushButton {
                background-color: #FF9800;
                color: white;
                border: none;
                padding: 4px 10px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
            QPushButton:pressed {
                background-color: #EF6C00;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """
        
    def init_ui(self):
        self.setWindowTitle("Ethernet Relay Control")
        self.setWindowIcon(self.create_ethernet_icon())
        self.setGeometry(100, 100, 100, 300)
        
        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)
        
        # Source Control Group
        source_group = QGroupBox("Source Control")
        source_layout = QVBoxLayout(source_group)
        
        # Status display
        status_layout = QHBoxLayout()
        status_label = QLabel("Source Status:")
        status_label.setFont(QFont("Arial", 10))
        self.status_indicator = QLabel("UNKNOWN")
        self.status_indicator.setFont(QFont("Arial", 10))
        self.status_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_indicator.setMinimumWidth(self.STATUS_MIN_WIDTH)
        self.status_indicator.setFrameStyle(QFrame.Shape.Box)
        self.status_indicator.setStyleSheet("padding: 3px 5px; border: 2px solid gray; border-radius: 5px;")
        
        status_layout.addWidget(status_label)
        status_layout.addWidget(self.status_indicator)
        status_layout.addStretch()
        
        # Control buttons
        button_layout = QHBoxLayout()
        
        self.toggle_btn = QPushButton("Turn Source OFF")
        self.toggle_btn.setFont(QFont("Arial", 10))
        self.toggle_btn.setMinimumHeight(self.BUTTON_HEIGHT)
        self.toggle_btn.setMinimumWidth(self.BUTTON_MIN_WIDTH)
        self.update_toggle_button_style()
        self.toggle_btn.clicked.connect(self.toggle_source)
        
        button_layout.addWidget(self.toggle_btn)
        
        source_layout.addLayout(status_layout)
        source_layout.addLayout(button_layout)
        
        # Magnet Inhibit Control Group
        magnet_group = QGroupBox("Magnet Enable Status")
        magnet_layout = QVBoxLayout(magnet_group)
        
        # Combined status display and control button
        self.magnet_status_btn = QPushButton("UNKNOWN")
        self.magnet_status_btn.setFont(QFont("Arial", 10))
        self.magnet_status_btn.setMinimumHeight(self.BUTTON_HEIGHT)
        self.magnet_status_btn.setMinimumWidth(self.BUTTON_MIN_WIDTH)
        self.magnet_status_btn.clicked.connect(self.toggle_magnet)
        self.update_magnet_status_button()
        
        magnet_layout.addWidget(self.magnet_status_btn)
        
        # ARTIQ Control Group
        artiq_group = QGroupBox("ARTIQ Control")
        artiq_layout = QVBoxLayout(artiq_group)
        self.artiq_settings_btn = QPushButton("⚙")
        self.artiq_settings_btn.setFont(QFont("Segoe UI Emoji", 10))
        self.artiq_settings_btn.setFixedSize(self.SETTINGS_BUTTON_SIZE, self.SETTINGS_BUTTON_SIZE)
        self.artiq_settings_btn.setToolTip("Configure ARTIQ restart timing")
        self.artiq_settings_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #c8c8c8;
                border-radius: 14px;
                padding-bottom: 1px;
            }
            QPushButton:hover {
                background-color: #e5e5e5;
            }
            QPushButton:pressed {
                background-color: #d8d8d8;
            }
            QPushButton:disabled {
                background-color: #f4f4f4;
                border-color: #dddddd;
            }
        """)
        self.artiq_settings_btn.clicked.connect(self.open_artiq_settings)
        
        self.artiq_restart_btn = QPushButton("Restart ARTIQ")
        self.artiq_restart_btn.setFont(QFont("Arial", 10))
        self.artiq_restart_btn.setMinimumHeight(self.BUTTON_HEIGHT)
        self.artiq_restart_btn.setMinimumWidth(self.BUTTON_MIN_WIDTH)
        self.artiq_restart_btn.setStyleSheet(self.artiq_button_style())
        self.artiq_restart_btn.clicked.connect(self.restart_artiq)
        
        artiq_layout.addWidget(self.artiq_restart_btn)

        artiq_subcontrols_layout = QHBoxLayout()

        self.artiq_satellites_restart_btn = QPushButton("Satellites")
        self.artiq_satellites_restart_btn.setFont(QFont("Arial", 9))
        self.artiq_satellites_restart_btn.setMinimumHeight(self.BUTTON_HEIGHT)
        self.artiq_satellites_restart_btn.setMinimumWidth(self.SUB_BUTTON_MIN_WIDTH)
        self.artiq_satellites_restart_btn.setStyleSheet(self.artiq_button_style(muted=True))
        self.artiq_satellites_restart_btn.clicked.connect(self.restart_artiq_satellites)

        self.artiq_main_restart_btn = QPushButton("Main")
        self.artiq_main_restart_btn.setFont(QFont("Arial", 9))
        self.artiq_main_restart_btn.setMinimumHeight(self.BUTTON_HEIGHT)
        self.artiq_main_restart_btn.setMinimumWidth(self.SUB_BUTTON_MIN_WIDTH)
        self.artiq_main_restart_btn.setStyleSheet(self.artiq_button_style(muted=True))
        self.artiq_main_restart_btn.clicked.connect(self.restart_artiq_main)

        artiq_subcontrols_layout.addWidget(self.artiq_satellites_restart_btn)
        artiq_subcontrols_layout.addWidget(self.artiq_settings_btn, alignment=Qt.AlignmentFlag.AlignVCenter)
        artiq_subcontrols_layout.addWidget(self.artiq_main_restart_btn)
        artiq_layout.addLayout(artiq_subcontrols_layout)
        
        # Refresh button
        self.refresh_btn = QPushButton("Refresh Status")
        self.refresh_btn.setFont(QFont("Arial", 9))
        self.refresh_btn.setMinimumHeight(self.BUTTON_HEIGHT)
        self.refresh_btn.setMinimumWidth(self.BUTTON_MIN_WIDTH)
        self.refresh_btn.clicked.connect(self.update_status)
        
        # Stack all groups vertically so the magnet enable status sits in
        # the same column as the source + ARTIQ controls.
        main_layout.addWidget(source_group)
        main_layout.addWidget(magnet_group)
        main_layout.addWidget(artiq_group)
        main_layout.addWidget(self.refresh_btn)
        main_layout.addStretch()
        
    def update_toggle_button_style(self):
        """Update the toggle button style based on current source status"""
        if self.source_status:
            # Source is ON - button should show "Turn OFF" and be red
            self.toggle_btn.setText("Turn Source OFF")
            self.toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #801b1b;
                    color: white;
                    border: none;
                    padding: 4px 8px;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #941e1e;
                }
                QPushButton:pressed {
                    background-color: #5c1313;
                }
                QPushButton:disabled {
                    background-color: #cccccc;
                    color: #666666;
                }
            """)
        else:
            # Source is OFF - button should show "Turn ON" and be green
            self.toggle_btn.setText("Turn Source ON")
            self.toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #598759;
                    color: white;
                    border: none;
                    padding: 4px 8px;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #609660;
                }
                QPushButton:pressed {
                    background-color: #335233;
                }
                QPushButton:disabled {
                    background-color: #cccccc;
                    color: #666666;
                }
            """)
        
    def update_status_indicator(self, is_on):
        """Update the visual status indicator"""
        # Only update if status has changed
        if is_on == self.source_status:
            return
            
        if is_on:
            self.status_indicator.setText("ON")
            self.status_indicator.setStyleSheet("""
                QLabel {
                    background-color: #4CAF50;
                    color: white;
                    padding: 3px 5px;
                    border: 2px solid #4CAF50;
                    border-radius: 5px;
                    font-weight: bold;
                }
            """)
        else:
            self.status_indicator.setText("OFF")
            self.status_indicator.setStyleSheet("""
                QLabel {
                    background-color: #f44336;
                    color: white;
                    padding: 3px 5px;
                    border: 2px solid #f44336;
                    border-radius: 5px;
                    font-weight: bold;
                }
            """)
        
        self.source_status = is_on
        self.update_toggle_button_style()
        
    def update_magnet_status_button(self, is_on=None):
        """Update the magnet status button display and style"""
        # Only update if status has changed
        if is_on is not None and is_on == self.magnet_status:
            return
            
        if is_on is not None:
            self.magnet_status = is_on
            
        if self.magnet_status:
            # Magnet is ON - show gray
            self.magnet_status_btn.setText("ON")
            self.magnet_status_btn.setStyleSheet("""
                QPushButton {
                    background-color: #757575;
                    color: white;
                    border: none;
                    padding: 4px 8px;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #616161;
                }
                QPushButton:pressed {
                    background-color: #424242;
                }
                QPushButton:disabled {
                    background-color: #cccccc;
                    color: #666666;
                }
            """)
        else:
            # Magnet is OFF - show muted red with "INH - Reset?" text
            self.magnet_status_btn.setText("INH - Reset?")
            self.magnet_status_btn.setStyleSheet("""
                QPushButton {
                    background-color: #c62828;
                    color: white;
                    border: none;
                    padding: 4px 8px;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #b71c1c;
                }
                QPushButton:pressed {
                    background-color: #8e0000;
                }
                QPushButton:disabled {
                    background-color: #cccccc;
                    color: #666666;
                }
            """)
        
    def update_status(self):
        """Update the source and magnet status"""
        # Don't check status if an operation is in progress
        if self.operation_in_progress:
            return
        
        # Use worker thread to check status
        self.status_worker = RelayWorker(self.relay, 'read_status')
        self.status_worker.finished.connect(self.on_status_updated)
        self.status_worker.error.connect(self.on_error)
        self.status_worker.start()
        
    def on_status_updated(self, status):
        """Handle status update completion"""
        # status is a list of 4 booleans for the 4 relays
        # Extract source and magnet status using 1-indexed relay numbers
        source_status = status[SOURCE_RELAY_IDX - 1]
        magnet_status = status[MAGNET_INHIBIT_IDX - 1]
        
        self.update_status_indicator(source_status)
        self.update_magnet_status_button(magnet_status)
        
    def toggle_source(self):
        """Toggle the source on or off based on current status"""
        self.operation_in_progress = True
        self.set_buttons_enabled(False)
        
        # Determine operation based on current status
        if self.source_status:
            operation = 'source_off'
        else:
            operation = 'source_on'
            
        self.worker = RelayWorker(self.relay, operation)
        self.worker.finished.connect(self.on_operation_complete)
        self.worker.error.connect(self.on_error)
        self.worker.start()
        
    def toggle_magnet(self):
        """Toggle the magnet inhibit on or off based on current status"""
        self.operation_in_progress = True
        self.set_buttons_enabled(False)
        
        # Determine operation based on current status
        if self.magnet_status:
            operation = 'magnet_off'
        else:
            operation = 'magnet_on'
            
        self.worker = RelayWorker(self.relay, operation)
        self.worker.finished.connect(self.on_operation_complete)
        self.worker.error.connect(self.on_error)
        self.worker.start()
        
    def restart_artiq(self):
        """Restart ARTIQ with confirmation dialog"""
        reply = QMessageBox.question(
            self, 
            'Confirm ARTIQ Restart',
            'Are you sure you want to restart ARTIQ?\n\nThis will interrupt any running experiments.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.operation_in_progress = True
            self.set_buttons_enabled(False)
            self.artiq_restart_btn.setText("Restarting ARTIQ...")
            
            self.worker = RelayWorker(
                self.relay,
                'toggle_artiq',
                settings=self.artiq_restart_settings.copy()
            )
            self.worker.finished.connect(self.on_artiq_restart_complete)
            self.worker.error.connect(self.on_error)
            self.worker.start()

    def restart_artiq_main(self):
        """Restart only the ARTIQ main crate."""
        reply = QMessageBox.question(
            self,
            'Confirm Main Restart',
            'Restart only the ARTIQ main crate?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.operation_in_progress = True
            self.set_buttons_enabled(False)
            self.artiq_main_restart_btn.setText("Restarting Main...")

            self.worker = RelayWorker(
                self.relay,
                'toggle_artiq_main',
                settings=self.artiq_restart_settings.copy()
            )
            self.worker.finished.connect(self.on_artiq_main_restart_complete)
            self.worker.error.connect(self.on_error)
            self.worker.start()

    def restart_artiq_satellites(self):
        """Restart only the ARTIQ satellite crates."""
        reply = QMessageBox.question(
            self,
            'Confirm Satellite Restart',
            'Restart only the ARTIQ satellite crates?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.operation_in_progress = True
            self.set_buttons_enabled(False)
            self.artiq_satellites_restart_btn.setText("Restarting Satellites...")

            self.worker = RelayWorker(
                self.relay,
                'toggle_artiq_satellites',
                settings=self.artiq_restart_settings.copy()
            )
            self.worker.finished.connect(self.on_artiq_satellites_restart_complete)
            self.worker.error.connect(self.on_error)
            self.worker.start()

    def open_artiq_settings(self):
        """Open the ARTIQ restart timing settings panel."""
        dialog = ArtiqRestartSettingsDialog(self.artiq_restart_settings, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.artiq_restart_settings = dialog.get_settings()
            
    def on_operation_complete(self, success):
        """Handle completion of source on/off operations"""
        self.operation_in_progress = False
        if success:
            # Update status after a short delay to see the change
            QTimer.singleShot(1000, self.update_status)
            self.set_buttons_enabled(True)
        else:
            self.set_buttons_enabled(True)
            logger.warning("The relay operation failed.")
            
    def on_artiq_restart_complete(self, success):
        """Handle completion of ARTIQ restart"""
        self.operation_in_progress = False
        self.artiq_restart_btn.setText("Restart ARTIQ")
        self.set_buttons_enabled(True)
        if success:
            QTimer.singleShot(1000, self.update_status)

    def on_artiq_main_restart_complete(self, success):
        """Handle completion of main crate restart."""
        self.operation_in_progress = False
        self.artiq_main_restart_btn.setText("Main")
        self.set_buttons_enabled(True)
        if success:
            QTimer.singleShot(1000, self.update_status)

    def on_artiq_satellites_restart_complete(self, success):
        """Handle completion of satellite crate restart."""
        self.operation_in_progress = False
        self.artiq_satellites_restart_btn.setText("Satellites")
        self.set_buttons_enabled(True)
        if success:
            QTimer.singleShot(1000, self.update_status)
        
        # if success:
        #     QMessageBox.information(self, "ARTIQ Restart", "ARTIQ restart command completed successfully.")
        # else:
        #     QMessageBox.warning(self, "ARTIQ Restart Failed", "The ARTIQ restart operation failed.")
            
    def on_error(self, error_message):
        """Handle errors from worker threads"""
        self.operation_in_progress = False
        self.set_buttons_enabled(True)
        self.artiq_restart_btn.setText("Restart ARTIQ")
        self.status_indicator.setText("ERROR")
        self.status_indicator.setStyleSheet("""
            QLabel {
                background-color: #9C27B0;
                color: white;
                padding: 5px;
                border: 2px solid #9C27B0;
                border-radius: 5px;
                font-weight: bold;
            }
        """)
        
        logger.error("Relay operation failed: %s", error_message)
        
    def set_buttons_enabled(self, enabled):
        """Enable or disable all buttons"""
        self.toggle_btn.setEnabled(enabled)
        self.magnet_status_btn.setEnabled(enabled)
        self.artiq_restart_btn.setEnabled(enabled)
        self.artiq_main_restart_btn.setEnabled(enabled)
        self.artiq_satellites_restart_btn.setEnabled(enabled)
        self.artiq_settings_btn.setEnabled(enabled)
        self.refresh_btn.setEnabled(enabled)
        
    def closeEvent(self, event):
        """Handle window close event"""
        # Stop the timer
        if hasattr(self, 'status_timer'):
            self.status_timer.stop()
            
        # Wait for any running workers to complete
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()
            
        if hasattr(self, 'status_worker') and self.status_worker.isRunning():
            self.status_worker.terminate()
            self.status_worker.wait()
            
        event.accept()


def main():
    
    from waxx.util.dashboard.logging_setup import configure_client_logging
    configure_client_logging()

    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('weldlab.kexp.gui.ethernet_relay')
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle('Windows')
    
    # Create and show the GUI
    gui = EthernetRelayGUI()
    gui.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
