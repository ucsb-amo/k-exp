import sys

from PyQt6.QtWidgets import (
    QApplication, QLabel, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QPushButton, QMainWindow, QFileDialog, QFrame, QSpacerItem,
    QSizePolicy, QMessageBox, QComboBox 
)
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal
from toggleSlider import AnimatedToggle
from PyQt6.QtGui import QColor, QIcon
import kexp.config.dds_id as dds_id
from dds_gui_ExptBuilder import DDSGUIExptBuilder
import copy

from kexp.control.artiq import DDS
import os

CODE_DIR = os.environ.get("code")
CONFIG_PATH = os.path.join(CODE_DIR,"k-exp","kexp","config","dds_state.py")

DISABLE_REVERT_BUTTON = True

EXECUTE_LOGIC = True

class DDSChannel(QWidget):

    toggleStateChanged = pyqtSignal(bool, int)

    def __init__(self, urukul_idx, ch_idx, dds: DDS):
        super().__init__(parent=None)

        self.toggle_states = {}  # Initialize toggle states dictionary

        self.dds = dds
        self.prev_freq = copy.deepcopy(self.dds.frequency)
        self.prev_amp = copy.deepcopy(self.dds.amplitude)
        self.prev_voltage = copy.deepcopy(self.dds.v_pd)
        
        self.urukul_idx = urukul_idx
        self.ch_idx = ch_idx

        dds_key = self.dds.key
        
        layout = QVBoxLayout()

        # Add frame to hold the input elements and toggle
        frame = QFrame(parent=self)
        frame.setObjectName("inputFrame")  # Add object name for styling
        frame_layout = QVBoxLayout(frame)  # Create a new QVBoxLayout for the frame
        frame_layout.setContentsMargins(10, 10, 10, 0)  # Remove margins

        # Create a QHBoxLayout to place the "CH:" label and custom_label_box on the same line
        ch_layout = QHBoxLayout()

        # Add channel label
        channel_label = QLabel(f"CH: {ch_idx}:", parent=frame)
        ch_layout.addWidget(channel_label)
    

        # Add custom label box
        self.custom_label_box = QLineEdit(parent=frame)
        self.custom_label_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)  # Set the size policy
        # default_label = f"dds{ch_idx}"  # Set the default label as "ddsX" where X is the channel number
        # custom_label_box.setText(default_label)
        self.custom_label_box.setText(dds_key)
        ch_layout.addWidget(self.custom_label_box)

        frame_layout.addLayout(ch_layout)
        # Add frequency input box and combobox
        freq_container = QWidget(parent=frame)
        freq_layout = QHBoxLayout(freq_container)
        freq_layout.setContentsMargins(0, 0, 0, 0)

        self.freq_input = QLineEdit(parent=freq_container)
        self.freq_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)  # Set the size policy
        # self.freq_input.setFixedWidth(100)
         # Set frequency input
        freq_layout.addWidget(self.freq_input)

        # Create combobox 
        self.freq_unit_combobox = QComboBox(parent=freq_container)

        # Set options
        self.set_freq_combobox_options()

        # Add to layout
        freq_layout.addWidget(self.freq_unit_combobox)

        frame_layout.addWidget(freq_container)

        # Add amplitude input box and combobox
        amp_container = QWidget(parent=frame)
        amp_layout = QHBoxLayout(amp_container)
        amp_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)  # Set alignment to the left
        amp_layout.setContentsMargins(0, 0, 0, 0)

        self.amp_input = QLineEdit(parent=amp_container)
        self.amp_input.setFixedWidth(80)
        amp_layout.addWidget(self.amp_input)

        self.amp_unit_combobox = QComboBox(parent=amp_container)

        self.set_amp_combobox_options()

        amp_layout.addWidget(self.amp_unit_combobox)

        frame_layout.addWidget(amp_container)

        # Create the AnimatedToggle widget with the specified colors
        self.toggle = AnimatedToggle(checked_color=QColor("#FFA500"), pulse_checked_color=QColor("#FFFF00"))
        self.toggle.setFixedSize(QSize(60, 40))
        EXECUTE_LOGIC = True
        self.toggle.stateChanged.connect(lambda state: self.toggle_state_changed(state, execute_logic=EXECUTE_LOGIC))
        frame_layout.addWidget(self.toggle)

         # Create the SET and REVERT buttons with smaller size
        button_height = 25
        self.set_button = QPushButton("Set", parent=frame)
        self.set_button.setFixedSize(QSize(60, button_height))
        if not DISABLE_REVERT_BUTTON:
            self.revert_button = QPushButton("Revert", parent=frame)
            self.revert_button.setFixedSize(QSize(60, button_height))
        else:
            self.revert_button = QPushButton("Revert")

        # Connect button clicks to functions
        self.set_button.clicked.connect(self.set_button_clicked)
        self.revert_button.clicked.connect(self.revert_button_clicked)

        # Create a vertical layout for buttons
        buttons_layout = QVBoxLayout()
        buttons_layout.addWidget(self.set_button)
        if not DISABLE_REVERT_BUTTON:
            buttons_layout.addWidget(self.revert_button)

        # Create a horizontal layout for toggle and buttons
        toggle_buttons_layout = QHBoxLayout()
        toggle_buttons_layout.addWidget(self.toggle)
        toggle_buttons_layout.addLayout(buttons_layout)  # Add buttons layout to the right of the toggle

        frame_layout.addLayout(toggle_buttons_layout)  # Add toggle and buttons layout to frame

        layout.addWidget(frame)  # Add the frame to the main layout

        self.setLayout(layout)

        # Add outline style to the frame
        frame.setStyleSheet("#inputFrame { border: 1px solid black; }")

        self._toggle_checked = False

    def update_previous_values(self):
        self.prev_freq = copy.deepcopy(self.dds.frequency)
        self.prev_amp = copy.deepcopy(self.dds.amplitude)
        self.prev_voltage = copy.deepcopy(self.dds.v_pd)

    def turn_on_toggle(self):
        self.toggle.setChecked(True)

    def turn_off_toggle(self):
        self.toggle.setChecked(False)

    def set_freq_combobox_options(self):
        if self.dds.transition != "None":
            # DDS has transition, use detuning  
            # initial_freq = self.dds.frequency_to_detuning(self.dds.frequency)
            self.freq_unit_combobox.addItems([ "Γ", "MHz"])
            initial_freq = self.dds.frequency
            initial_detuning = self.dds.frequency_to_detuning(initial_freq)
             # Set initial value
            self.freq_input.setText(f"{initial_detuning:.3f}")
            self.freq_unit_combobox.currentIndexChanged.connect(self.handle_freq_combo_change)
        else:
            initial_freq = self.dds.frequency / 1e6
            self.freq_unit_combobox.addItems(["MHz"])
            # Set initial value
            self.freq_input.setText(f"{initial_freq:.3f}")

    def handle_freq_combo_change(self):
        # Get current selection
        unit = self.freq_unit_combobox.currentText() 
        
        if unit == "MHz":
            # Show frequency in MHz
            freq_mhz = self.dds.frequency / 1e6
            self.freq_input.setText(f"{freq_mhz:.3f}")

        elif unit == "Γ":
            # Show detuning 
            detuning = self.dds.frequency_to_detuning(self.dds.frequency)
            self.freq_input.setText(f"{detuning:.3f}")

    def set_amp_combobox_options(self):
        if self.dds.dac_ch != -1:
            self.amp_unit_combobox.addItems(["V (DAC)","A (DDS)"])
            v_pd = self.dds.v_pd
            self.amp_input.setText(f'{v_pd}')
            self.amp_unit_combobox.currentIndexChanged.connect(self.handle_amp_combo_change)
        else:
            self.amp_unit_combobox.addItems(["A (DDS)"])
            self.amp_input.setText(f'{self.dds.amplitude}')

    def handle_amp_combo_change(self):
        unit = self.amp_unit_combobox.currentText()
        if unit == "V (DAC)":
            self.dds.amplitude = float(self.amp_input.text().strip())
            v_pd = self.dds.v_pd
            self.amp_input.setText(f"{v_pd}")
        if unit == "A (DDS)":
            if self.dds.dac_ch != -1:
                self.dds.v_pd = float(self.amp_input.text().strip())
            amp = self.dds.amplitude
            self.amp_input.setText(f'{amp}')

    def toggle_state_changed(self, state, execute_logic):
        if execute_logic:
            self.toggle_states = state
            # print("Toggle state changed:", state)
            if not state:
                # print("Turning off DDS...")
                # Handle turning off DDS here
                builder = DDSGUIExptBuilder()
                builder.one_off(self.dds)
            else:
                # print("Turning on DDS...")
                self.dds.frequency = float(self.freq_input.text().strip()) * 1e6
                unit = self.amp_unit_combobox.currentText()
                if unit == "V (DAC)":
                    self.dds.v_pd = float(self.amp_input.text().strip())
                if unit == "A (DDS)":
                    self.dds.amplitude = float(self.amp_input.text().strip())
                self.prev_freq = self.dds.frequency
                self.prev_amp = self.dds.amplitude
                self.prev_voltage = self.dds.v_pd
                builder = DDSGUIExptBuilder()
                builder.one_on(self.dds)

    def set_button_clicked(self): # set_button is a way to change input values without going through turn_off_dss, i.e. toggle off.
        # Function to handle REVERT button click

        self.update_previous_values()

        freq_unit = self.freq_unit_combobox.currentText() 
        if freq_unit == "MHz":
            # Show frequency in MHz
            self.dds.frequency = float(self.freq_input.text().strip())*1e6
            print(self.dds.frequency)
        elif freq_unit == "Γ":
            # Show detuning 
            self.dds.frequency = (self.dds.detuning_to_frequency(self.freq_input.text().strip()))
            print(self.dds.frequency)
        amp_unit = self.amp_unit_combobox.currentText()
        if amp_unit == "V (DAC)":
            self.dds.v_pd = float(self.amp_input.text().strip())
        if amp_unit == "A (DDS)":
            self.dds.amplitude = float(self.amp_input.text().strip())
            
        builder = DDSGUIExptBuilder()
        return_code = builder.one_on(self.dds)

        return_code = 0
        t = 500
        if return_code == 0: 
            EXECUTE_LOGIC = False
            self.turn_on_toggle()
            # Change the background color to the specified color
            self.set_button.setStyleSheet("background-color: #FFA500")
            # Remain colored for duration equivalent to loading DDS
            QTimer.singleShot(t, lambda: self.set_button.setStyleSheet(""))  # Clear the stylesheet to revert to default color)
            EXECUTE_LOGIC = True
        else:
             # Change the background color to the specified color
            self.set_button.setStyleSheet("background-color: #FF4500")
            # Remain colored for duration equivalent to loading DDS
            QTimer.singleShot(t, lambda: self.set_button.setStyleSheet(""))  # Clear the stylesheet to revert to default color)
        

    def revert_button_clicked(self):
        # Function to handle REVERT button click
        warningmessage = "Reverting will overwrite the existing configuration. Current settings will be lost forever."
        warningmessage += f"\nCurrent:   (frequency, amp, v_pd) = ({self.dds.frequency/1.e6:1.3f},{self.dds.amplitude:1.3f},{self.dds.v_pd:1.3f})"
        warningmessage += f"\nRevert to: (frequency, amp, v_pd) = ({self.prev_freq/1.e6:1.3f},{self.prev_amp:1.3f},{self.prev_voltage:1.3f})"
        warningmessage += f"\nAre you sure you want to proceed?"
        message = QMessageBox.warning(
            self,
            "Warning",
            warningmessage,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        if message == QMessageBox.StandardButton.Ok:
            self.dds.frequency = self.prev_freq
            self.dds.amplitude = self.prev_amp
            self.dds.v_pd = self.prev_voltage

            unit = self.freq_unit_combobox.currentText() 
            if unit == "MHz":
                # Show frequency in MHz
                print(self.dds.frequency)
                self.freq_input.setText(f"{self.dds.frequency/1e6}")
            elif unit == "Γ":
                # Show detuning 
                detuning = (self.dds.frequency_to_detuning(self.dds.frequency))
                self.freq_input.setText(f"{detuning:.3f}")
            
            unit = self.amp_unit_combobox.currentText()
            if unit == "V (DAC)": 
                print(self.dds.v_pd)
                self.amp_input.setText(f"{self.dds.v_pd}")
            elif unit == "A (DDS)":
                print(self.dds.amplitude)
                self.amp_input.setText(f'{self.dds.amplitude}')
        else:
            return
    
    def get_urukul_idx(self):
        return self.urukul_idx

    def get_ch_idx(self):
        return self.ch_idx

    def get_frequency(self):
        freq_unit = self.freq_unit_combobox.currentText()
        if freq_unit == "MHz":
            return float(self.freq_input.text().strip())
        elif freq_unit == "Γ":
            return self.dds.detuning_to_frequency(self.freq_input.text().strip())/1e6

    def get_amplitude(self):
        amp_unit = self.amp_unit_combobox.currentText()
        if amp_unit == "V (DAC)":
            return self.dds.amplitude
        elif amp_unit == "A (DDS)":
            return float(self.amp_input.text().strip())

    def get_v_dac(self):
        amp_unit = self.amp_unit_combobox.currentText()
        if amp_unit == "V (DAC)":
            return float(self.amp_input.text().strip())
        else:
            return self.dds.v_pd

class DDSControlGrid(QWidget):
    def __init__(self):
        super().__init__()
        self.setGeometry(100, 100, 800, 400)

        self.layout = QVBoxLayout(self)

        # Add a hello message
        hello_msg = QLabel("<h1>DDS Control</h1>", parent=self)
        self.layout.addWidget(hello_msg)
        
        self.init_button = QPushButton("If unsure of initialization, or CH. not responding, click here to initialize All CH.", parent=self)
        self.init_button.setStyleSheet(f"background-color: #262626")
        self.init_button.clicked.connect(self.initialize)
        self.layout.addWidget(self.init_button)

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

        # Add the button_layout to the top_layout
        # top_layout.addLayout(button_layout)

        # Create a grid layout to hold the DDS control boxes and column frames
        self.grid_layout = QGridLayout()
        self.layout.addLayout(self.grid_layout)

        # Create a list to store the DDSChannel widgets
        self.dds_channels = []

        # Create column frames to hold DDSChannel widget
        self.column_frames = []  # Convert to instance variable

        self.dds = dds_id.dds_frame()

        # Create DDS channels in each column
        for urukul_idx in range(dds_id.N_uru): # can replace with dds_id.shape[0]
            column_frame = QFrame(parent=self)
            column_frame.setFrameShape(QFrame.Shape.Box)  # Set the frame shape
            column_frame.setLineWidth(1)  # Set the frame width
            column_frame.setObjectName(f"columnFrame_{urukul_idx}")  # Add object name for styling
            column_frame.setStyleSheet("QFrame#columnFrame { border: 1px solid black; }")  # Set black border
            column_layout = QVBoxLayout(column_frame)  # Create a new QVBoxLayout for the column frame

            # Add label to the column frame
            label = QLabel(f"Urukul {urukul_idx}:", parent=column_frame)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            column_layout.addWidget(label)

            self.column_frames.append(column_frame)

            for ch_idx in range(dds_id.N_ch): # can replace with dds_id.shape[1]
                dds_object = self.dds.dds_array[urukul_idx][ch_idx]
                # main__DDSChannel object with PyQt6 general attributes
                channel = DDSChannel(urukul_idx, ch_idx, dds_object)
                # list of DDSChannel objects
                self.dds_channels.append(channel)
                column_layout.addWidget(channel)

        # Add column frames to the grid layout
        for idx, frame in enumerate(self.column_frames):
            self.grid_layout.addWidget(frame, 0, idx)

        # Set the contents margins
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.grid_layout.setSpacing(20)  # Adjust the spacing between DDS control boxes

        # Create the "Set All On" button
        set_all_button = QPushButton("Set All On", parent=self)
        set_all_button.clicked.connect(self.set_all_on)
        self.layout.addWidget(set_all_button)

        # Create the "Set All Off" button
        off_button = QPushButton("All Off", parent=self)
        off_button.clicked.connect(self.set_all_off)
        self.layout.addWidget(off_button)

    def save_settings(self):
        pass
    # def save_settings(self):
    #     result = QMessageBox.warning(
    #         self,
    #         "Warning",
    #         "Saving settings will overwrite the existing saved configuration. All previous labels and values will be lost forever. Are you sure you want to proceed?",
    #         QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
    #     )

    #     if result == QMessageBox.StandardButton.Ok:
    #         filename = CONFIG_PATH
    #         if filename:
    #             urukul_ch_indices = [(channel.get_urukul_idx(), channel.get_ch_idx()) for channel in self.dds_channels]
    #             frequencies = [channel.get_frequency() for channel in self.dds_channels]
    #             amplitudes = [channel.get_amplitude() for channel in self.dds_channels]
    #             v_dacs = [channel.get_v_dac() for channel in self.dds_channels]

    #             # Save settings to a file
    #             with open(CONFIG_PATH, "w") as f:
    #                 f.write("ch = " + str(urukul_ch_indices) + "\n")
    #                 f.write("freq = " + str([float(f"{freq:.3f}") for freq in frequencies]) + "\n")
    #                 f.write("amplitude = " + str(amplitudes) + "\n")
    #                 f.write("v_dac = " + str(v_dacs) + "\n")
            
    #             print("Settings saved to dds_state.py")
            
    #     else:
    #         return
        
    def reload_settings(self):
        pass
    # def reload_settings(self):
    #     result = QMessageBox.warning(
    #         self,
    #         "Warning",
    #         "Reloading settings will overwrite the existing configuration. All previous labels and values will be lost forever. Are you sure you want to proceed?",
    #         QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
    #     )

    #     if result == QMessageBox.StandardButton.Ok:
    #         filename = CONFIG_PATH
    #         if filename:
    #             self.load_settings_from_file(filename)
    #             print("Settings reloaded from dds_state.py")

    def load_settings_from_file(self,filename):
        pass
    # def load_settings_from_file(self, filename):
    #     try:
    #         urukul_ch_indices = dds_state.ch
    #         frequencies = dds_state.freq
    #         amplitudes = dds_state.amplitude
    #         v_dacs = dds_state.v_dac

    #         for channel, (urukul_idx, ch_idx) in zip(self.dds_channels, urukul_ch_indices):
    #             frequency = frequencies[channel.get_urukul_idx() * dds_id.N_ch + channel.get_ch_idx()]
    #             amplitude = amplitudes[channel.get_urukul_idx() * dds_id.N_ch + channel.get_ch_idx()]
    #             v_dac = v_dacs[channel.get_urukul_idx() * dds_id.N_ch + channel.get_ch_idx()]

    #             self.update_channel_inputs(channel, frequency, amplitude, v_dac)

    #     except ImportError:
    #         print("dds_state.py not found or does not contain the required attributes.")

    def update_channel_inputs(self, channel, frequency, amplitude, v_dac):

        channel.dds.v_pd = v_dac
        channel.dds.frequency = frequency * 1.e6
        channel.dds.amplitude = amplitude

        channel.freq_input.setText(f"{frequency:.3f}")
        
        if channel.dds.dac_ch != -1:
            channel.amp_unit_combobox.setCurrentText("V (DAC)")
            channel.amp_input.setText(f"{v_dac:.3f}")
        else:
            channel.amp_unit_combobox.setCurrentText("A (DDS)")
            channel.amp_input.setText(f"{amplitude:.3f}")

    def set_all_on(self):            
        # Implement All On settings logic here
        builder = DDSGUIExptBuilder()
        builder.all_on(self.dds_channels)
        EXECUTE_LOGIC = False
          # Loop through all the DDSChannel instances and turn on their toggles
        for channel in self.dds_channels:
            channel.turn_on_toggle()
        EXECUTE_LOGIC = True
            
    def set_all_off(self):
    # Implement All Off settings logic here
        builder = DDSGUIExptBuilder()
        builder.all_off(self.dds_channels)
        EXECUTE_LOGIC = False
         # Loop through all the DDSChannel instances and turn off their toggles
        for channel in self.dds_channels:
            channel.turn_off_toggle()
        EXECUTE_LOGIC = True

    def initialize(self):
        # Initalize all CH. 
        builder = DDSGUIExptBuilder()
        return_code = builder.startup(self.dds_channels)
        if return_code == 0:
            self.init_button.setText("Initialized!")
            self.init_button.setStyleSheet(f"background-color: #FFA500")
        else:
            self.init_button.setStyleSheet(f"background-color: #FF4500")

def main():
    app = QApplication(sys.argv)
    window = QWidget()

    # Set the style
    app.setStyle("Fusion")  # Set the style to Fusion

    grid = DDSControlGrid()
    window.setLayout(grid.layout)
    window.setWindowTitle("DDS Control Grid")
    window.setWindowIcon(QIcon('banana-icon.png'))

    # Set the window position at the top of the screen
    window.setGeometry(window.x(), 0, window.width(), window.height())

    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
