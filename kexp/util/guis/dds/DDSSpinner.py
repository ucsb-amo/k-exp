from PyQt6.QtWidgets import (
    QApplication, QLabel, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QDoubleSpinBox, QToolButton, QMainWindow, QMessageBox
)
from PyQt6.QtCore import Qt
import sys
# Add the path to the 'kexp' module
kexp_path = "C:/Users/clepart/Documents/GitHub/kexp"
sys.path.append(kexp_path)

# Replace with relevant imports for DDS
from kexp.util.guis.dds.dds_gui_ExptBuilder import DDSGUIExptBuilder
# from DDS_GUIExptBuilder import DDSGUIExptBuilder
from kexp.control.artiq.DDS import DDS
from kexp.config import dds_state
from kexp.config import dds_id
from kexp.config.expt_params import ExptParams 


class DDSSpinner(QWidget):
    '''Frequency and amplitude spinbox widgets for a DDS channel'''
    def __init__(self, urukul_idx, ch_idx):
        super().__init__(parent=None)

        self.modelDDS = DDS(urukul_idx, ch_idx)

        layout = QVBoxLayout()
        labeltext = f'Urukul{urukul_idx}_Ch{ch_idx}'

        self.f = QDoubleSpinBox()
        self.f.setRange(0., 500.)
        self.f.setSuffix(" MHz")
        self.f.setDecimals(3)
        self.f.setSingleStep(3.)

        self.amp = QDoubleSpinBox()
        self.amp.setRange(0., 1.)
        self.amp.setDecimals(4)

        self.offbutton = QToolButton()
        self.offbutton.pressed.connect(self.submit_dds_off_job)
        self.offbutton.setText("Off")

        layout.addWidget(QLabel(labeltext, alignment=Qt.AlignmentFlag.AlignCenter))
        layout.addWidget(self.f)
        layout.addWidget(self.amp)

        onofflayout = QHBoxLayout()
        onofflayout.addWidget(self.offbutton)

        layout.addLayout(onofflayout)

        self.setLayout(layout)

    def submit_dds_off_job(self):
        expt_builder.execute_single_dds_off(self.modelDDS)

class MainWindow(QWidget):
    def __init__(self):
        '''Create main window, populate with widgets'''
        super().__init__()
        self.setFixedSize(300, 600)

        self.N_urukul = dds_id.N_uru
        self.N_ch = dds_id.N_ch

        self.grid = QGridLayout()
        self.setWindowTitle("DDS Control")

        self.message = QLabel()
        self.message.setWordWrap(True)
        self.grid.addWidget(self.message, 0, 0, 1, self.N_urukul)

        self.add_dds_to_grid()

        self.button = QToolButton()
        self.button.setText("Set all")
        self.button.setToolTip("Submit the changes")
        self.button.pressed.connect(self.submit_job)
        self.button.setShortcut("Return")
        self.grid.addWidget(self.button, self.N_ch + 1, 1, 1, self.N_urukul - 1)

        self.setLayout(self.grid)

    def add_dds_to_grid(self):
        '''Populate grid layout with DDS channels'''

        self.spinners = dds_id.dds_empty_frame()

        for uru_idx in range(self.N_urukul):
            for ch_idx in range(self.N_ch):
                self.make_spinner(uru_idx, ch_idx)
                self.grid.addWidget(
                    self.spinners[uru_idx][ch_idx],
                    ch_idx + 1, uru_idx)

    def make_spinner(self, uru_idx, ch_idx):
        '''Create DDS spinner GUI widget for specified uru, ch'''
        spin = DDSSpinner(uru_idx, ch_idx)
        spin.f.valueChanged.connect(self.valueChangedWarning)
        spin.amp.valueChanged.connect(self.valueChangedWarning)
        self.spinners[uru_idx][ch_idx] = spin

    def valueChangedWarning(self):
        self.message.setText("A value has been changed -- values shown may not reflect DDS settings.")

    def spinners_to_param_list(self):
        '''Convert GUI values into a parameter list'''
        param_list = dds_id.dds_empty_frame()
        for uru_idx in range(self.N_urukul):
            for ch_idx in range(self.N_ch):
                this_spinner = self.spinners[uru_idx][ch_idx]
                freq = this_spinner.f.value() * 1.e6
                amp = this_spinner.amp.value()
                param_list[uru_idx][ch_idx] = DDS(uru_idx, ch_idx, freq, amp)
        return param_list

    def submit_job(self):
        '''Submit job when clicked or when the hotkey is pressed'''
        param_list = self.spinners_to_param_list()
        returncode = expt_builder.execute_set_from_gui(param_list)
        self.message.setText("Settings applied with no errors.\n" if returncode == 0 else "An error occurred applying settings. Check error messages.")

def main():
    app = QApplication([])
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    # expt_builder = DDSGUIExptBuilder()  # Instantiate DDSGUIExptBuilder
    app = QApplication([])
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
