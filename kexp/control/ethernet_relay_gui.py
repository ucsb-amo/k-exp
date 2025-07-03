import sys
import time
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QGroupBox, 
                             QMessageBox, QFrame)
from PyQt6.QtCore import QTimer, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QPalette, QColor
try:
    from .ethernet_relay import EthernetRelay
except ImportError:
    from ethernet_relay import EthernetRelay


class RelayWorker(QThread):
    """Worker thread to handle relay operations without blocking the GUI"""
    finished = pyqtSignal(bool)  # Signal to emit when operation is complete
    error = pyqtSignal(str)  # Signal to emit on error
    
    def __init__(self, relay, operation):
        super().__init__()
        self.relay = relay
        self.operation = operation
        
    def run(self):
        try:
            if self.operation == 'source_on':
                self.relay.source_on()
            elif self.operation == 'source_off':
                self.relay.source_off()
            elif self.operation == 'toggle_artiq':
                self.relay.toggle_artiq_power()
            elif self.operation == 'read_status':
                status = self.relay.read_source_status()
                self.finished.emit(status)
                return
            
            self.finished.emit(True)
        except Exception as e:
            self.error.emit(str(e))


class EthernetRelayGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.relay = EthernetRelay()
        self.source_status = False
        self.init_ui()
        
        # Timer for periodic status updates
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(5000)  # Update every 5 seconds
        
        # Initial status check
        self.update_status()
        
    def init_ui(self):
        self.setWindowTitle("Ethernet Relay Control")
        self.setGeometry(100, 100, 400, 300)
        
        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Source Control Group
        source_group = QGroupBox("Source Control")
        source_layout = QVBoxLayout(source_group)
        
        # Status display
        status_layout = QHBoxLayout()
        status_label = QLabel("Source Status:")
        status_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.status_indicator = QLabel("UNKNOWN")
        self.status_indicator.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.status_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_indicator.setMinimumWidth(100)
        self.status_indicator.setFrameStyle(QFrame.Shape.Box)
        self.status_indicator.setStyleSheet("padding: 5px; border: 2px solid gray; border-radius: 5px;")
        
        status_layout.addWidget(status_label)
        status_layout.addWidget(self.status_indicator)
        status_layout.addStretch()
        
        # Control buttons
        button_layout = QHBoxLayout()
        
        self.source_on_btn = QPushButton("Turn Source ON")
        self.source_on_btn.setFont(QFont("Arial", 11))
        self.source_on_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 10px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.source_on_btn.clicked.connect(self.turn_source_on)
        
        self.source_off_btn = QPushButton("Turn Source OFF")
        self.source_off_btn.setFont(QFont("Arial", 11))
        self.source_off_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                padding: 10px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:pressed {
                background-color: #c11e12;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.source_off_btn.clicked.connect(self.turn_source_off)
        
        button_layout.addWidget(self.source_on_btn)
        button_layout.addWidget(self.source_off_btn)
        
        source_layout.addLayout(status_layout)
        source_layout.addLayout(button_layout)
        
        # ARTIQ Control Group
        artiq_group = QGroupBox("ARTIQ Control")
        artiq_layout = QVBoxLayout(artiq_group)
        
        self.artiq_restart_btn = QPushButton("Restart ARTIQ")
        self.artiq_restart_btn.setFont(QFont("Arial", 11))
        self.artiq_restart_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                border: none;
                padding: 10px;
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
        """)
        self.artiq_restart_btn.clicked.connect(self.restart_artiq)
        
        artiq_layout.addWidget(self.artiq_restart_btn)
        
        # Refresh button
        self.refresh_btn = QPushButton("Refresh Status")
        self.refresh_btn.setFont(QFont("Arial", 10))
        self.refresh_btn.clicked.connect(self.update_status)
        
        # Add all groups to main layout
        main_layout.addWidget(source_group)
        main_layout.addWidget(artiq_group)
        main_layout.addWidget(self.refresh_btn)
        main_layout.addStretch()
        
    def update_status_indicator(self, is_on):
        """Update the visual status indicator"""
        if is_on:
            self.status_indicator.setText("ON")
            self.status_indicator.setStyleSheet("""
                QLabel {
                    background-color: #4CAF50;
                    color: white;
                    padding: 5px;
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
                    padding: 5px;
                    border: 2px solid #f44336;
                    border-radius: 5px;
                    font-weight: bold;
                }
            """)
        
        self.source_status = is_on
        
    def update_status(self):
        """Update the source status"""
        self.set_buttons_enabled(False)
        self.status_indicator.setText("CHECKING...")
        self.status_indicator.setStyleSheet("""
            QLabel {
                background-color: #FFC107;
                color: black;
                padding: 5px;
                border: 2px solid #FFC107;
                border-radius: 5px;
                font-weight: bold;
            }
        """)
        
        # Use worker thread to check status
        self.status_worker = RelayWorker(self.relay, 'read_status')
        self.status_worker.finished.connect(self.on_status_updated)
        self.status_worker.error.connect(self.on_error)
        self.status_worker.start()
        
    def on_status_updated(self, status):
        """Handle status update completion"""
        self.update_status_indicator(status)
        self.set_buttons_enabled(True)
        
    def turn_source_on(self):
        """Turn the source on"""
        self.set_buttons_enabled(False)
        self.worker = RelayWorker(self.relay, 'source_on')
        self.worker.finished.connect(self.on_operation_complete)
        self.worker.error.connect(self.on_error)
        self.worker.start()
        
    def turn_source_off(self):
        """Turn the source off"""
        self.set_buttons_enabled(False)
        self.worker = RelayWorker(self.relay, 'source_off')
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
            self.set_buttons_enabled(False)
            self.artiq_restart_btn.setText("Restarting ARTIQ...")
            
            self.worker = RelayWorker(self.relay, 'toggle_artiq')
            self.worker.finished.connect(self.on_artiq_restart_complete)
            self.worker.error.connect(self.on_error)
            self.worker.start()
            
    def on_operation_complete(self, success):
        """Handle completion of source on/off operations"""
        if success:
            # Update status after a short delay to see the change
            QTimer.singleShot(1000, self.update_status)
        else:
            self.set_buttons_enabled(True)
            QMessageBox.warning(self, "Operation Failed", "The relay operation failed.")
            
    def on_artiq_restart_complete(self, success):
        """Handle completion of ARTIQ restart"""
        self.artiq_restart_btn.setText("Restart ARTIQ")
        self.set_buttons_enabled(True)
        
        if success:
            QMessageBox.information(self, "ARTIQ Restart", "ARTIQ restart command completed successfully.")
        else:
            QMessageBox.warning(self, "ARTIQ Restart Failed", "The ARTIQ restart operation failed.")
            
    def on_error(self, error_message):
        """Handle errors from worker threads"""
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
        
        QMessageBox.critical(self, "Error", f"An error occurred:\n{error_message}")
        
    def set_buttons_enabled(self, enabled):
        """Enable or disable all buttons"""
        self.source_on_btn.setEnabled(enabled)
        self.source_off_btn.setEnabled(enabled)
        self.artiq_restart_btn.setEnabled(enabled)
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
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle('Fusion')
    
    # Create and show the GUI
    gui = EthernetRelayGUI()
    gui.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
