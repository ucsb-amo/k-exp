import sys
import os
from PyQt6.QtWidgets import (
    QApplication, QLabel, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QPushButton, QMainWindow, QFileDialog, QFrame, QSpacerItem,
    QSizePolicy, QMessageBox
)
import numpy as np
from PyQt6.QtCore import Qt, QSize, QMargins
from PyQt6.QtGui import QIcon
from toggleSlider import AnimatedToggle
from DAC_GUI_ExptBuilder import DACGUIExptBuilder, CHDACGUIExptBuilder
from kexp.config.dac_id import dac_frame

CODE_DIR = os.environ.get("code")
CONFIG_PATH = os.path.join(CODE_DIR,"k-exp","kexp","config","dac_config.py")

SKIP_CHANNELS = []

# Create the main window
class InputBox(QWidget):
    def __init__(self, channel):
        super().__init__()
        self.box_layout = QVBoxLayout()

        # Add frame to hold the input elements and toggle
        frame = QFrame(parent=self)
        frame.setObjectName("inputFrame")  # Add object name for styling
        frame_layout = QHBoxLayout(frame)  # Create a new QHBoxLayout for the frame
        frame_layout.setContentsMargins(0, 0, 0, 0)  # Remove margins

        # Create a container widget for the channel label and input elements
        container = QWidget(parent=frame)

        # Create a vertical layout for the container widget
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(10, 10, 0, 0)  # Remove margins
        container_layout.setSpacing(0)  # Remove spacing

        upper_label_layout = QHBoxLayout()

        # Add channel label
        channel_label = QLabel(f"CH. {channel}: ", parent=container)
        upper_label_layout.addWidget(channel_label)
        
        custom_label_box = QLineEdit(parent=container)
        custom_label_box.setFixedWidth(160)  # Adjust the width as needed
        upper_label_layout.addWidget(custom_label_box)

        container_layout.addLayout(upper_label_layout)

        # Create a horizontal layout for the toggle, channel label, input box, and volts label
        elements_layout = QHBoxLayout()
        
        # Create the AnimatedToggle widget
        self.toggle = AnimatedToggle()
        self.toggle.setFixedSize(QSize(60, 40))
        self.toggle.stateChanged.connect(self.set_channel)
        elements_layout.addWidget(self.toggle)

        set_button = QPushButton("Set")
        set_button.clicked.connect(self.set_channel)
        set_button.setFixedSize(QSize(50, set_button.sizeHint().height()))
        elements_layout.addWidget(set_button)
        spacer_after = QSpacerItem(10, 10, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        elements_layout.addItem(spacer_after)

        # Add input box
        voltage_box = QLineEdit(parent=container)
        voltage_box.setFixedWidth(50)  # Adjust the width as needed
        elements_layout.addWidget(voltage_box)

        # Add spacer for spacing before the volts label
        spacer_before = QSpacerItem(10, 10, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        elements_layout.addItem(spacer_before)

        # Add volts label
        volts_label = QLabel("V", parent=container)
        volts_label.setFixedSize(QSize(10, voltage_box.sizeHint().height()))  # Match height with input box
        volts_label.setStyleSheet("font-weight: bold;")
        elements_layout.addWidget(volts_label)

        # Add spacer for spacing after the volts label
        spacer_after = QSpacerItem(10, 10, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        elements_layout.addItem(spacer_after)

        # Add spacer for extra space on the right side
        spacer = QSpacerItem(10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        elements_layout.addItem(spacer)

        frame_layout.addWidget(container)  # Add the container widget to the frame layout
        self.box_layout.addWidget(frame)  # Add the frame to the main box layout

        self.previous_voltage = ""
        # Initialize a variable to track the previous state
        self.previous_toggle_state = self.toggle.isChecked()

        self.toggle_state = True  # True represents "on"
        self.toggle.stateChanged.connect(self.toggle_state_changed)

        self.setLayout(self.box_layout)
        self.voltage_box = voltage_box
        self.channel = channel
        self.custom_label_box = custom_label_box
        
        container_layout.addLayout(elements_layout)

        # Add outline style to the frame
        frame.setStyleSheet("#inputFrame { border: 1px solid black; }")

        self.toggle.setChecked(True)

    def set_channel(self):
        current_voltage = self.voltage_box.text().strip()
        print(self.toggle.isChecked())
        if self.toggle.isChecked():
            current_voltage = self.voltage_box.text().strip()
            if current_voltage:
                voltage = float(current_voltage)
                ch_builder = CHDACGUIExptBuilder()
                ch_builder.execute_set_dac_voltage(self.channel, voltage)
        else:
            ch_builder = CHDACGUIExptBuilder()
            ch_builder.execute_set_dac_voltage(self.channel, 0.0)

    def toggle_state_changed(self, state):
        # Check if the new state is different from the previous state
        current_toggle_state = state == Qt.CheckState.Checked
        if current_toggle_state != self.previous_toggle_state:
            self.previous_toggle_state = current_toggle_state
            self.set_channel()

class DACControlGrid(QWidget):
    def __init__(self):
        super().__init__()
        self.setGeometry(100, 100, 800, 400)

        dacs = dac_frame()
        ch_in_frame = [dac.ch for dac in dacs.dac_ch_list]

        self.layout = QVBoxLayout(self)

        # Add a hello message
        hello_msg = QLabel("<h1>DAC Control</h1>", parent=self)
        self.layout.addWidget(hello_msg)

        top_layout = QHBoxLayout()  # Create a QHBoxLayout for the top section
        self.layout.addLayout(top_layout)  # Add the top layout to the main layout

        # Create a horizontal layout for the buttons
        # button_layout = QHBoxLayout()

        # self.save_button = QPushButton("Save Configuration", parent=self)
        # self.save_button.clicked.connect(self.save_settings)
        # button_layout.addWidget(self.save_button)

        # self.reload_button = QPushButton("Reload Configuration", parent=self)
        # self.reload_button.clicked.connect(self.reload_settings)
        # button_layout.addWidget(self.reload_button)

        # # Add the button_layout to the top_layout
        # top_layout.addLayout(button_layout)

        # Create a grid layout to hold the DAC control boxes
        self.grid_layout = QHBoxLayout()
        self.layout.addLayout(self.grid_layout)

        # Create a list to store the InputBox widgets
        self.input_boxes = []
        self.channels = []  # Store the channel numbers

        # Create 32 DAC control boxes in an 8 x 4 configuration
        for i in range(4):
            row_layout = QVBoxLayout()
            self.grid_layout.addLayout(row_layout)
            for j in range(8):
                channel = i * 8 + j
                input_box = InputBox(channel)
                if channel in ch_in_frame:
                    dac_ch = dacs.dac_by_ch(channel)
                    input_box.custom_label_box.setText(dac_ch.key)
                    input_box.voltage_box.setText(f"{dac_ch.v:1.3f}")
                else:
                    input_box.voltage_box.setText("0.0")  # Set the input box value to "0.0"
                row_layout.addWidget(input_box)
                self.input_boxes.append(input_box)
                self.channels.append(input_box.channel)  # Add the channel number to the list

                if channel in SKIP_CHANNELS:
                    input_box.toggle.stateChanged.disconnect(input_box.set_channel)
                    input_box.setStyleSheet("background-color: red")
                
        # Reload labels and voltages from configuration file on first program launch without giving a warning
        # self.reload_opening()

        # Create the "Set Voltages" button
        self.button = QPushButton("Set Voltages", parent=self)
        self.button.clicked.connect(self.handle_button_click)
        self.layout.addWidget(self.button)
        
        # result = QMessageBox.warning(self, "Warning", "Set DAC output to defaults?",
        #                               QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.No)
        # if result == QMessageBox.StandardButton.Ok:
        #     self.handle_button_click()

        # Create the "Set All to Zero" button
        zero_button = QPushButton("Set All to Zero", parent=self)
        zero_button.clicked.connect(self.set_all_to_zero)
        self.layout.addWidget(zero_button)

        # Set the contents margins
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.grid_layout.setSpacing(20)  # Adjust the spacing between input boxes

    def handle_button_click(self):
        # Get the voltage values for each channel from the input boxes
        voltages = []
        channels = []
        for input_box in self.input_boxes:
            if isinstance(input_box.voltage_box, QLineEdit):  # Skip the input boxes without channel labels
                voltage = input_box.voltage_box.text().strip()
                if voltage:
                    try:
                        voltages.append(float(voltage))
                        channels.append(input_box.channel)
                    except ValueError:
                        print(f"Invalid voltage: {voltage}")

                    if input_box.channel not in SKIP_CHANNELS:
                        # Disconnect the stateChanged signal temporarily
                        input_box.toggle.stateChanged.disconnect(input_box.set_channel)

                        # Update the toggle's state without triggering set_channel
                        # if voltage != '0.0':
                        input_box.toggle.setChecked(True)
                        # else:
                        #     input_box.toggle.setChecked(False)

                        # Reconnect the stateChanged signal
                        input_box.toggle.stateChanged.connect(input_box.set_channel)

        if voltages:
            builder = DACGUIExptBuilder()
            new_channels = list( set(channels).difference(set(SKIP_CHANNELS)) )
            if new_channels != channels:
                skip_ch_idx = [channels.index(skip_ch) for skip_ch in SKIP_CHANNELS]
                no_skip_ch_idx = list( set(range(len(voltages))).difference(skip_ch_idx) )
                voltages = list(np.array(voltages)[no_skip_ch_idx])
            channels = new_channels
            
            print(channels)
            builder.execute_set_all_dac_voltage(channels, voltages)
            print(f"DAC channels are   : {channels}")
            print(f"DAC voltages set to: {voltages}")
        else:
            print("No valid voltages entered")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self.handle_button_click()

    def set_all_to_zero(self):
        for input_box in self.input_boxes:
            input_box.voltage_box.setText("0.0")

    def save_settings(self):
        pass
    # def save_settings(self):
    #     result = QMessageBox.warning(self, "Warning", "Saving settings will overwrite the existing saved configuration. All previous labels and values will be lost forever. Are you sure you want to proceed?",
    #                                  QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
    #     if result == QMessageBox.StandardButton.Ok:
    #         filename = CONFIG_PATH
    #         if filename:
    #             # Code for saving settings goes here
    #             with open(filename, "w") as file:
    #                 file.write("channels = [")
    #                 for input_box in self.input_boxes:
    #                     channel = input_box.channel
    #                     file.write(f"{channel}, ")
    #                 file.write("]\n")
    #                 file.write("voltages = [")
    #                 for input_box in self.input_boxes:
    #                     voltage = input_box.voltage_box.text()
    #                     file.write(f"{voltage}, ")
    #                 file.write("]\n")

    #                 file.write("labels = [")
    #                 for input_box in self.input_boxes:
    #                     label = input_box.custom_label_box.text()
    #                     file.write(f"'{label}', ")
    #                 file.write("]\n")
    #     else:
    #         return

    def reload_settings(self):
        pass
    # def reload_settings(self):
    #     result = QMessageBox.warning(self, "Warning", "Reloading settings will overwrite current configuration. Are you sure you want to proceed?",
    #                                  QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
    #     if result == QMessageBox.StandardButton.Ok:
    #         filename = CONFIG_PATH
    #         if filename:
    #             # Code for reloading settings goes here
    #             settings = {}
    #             with open(filename, "r") as file:
    #                 exec(file.read(), {}, settings)

    #             channels = settings.get("channels", [])
    #             voltages = settings.get("voltages", [])
    #             labels = settings.get("labels", [])
    #             for i, input_box in enumerate(self.input_boxes):
    #                 if i < len(labels):
    #                     label = labels[i]
    #                     input_box.custom_label_box.setText(label)
    #                 else:
    #                     input_box.custom_label_box.setText("")

    #             for input_box in self.input_boxes:
    #                 channel = input_box.channel
    #                 if channel in channels:
    #                     index = channels.index(channel)
    #                     voltage = voltages[index]
    #                     input_box.voltage_box.setText(str(voltage))
    #                 else:
    #                     input_box.voltage_box.setText("0.0")
    #     else:
    #         return
        
    def reload_opening(self):
        pass
    # def reload_opening(self):
    #     filename = CONFIG_PATH  # Set the file name

    #     settings = {}
    #     with open(filename, "r") as file:
    #         exec(file.read(), {}, settings)

    #     channels = settings.get("channels", [])
    #     voltages = settings.get("voltages", [])

    #     labels = settings.get("labels", [])

    #     for i, input_box in enumerate(self.input_boxes):
    #         if i < len(labels):
    #             label = labels[i]
    #             input_box.custom_label_box.setText(label)
    #         else:
    #             input_box.custom_label_box.setText("")

    #     for input_box in self.input_boxes:
    #         channel = input_box.channel
    #         if channel in channels:
    #             index = channels.index(channel)
    #             voltage = voltages[index]
    #             input_box.voltage_box.setText(str(voltage))
    #         else:
    #             input_box.voltage_box.setText("0.0")
    
app = QApplication(sys.argv)
window = QMainWindow()

# Set the style
app.setStyle("Fusion")  # Set the style to Fusion

grid = DACControlGrid()
window.setCentralWidget(grid)
window.setWindowTitle("DAC Control Grid")
window.setWindowIcon(QIcon('banana-icon.png'))

# Set the window position at the top of the screen
window.setGeometry(window.x(), 0, window.width(), window.height())

window.show()
sys.exit(app.exec())
