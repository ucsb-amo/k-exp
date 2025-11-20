import sys
import time
import serial
import numpy as np
import os
import csv
from datetime import datetime, timedelta
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                            QWidget, QPushButton, QLabel, QSpinBox, QCheckBox,
                            QComboBox, QStatusBar, QGridLayout)
from PyQt5.QtCore import QTimer, QThread, pyqtSignal, Qt
from PyQt5.QtGui import QFont
import pyqtgraph as pg
from collections import deque
import re

# Conversion factor: raw counts to Gauss
COUNTS_PER_GAUSS = 6842

class SerialReaderThread(QThread):
    data_received = pyqtSignal(float, float, float, float)  # timestamp, x, y, z
    
    def __init__(self, port='COM23', baudrate=9600):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.running = False
        self.serial_conn = None
        
    def run(self):
        try:
            self.serial_conn = serial.Serial(self.port, self.baudrate, timeout=1)
            self.running = True
            
            while self.running:
                try:
                    line = self.serial_conn.readline().decode('utf-8').strip()
                    if line and 'M:' in line:
                        # Parse line like: 16:29:12.474 -> M: -451 1264 -1771
                        parts = line.split('M:')
                        if len(parts) == 2:
                            timestamp = time.time()
                            values_str = parts[1].strip()
                            
                            # Extract the three values and convert to Gauss
                            values = values_str.split()
                            if len(values) >= 3:
                                x_raw, y_raw, z_raw = float(values[0]), float(values[1]), float(values[2])
                                # Convert to Gauss
                                x = x_raw / COUNTS_PER_GAUSS
                                y = y_raw / COUNTS_PER_GAUSS
                                z = z_raw / COUNTS_PER_GAUSS
                                self.data_received.emit(timestamp, x, y, z)
                                
                except Exception as e:
                    print(f"Error parsing line: {line}, Error: {e}")
                    
        except Exception as e:
            print(f"Serial connection error: {e}")
            
    def stop(self):
        self.running = False
        if self.serial_conn:
            self.serial_conn.close()
        self.quit()

class DataLogger:
    def __init__(self):
        # Get data directory from environment variable
        self.data_dir = os.getenv('DATA', os.path.expanduser('~/Documents'))
        self.mag_data_dir = os.path.join(self.data_dir, 'magnetometer_data')
        
        # Create directory if it doesn't exist
        os.makedirs(self.mag_data_dir, exist_ok=True)
        
        self.current_file = None
        self.current_writer = None
        self.current_date = None
        self.logged_points = 0
        
    def log_data(self, timestamp, x_gauss, y_gauss, z_gauss):
        """Log data point to CSV file (in Gauss units)"""
        current_dt = datetime.fromtimestamp(timestamp)
        today = current_dt.date()
        
        # Check if we need a new file (new day)
        if self.current_date != today:
            self._create_new_file(today)
            
        # Write data in Gauss
        if self.current_writer:
            self.current_writer.writerow([
                current_dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],  # Timestamp with milliseconds
                timestamp,
                x_gauss, y_gauss, z_gauss
            ])
            self.current_file.flush()  # Ensure data is written immediately
            self.logged_points += 1
            
    def _create_new_file(self, date):
        """Create new CSV file for the given date"""
        # Close previous file if open
        if self.current_file:
            self.current_file.close()
            
        # Create new filename
        filename = f"magnetometer_{date.strftime('%Y%m%d')}.csv"
        filepath = os.path.join(self.mag_data_dir, filename)
        
        # Open new file
        self.current_file = open(filepath, 'a', newline='')
        self.current_writer = csv.writer(self.current_file)
        
        # Write header if file is new
        if os.path.getsize(filepath) == 0:
            self.current_writer.writerow(['DateTime', 'Timestamp', 'X_Gauss', 'Y_Gauss', 'Z_Gauss'])
            
        self.current_date = date
        self.logged_points = 0
        
    def close(self):
        """Close current file"""
        if self.current_file:
            self.current_file.close()
            
    def get_current_file_path(self):
        """Get path of current log file"""
        if self.current_date:
            filename = f"magnetometer_{self.current_date.strftime('%Y%m%d')}.csv"
            return os.path.join(self.mag_data_dir, filename)
        return None

class MagnetometerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("3-Channel Magnetometer GUI with Data Logging (Gauss Units)")
        self.setGeometry(100, 100, 1400, 900)
        
        # Data storage (in Gauss)
        self.max_points = 2000
        self.timestamps = deque(maxlen=self.max_points)
        self.x_data = deque(maxlen=self.max_points)
        self.y_data = deque(maxlen=self.max_points)
        self.z_data = deque(maxlen=self.max_points)
        self.start_time = None
        
        # Data logger
        self.logger = DataLogger()
        
        # Setup UI
        self.setup_ui()
        
        # Setup serial reader
        self.serial_thread = SerialReaderThread()
        self.serial_thread.data_received.connect(self.update_data)
        
        # Setup plot update timer
        self.plot_timer = QTimer()
        self.plot_timer.timeout.connect(self.update_plots)
        
    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        
        # Control panel
        control_layout = QHBoxLayout()
        
        # Start/Stop button
        self.start_button = QPushButton("Start Acquisition")
        self.start_button.setStyleSheet("QPushButton { font-size: 14px; padding: 10px; }")
        self.start_button.clicked.connect(self.toggle_acquisition)
        control_layout.addWidget(self.start_button)
        
        # Port selection
        control_layout.addWidget(QLabel("Port:"))
        self.port_combo = QComboBox()
        self.port_combo.addItems([f"COM{i}" for i in range(1, 25)])
        self.port_combo.setCurrentText("COM23")
        control_layout.addWidget(self.port_combo)
        
        # Baud rate
        control_layout.addWidget(QLabel("Baud:"))
        self.baud_spin = QSpinBox()
        self.baud_spin.setRange(300, 115200)
        self.baud_spin.setValue(9600)
        control_layout.addWidget(self.baud_spin)
        
        # Conversion factor display
        conversion_label = QLabel(f"Scale: {COUNTS_PER_GAUSS} counts/G")
        conversion_label.setStyleSheet("color: blue; font-weight: bold;")
        control_layout.addWidget(conversion_label)
        
        # Logging checkbox
        self.logging_cb = QCheckBox("Enable Logging")
        self.logging_cb.setChecked(True)
        self.logging_cb.setToolTip(f"Log data to: {self.logger.mag_data_dir}")
        control_layout.addWidget(self.logging_cb)
        
        # Auto-scale checkbox
        self.autoscale_cb = QCheckBox("Auto-scale Y")
        self.autoscale_cb.setChecked(True)
        control_layout.addWidget(self.autoscale_cb)
        
        # Update rate
        control_layout.addWidget(QLabel("Update (ms):"))
        self.update_spin = QSpinBox()
        self.update_spin.setRange(10, 1000)
        self.update_spin.setValue(50)
        self.update_spin.valueChanged.connect(self.change_update_rate)
        control_layout.addWidget(self.update_spin)
        
        # Clear data button
        self.clear_button = QPushButton("Clear Data")
        self.clear_button.clicked.connect(self.clear_data)
        control_layout.addWidget(self.clear_button)
        
        # Open log folder button
        self.open_folder_button = QPushButton("Open Log Folder")
        self.open_folder_button.clicked.connect(self.open_log_folder)
        control_layout.addWidget(self.open_folder_button)
        
        control_layout.addStretch()
        main_layout.addLayout(control_layout)
        
        # Stats panel
        stats_layout = QHBoxLayout()
        self.x_label = QLabel("X: --- G")
        self.y_label = QLabel("Y: --- G")
        self.z_label = QLabel("Z: --- G")
        self.mag_label = QLabel("Magnitude: --- G")
        self.count_label = QLabel("Points: 0")
        self.logged_label = QLabel("Logged: 0")
        
        for label in [self.x_label, self.y_label, self.z_label, self.mag_label, self.count_label, self.logged_label]:
            label.setFont(QFont("Arial", 12, QFont.Bold))
            stats_layout.addWidget(label)
        
        stats_layout.addStretch()
        main_layout.addLayout(stats_layout)
        
        # Create plots using pyqtgraph
        self.setup_plots()
        main_layout.addWidget(self.plot_widget)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(f"Ready - Log directory: {self.logger.mag_data_dir} | Scale: {COUNTS_PER_GAUSS} counts/G")
        
    def setup_plots(self):
        # Create plot widget
        self.plot_widget = pg.GraphicsLayoutWidget()
        self.plot_widget.setBackground('w')
        
        # Create three plot items
        self.x_plot = self.plot_widget.addPlot(title="X Channel", row=0, col=0)
        self.y_plot = self.plot_widget.addPlot(title="Y Channel", row=1, col=0)
        self.z_plot = self.plot_widget.addPlot(title="Z Channel", row=2, col=0)
        
        # Configure plots
        plots_config = [
            (self.x_plot, 'X Magnetic Field (G)', 'red'),
            (self.y_plot, 'Y Magnetic Field (G)', 'green'),
            (self.z_plot, 'Z Magnetic Field (G)', 'blue')
        ]
        
        self.plot_curves = []
        for plot, ylabel, color in plots_config:
            plot.setLabel('left', ylabel)
            plot.setLabel('bottom', 'Time (s)')
            plot.showGrid(x=True, y=True, alpha=0.3)
            plot.setDownsampling(mode='peak')
            plot.setClipToView(True)
            
            # Create curve
            curve = plot.plot(pen=pg.mkPen(color=color, width=2))
            self.plot_curves.append(curve)
        
        # Link x-axes for synchronized zooming
        self.y_plot.setXLink(self.x_plot)
        self.z_plot.setXLink(self.x_plot)
        
    def change_update_rate(self):
        if self.plot_timer.isActive():
            self.plot_timer.stop()
            self.plot_timer.start(self.update_spin.value())
        
    def toggle_acquisition(self):
        if not self.serial_thread.running:
            # Start acquisition
            port = self.port_combo.currentText()
            baud = self.baud_spin.value()
            
            self.serial_thread = SerialReaderThread(port, baud)
            self.serial_thread.data_received.connect(self.update_data)
            self.serial_thread.start()
            
            self.plot_timer.start(self.update_spin.value())
            
            self.start_button.setText("Stop Acquisition")
            self.start_button.setStyleSheet("QPushButton { background-color: #ff6b6b; font-size: 14px; padding: 10px; }")
            
            log_status = "with logging" if self.logging_cb.isChecked() else "without logging"
            self.status_bar.showMessage(f"Acquiring data from {port} at {baud} baud {log_status}")
            self.start_time = time.time()
            
        else:
            # Stop acquisition
            self.serial_thread.stop()
            self.plot_timer.stop()
            
            self.start_button.setText("Start Acquisition")
            self.start_button.setStyleSheet("QPushButton { font-size: 14px; padding: 10px; }")
            self.status_bar.showMessage("Stopped - Ready to restart")
            
    def update_data(self, timestamp, x_gauss, y_gauss, z_gauss):
        if self.start_time is None:
            self.start_time = timestamp
            
        relative_time = timestamp - self.start_time
        
        # Store data in Gauss
        self.timestamps.append(relative_time)
        self.x_data.append(x_gauss)
        self.y_data.append(y_gauss)
        self.z_data.append(z_gauss)
        
        # Log data if enabled (already in Gauss)
        if self.logging_cb.isChecked():
            self.logger.log_data(timestamp, x_gauss, y_gauss, z_gauss)
        
    def update_plots(self):
        if len(self.timestamps) == 0:
            return
            
        times = np.array(list(self.timestamps))
        data_arrays = [
            np.array(list(self.x_data)),
            np.array(list(self.y_data)),
            np.array(list(self.z_data))
        ]
        
        # Update curves
        for curve, data in zip(self.plot_curves, data_arrays):
            curve.setData(times, data)
        
        # Auto-scale if enabled
        if self.autoscale_cb.isChecked():
            for plot in [self.x_plot, self.y_plot, self.z_plot]:
                plot.enableAutoRange('y', enable=True)
        
        # Update statistics labels
        if len(data_arrays[0]) > 0:
            x_val = data_arrays[0][-1]
            y_val = data_arrays[1][-1]
            z_val = data_arrays[2][-1]
            magnitude = np.sqrt(x_val**2 + y_val**2 + z_val**2)
            
            self.x_label.setText(f"X: {x_val:.4f} G")
            self.y_label.setText(f"Y: {y_val:.4f} G")
            self.z_label.setText(f"Z: {z_val:.4f} G")
            self.mag_label.setText(f"Magnitude: {magnitude:.4f} G")
            self.count_label.setText(f"Points: {len(times)}")
            self.logged_label.setText(f"Logged: {self.logger.logged_points}")
            
            # Color-code labels based on channels
            self.x_label.setStyleSheet(f"color: red; font-weight: bold;")
            self.y_label.setStyleSheet(f"color: green; font-weight: bold;")
            self.z_label.setStyleSheet(f"color: blue; font-weight: bold;")
            self.mag_label.setStyleSheet(f"color: purple; font-weight: bold;")
            
            # Update status with current log file
            if self.logging_cb.isChecked() and self.logger.get_current_file_path():
                current_file = os.path.basename(self.logger.get_current_file_path())
                self.status_bar.showMessage(f"Logging to: {current_file} | Logged: {self.logger.logged_points} | Latest: {magnitude:.4f} G")
        
    def clear_data(self):
        self.timestamps.clear()
        self.x_data.clear()
        self.y_data.clear()
        self.z_data.clear()
        self.start_time = None
        
        # Clear plots
        for curve in self.plot_curves:
            curve.setData([], [])
            
        # Reset labels
        self.x_label.setText("X: --- G")
        self.y_label.setText("Y: --- G")
        self.z_label.setText("Z: --- G")
        self.mag_label.setText("Magnitude: --- G")
        self.count_label.setText("Points: 0")
        
        self.status_bar.showMessage("Display data cleared (log files preserved)")
        
    def open_log_folder(self):
        """Open the log folder in Windows Explorer"""
        import subprocess
        try:
            subprocess.Popen(f'explorer "{self.logger.mag_data_dir}"')
        except Exception as e:
            print(f"Could not open folder: {e}")
        
    def closeEvent(self, event):
        if self.serial_thread.running:
            self.serial_thread.stop()
        self.logger.close()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Modern looking style
    
    gui = MagnetometerGUI()
    gui.show()
    
    sys.exit(app.exec_())