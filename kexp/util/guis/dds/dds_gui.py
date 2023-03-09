from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
import sys
import textwrap

from kexp.util.guis.dds.dds_gui_ExptBuilder import DDSGUIExptBuilder
from kexp.control.artiq.DDS import DDS
from kexp.config import dds_state

__config_path__ = dds_state.__file__
expt_builder = DDSGUIExptBuilder()
        
class DDSSpinner(QWidget):
    '''Frequency and attenuation spinbox widgets for a DDS channel'''
    def __init__(self,urukul_idx,ch_idx):
        super().__init__(parent=None)

        self.modelDDS = DDS(urukul_idx,ch_idx)

        layout = QVBoxLayout()
        labeltext = f'Urukul{urukul_idx}_Ch{ch_idx}'

        self.f = QDoubleSpinBox()
        self.f.setDecimals(1)
        self.f.setRange(0.,500.)
        self.f.setSuffix(" MHz")
        
        self.att = QDoubleSpinBox()
        self.att.setRange(0.,60.)
        self.att.setSuffix(" dB")

        self.offbutton = QToolButton()
        self.offbutton.pressed.connect(self.submit_dds_off_job)
        self.offbutton.setText("Off")
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.offbutton.setSizePolicy(sizePolicy)

        # self.onbutton = QToolButton()
        # self.onbutton.pressed.connect(self.submit_dds_on_job)
        # self.onbutton.setText("On")
        # sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # self.onbutton.setSizePolicy(sizePolicy)

        label = QLabel(labeltext)
        layout.addWidget(label, alignment=Qt.AlignCenter)
        layout.addWidget(self.f)
        layout.addWidget(self.att)

        onofflayout = QHBoxLayout()
        # onofflayout.addWidget(self.onbutton)
        onofflayout.addWidget(self.offbutton)

        layout.addLayout(onofflayout)

        self.setLayout(layout)

    def submit_dds_off_job(self):
        expt_builder.execute_single_dds_off(self.modelDDS)

    # def submit_dds_on_job(self):
    #     freq_MHz = self.f.value()
    #     att_dB = self.att.value()
    #     self.modelDDS.freq_MHz = freq_MHz
    #     self.modelDDS.att_dB = att_dB
    #     expt_builder.execute_single_dds_on(self.modelDDS)

class MessageWindow(QLabel):
    def __init__(self):
        super().__init__()
        self.setWordWrap(True)

    def msg_loadedText(self):
        self.setText("Settings loaded from defaults -- may not reflect active DDS settings.")

    def msg_report(self,returncode):
        if returncode == 0:
            self.setText("Settings applied with no errors.\n")
        else:
            self.setText("An error occurred applying settings. Check error messages.")

