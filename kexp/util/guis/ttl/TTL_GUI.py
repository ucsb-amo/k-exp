import sys
from PyQt6.QtWidgets import (
    QApplication, QLabel, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QPushButton, QMainWindow, QFileDialog, QFrame, QSpacerItem,
    QSizePolicy, QMessageBox, QComboBox 
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QTimer


from PyQt6.QtGui import QIcon, QColor, QScreen, QGuiApplication, QPixmap
from toggleSlider import AnimatedToggle
from TTL_GUI_ExptBuilder import TTLGUIExptBuilder
from kexp.config.ttl_id import ttl_frame

import os

import numpy as np

IGNORE_IDX = range(40,48)
TTL_IDX = np.array(range(88))
TTL_IDX = list( TTL_IDX[ [idx not in IGNORE_IDX for idx in TTL_IDX] ] )

CODE_DIR = os.environ.get("code")
CONFIG_PATH = os.path.join(CODE_DIR,"k-exp","kexp","config","ttl_config.py")

class InputBox(QWidget):
    toggleStateChanged = pyqtSignal(bool, int)

    def __init__(self, channel):
        super().__init__()

        self.toggle_states = {}  # Initialize toggle states dictionary

        self.box_layout = QVBoxLayout()

        frame = QFrame(parent=self)
        frame.setObjectName("inputFrame")
        frame_layout = QHBoxLayout(frame)
        frame_layout.setContentsMargins(10, 10, 10, 0)

        container = QWidget(parent=frame)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        ch_layout = QHBoxLayout()  # Add parentheses to create an instance

        channel_label = QLabel(f"CH. {channel}: ", parent=container)  # Moved the channel label here

        custom_label_box = QLineEdit(parent=container)
        custom_label_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)  # Set the size policy
        # custom_label_box.setFixedWidth(60)

        ch_layout.addWidget(channel_label)
        ch_layout.addWidget(custom_label_box)

        # Set the default label as "ttlX" where X is the channel number
        default_label = f"ttl{channel}"
        custom_label_box.setText(default_label)

        elements_layout = QHBoxLayout()

        self.toggle = AnimatedToggle(checked_color=QColor("#0000FF"), pulse_checked_color=QColor("#6495ED"))

        self.toggle.setFixedSize(QSize(30, 20))
        elements_layout.addWidget(self.toggle)

        pulse_label = QLabel(f" _/\_ ", parent=container)
        elements_layout.addWidget(pulse_label)

        input_box = QLineEdit(parent=container)
        input_box.setFixedWidth(30)
        input_box.setText('0.0')
        elements_layout.addWidget(input_box)

        spacer_before = QSpacerItem(10, 10, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        elements_layout.addItem(spacer_before)

        # self.duration = 0  # Store the duration in a class variable

        self.duration_combobox = QComboBox(parent=container)
        self.duration_combobox.addItem("s")
        self.duration_combobox.addItem("ms")
        self.duration_combobox.addItem("µs")

        self.duration_combobox.currentIndexChanged.connect(self.update_duration)

        elements_layout.addWidget(self.duration_combobox)

        frame_layout.addWidget(container)
        self.box_layout.addWidget(frame)

        self.setLayout(self.box_layout)
        self.input_box = input_box
        self.channel = channel
        self.custom_label_box = custom_label_box
         # Add the ch_layout to the container layout
        container_layout.addLayout(ch_layout)

        container_layout.addLayout(elements_layout)
    
        frame_layout.addWidget(container)  # Add the container to the frame layout

        frame.setStyleSheet("#inputFrame { border: 1px solid black; }")

        self.do_it = True
        self.toggle.stateChanged.connect(lambda state, ch=channel: self.toggle_state_changed(state, ch, do_it=self.do_it))

    def update_duration(self):
        selected_unit = self.duration_combobox.currentText()
        if self.toggle.isChecked() and self.input_box.text():
            self.duration = float(self.input_box.text())
            if selected_unit == "µs":
                self.duration *= 1e-6
            elif selected_unit == "ms":
                self.duration *= 1e-3

        # Store the reference to the currently selected InputBox
        # InputBox.current_input_box = self

    def toggle_off_after_duration(self, channel):
        if self.toggle_states[channel]:
            self.toggle.setChecked(False)

    def toggle_state_changed(self, state, channel, do_it):
        if do_it:
            self.toggle_states[channel] = state
            if state:
                # Check if the pulse input_box value is not '0.0'
                duration = self.input_box.text()
                if float(duration) != 0.:
                    # Update the duration before using it
                    self.update_duration()
                    # Execute TTL pulse
                    self.toggle.setChecked(True)
                    if self.duration < 1:
                        ch_builder = TTLGUIExptBuilder()
                        ch_builder.execute_pulse_ttl(channel, self.duration)
                        # For durations less than 1 second, stay on for 1 second
                        QTimer.singleShot(1000, lambda: self.toggle.setChecked(False))
                    else:
                        ch_builder = TTLGUIExptBuilder()
                        ch_builder.execute_pulse_ttl(channel, self.duration)
                        # For durations greater than or equal to 1 second, stay on for the specified duration
                        interval = int(self.duration * 1000) 
                        QTimer.singleShot(interval, lambda: self.toggle.setChecked(False))
                        
                    print(f"{channel} {float(self.input_box.text())} {self.duration_combobox.currentText()}")
                else:
                    self.set_channel(channel)
            else:
                # Execute TTL on/off
                self.set_channel(channel)

    def set_channel(self, channel):
        if self.toggle.isChecked():
            # Execute TTL on
            ch_builder = TTLGUIExptBuilder()
            ch_builder.execute_set_ttl_on(channel)
            print(str(channel) + ' ON')
        else:
            # Execute TTL off
            ch_builder = TTLGUIExptBuilder()
            ch_builder.execute_set_ttl_off(channel)
            print(str(channel) + ' OFF')

class TTLControlGrid(QWidget):
    def __init__(self):
        super().__init__()

        # Variables allow for extension of grid

        # Maintains the X x 8 layout of the grid
        num_rows = int(len(TTL_IDX)/8)

        ttls = ttl_frame()
        ttl_id_channels = [ttl.ch for ttl in ttls.ttl_list]

        self.toggle_channels = {}  # Dictionary to store toggle button channels
        self.toggle_states = {}

        self.setGeometry(100, 100, 800, 400)

        self.layout = QVBoxLayout(self)

        # Add a hello message
        hello_msg = QLabel("<h1>TTL Control</h1>", parent=self)
        self.layout.addWidget(hello_msg)

        top_layout = QHBoxLayout()  # Create a QHBoxLayout for the top section
        self.layout.addLayout(top_layout)  # Add the top layout to the main layout

        # Create a horizontal layout for the buttons
        button_layout = QHBoxLayout()

        self.save_button = QPushButton("Save Configuration", parent=self)
        self.save_button.clicked.connect(self.save_settings)
        button_layout.addWidget(self.save_button)

        self.reload_button = QPushButton("Reload Configuration", parent=self)
        self.reload_button.clicked.connect(self.reload_settings)
        button_layout.addWidget(self.reload_button)

        # Add the button_layout to the top_layout
        top_layout.addLayout(button_layout)

        # Create a grid layout to hold the TTL control boxes
        self.grid_layout = QHBoxLayout()
        self.layout.addLayout(self.grid_layout)

        # Create a list to store the InputBox widgets
        self.input_boxes = []
        self.channels = []  # Store the channel numbers

        # Create 16 TTL control boxes in an 8 x 2 configuration
        for i in range(num_rows):
            row_layout = QVBoxLayout()
            self.grid_layout.addLayout(row_layout)
            for j in range(8):
                channel = TTL_IDX[i * 8 + j]
                if channel <= TTL_IDX[-1]:
                    input_box = InputBox(channel)
                    
                    if channel in ttl_id_channels:
                        idx = ttl_id_channels.index(channel)
                        input_box.custom_label_box.setText(ttls.ttl_list[idx].key)

                    row_layout.addWidget(input_box)
                    self.input_boxes.append(input_box)
                    self.channels.append(input_box.channel)  # Add the channel number to the list

                    # Store the initial state of the toggle button in the toggle_states dictionary
                    self.toggle_states[channel] = input_box.toggle.isChecked()

        # Create the "Set All Off" button
        off_button = QPushButton("Set All Off", parent=self)
        off_button.clicked.connect(self.set_all_off)
        self.layout.addWidget(off_button)

        # Set the contents margins
        self.layout.setContentsMargins(10, 10, 0, 10)
        self.grid_layout.setSpacing(0)  # Adjust the spacing between input boxes

    def set_all_off(self):
        for input_box in self.input_boxes:
            if input_box.toggle.isChecked():  # Check if the toggle is currently on
                input_box.do_it = False
                input_box.toggle.setChecked(False)  # Turn off the toggle
                channel = input_box.channel
                self.toggle_states[channel] = False
                input_box.do_it = True
        builder = TTLGUIExptBuilder()
        builder.execute_all_ttl_off(TTL_IDX)

    def save_settings(self):
        pass

    def reload_settings(self):
        pass

    # def save_settings(self):
    #     result = QMessageBox.warning(
    #         self,
    #         "Warning",
    #         "Saving settings will overwrite the existing saved configuration. All previous labels and values will be lost forever. Are you sure you want to proceed?",
    #         QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
    #     )
    #     if result == QMessageBox.StandardButton.Ok:
    #         filename = CONFIG_PATH  # Set the file name
    #         if filename:
    #             # Code for saving settings goes here
    #             channels = []
    #             durations = []
    #             labels = []
    #             duration_units = []
    #             for input_box in self.input_boxes:
    #                 channel = input_box.channel
    #                 duration = float(input_box.input_box.text())
    #                 label = input_box.custom_label_box.text()
                    
    #                 channels.append(channel)
    #                 durations.append(duration)
    #                 labels.append(label)
    #                 duration_units.append(input_box.duration_combobox.currentIndex())
        

    #             with open(filename, "w") as file:
    #                 file.write("channels = ")
    #                 file.write(str(channels))
    #                 file.write("\n")
    #                 file.write("durations = ")
    #                 file.write(str(durations))
    #                 file.write("\n")
    #                 file.write("labels = ")
    #                 file.write(repr(labels))
    #                 file.write("\n")
    #                 file.write("duration_units = ")
    #                 file.write(str(duration_units))
    #                 file.write("\n")
    #     else:
    #         return

    # def reload_settings(self):
    #     result = QMessageBox.warning(
    #         self,
    #         "Warning",
    #         "Reloading settings will overwrite current configuration. Are you sure you want to proceed?",
    #         QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
    #     )
    #     if result == QMessageBox.StandardButton.Ok:
    #         filename = CONFIG_PATH  # Set the file name
    #         if filename:
    #             # Code for reloading settings goes here
    #             settings = {}
    #             with open(filename, "r") as file:
    #                 exec(file.read(), {}, settings)
    #             channels = settings.get("channels", [])
    #             durations = settings.get("durations", [])
    #             labels = settings.get("labels", [])

    #             # Additional code to retrieve the duration units from the settings
    #             duration_units = settings.get("duration_units", [])
    #             for input_box in self.input_boxes:
    #                     channel = input_box.channel
    #                     index = channels.index(channel) if channel in channels else -1

    #                     if index != -1:
    #                         duration = durations[index]
    #                         input_box.input_box.setText(str(duration))
    #                         label = labels[index]
    #                         input_box.custom_label_box.setText(label)

    #                         # Set the corresponding index of the duration_combobox
    #                         if index < len(duration_units):
    #                             duration_unit_index = duration_units[index]
    #                             input_box.duration_combobox.setCurrentIndex(duration_unit_index)
    #                     else:
    #                         input_box.input_box.setText("")
    #                         input_box.custom_label_box.setText("")

    #                         # Set the duration_combobox index to 0 (first item) for new input_boxes
    #                         input_box.duration_combobox.setCurrentIndex(0)
    #     else:
    #         return

app = QApplication(sys.argv)
window = QMainWindow()

# Set the style
app.setStyle("Fusion")  # Set the style to Fusion

grid = TTLControlGrid()
window.setCentralWidget(grid)
window.setWindowTitle("TTL Control Grid")
window.setWindowIcon(QIcon('banana-icon.png'))

window.show()

sys.exit(app.exec())