class MainWindow(QWidget):
    def __init__(self):
        '''Create main window, populate with widgets'''
        super().__init__()
        self.setFixedSize(300,540)

        self.N_urukul = 3
        self.N_ch = 4

        self.grid = QGridLayout()
        self.setWindowTitle("DDS Control")

        self.message = MessageWindow()
        msgSizePolicy = QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.message.setSizePolicy(msgSizePolicy)
        
        self.grid.addWidget(self.message,0,0,1,self.N_urukul)

        self.add_dds_to_grid()
        self.read_defaults()

        self.message.msg_loadedText()

        self.button = QToolButton()
        self.button.setText("Set all")
        self.button.setToolTip("Submit the changes")
        self.button.pressed.connect(self.submit_job)
        self.button.setShortcut("Return")
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.button.setSizePolicy(sizePolicy)
        self.grid.addWidget(self.button,self.N_ch+1,1,1,self.N_urukul-1)

        self.save_defaults_button = QToolButton()
        self.save_defaults_button.setText("Save")
        self.save_defaults_button.setToolTip("Save current DDS settings as default.")
        self.save_defaults_button.clicked.connect(self.write_config_button_pressed)
        self.save_defaults_button.setShortcut("Ctrl+S")
        self.save_defaults_button.setSizePolicy(sizePolicy)
        self.grid.addWidget(self.save_defaults_button,self.N_ch+1,0,1,1)

        self.load_defaults_button = QToolButton()
        self.load_defaults_button.setText("Load")
        self.load_defaults_button.setToolTip("Load saved DDS settings.")
        self.load_defaults_button.clicked.connect(self.load_config_button_pressed)
        self.load_defaults_button.setShortcut("Ctrl+O")
        self.load_defaults_button.setSizePolicy(sizePolicy)
        self.grid.addWidget(self.load_defaults_button,self.N_ch+2,0,1,1)

        self.all_off_button = QToolButton()
        self.all_off_button.setText("All off")
        self.all_off_button.setToolTip("Turn off all DDS channels.")
        self.all_off_button.clicked.connect(self.submit_all_dds_off_job)
        self.all_off_button.setSizePolicy(sizePolicy)
        self.grid.addWidget(self.all_off_button,self.N_ch+2,1,1,self.N_urukul-1)

        self.setLayout(self.grid)

    def add_dds_to_grid(self):
        '''Populate grid layout with dds channels'''

        self.spinners = [[None,None,None,None],[None,None,None,None],[None,None,None,None]]

        for uru_idx in range(self.N_urukul):
            for ch_idx in range(self.N_ch):
                self.make_spinner(uru_idx,ch_idx)
                self.grid.addWidget(
                    self.spinners[uru_idx][ch_idx],
                    ch_idx+1,uru_idx)

    def make_spinner(self,uru_idx,ch_idx):
        '''Create dds spinner gui widget for specified uru, ch'''
        spin = DDSSpinner(uru_idx,ch_idx)
        spin.f.valueChanged.connect(self.valueChangedWarning)
        spin.att.valueChanged.connect(self.valueChangedWarning)
        self.spinners[uru_idx][ch_idx] = spin

    def valueChangedWarning(self):
        self.message.setText("A value has been changed -- values shown may not reflect DDS settings.")

    def spinners_to_param_list(self):
        '''Convert gui values into parameter list'''
        param_list = []
        for uru_idx in range(self.N_urukul):
            for ch_idx in range(self.N_ch):
                this_spinner = self.spinners[uru_idx][ch_idx]
                freq = this_spinner.f.value()
                att = this_spinner.att.value()
                param_list.append(DDS(uru_idx,ch_idx,freq,att))
        return param_list

    def submit_job(self):
        '''Submit job when clicked or when hotkey is pressed'''
        param_list = self.spinners_to_param_list()
        returncode = expt_builder.execute_set_from_gui(param_list)
        self.message.msg_report(returncode)

    def submit_all_dds_off_job(self):
        returncode = expt_builder.execute_all_dds_off()
        self.message.msg_report(returncode)

    def update_dds(self,dds):
        '''Set default values for when the gui opens'''

        uru_idx = dds.urukul_idx
        ch = dds.ch
        f = dds.freq_MHz
        att = dds.att_dB

        self.spinners[uru_idx][ch].f.setValue(f)
        self.spinners[uru_idx][ch].att.setValue(att)

    def read_defaults(self):
        for dds in dds_state.defaults:
            self.update_dds(dds)
            self.message.msg_loadedText()

    def write_defaults(self):
        dds_strings = self.make_write_defaults_line()
        default_py = textwrap.dedent(
            f"""
            from wax.devices.DDS import DDS

            defaults = [{dds_strings}]
            """
        )
        with open(__config_path__, 'w') as file:
            file.write(default_py)

    def make_write_defaults_line(self):
        lines = ""
        for uru_idx in range(self.N_urukul):
            for ch in range(self.N_ch):
                freq_MHz = self.spinners[uru_idx][ch].f.value()
                att_dB = self.spinners[uru_idx][ch].att.value()
                lines += f"""
                DDS({uru_idx:d},{ch:d},{freq_MHz:.2f},{att_dB:.1f}),"""
        return lines

    def write_config_button_pressed(self):
        qm = QMessageBox()
        reply = qm.question(self,'Confirm',"Write new default values?", qm.Yes | qm.No, qm.No)

        if reply == qm.Yes:
            self.write_defaults()

    def load_config_button_pressed(self):
        qm = QMessageBox()
        reply = qm.question(self,'Confirm',"Load default values?", qm.Yes | qm.No, qm.No)

        if reply == qm.Yes:
            self.read_defaults()


def main():
    app = QApplication([])
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
