from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
import sys
import textwrap

import os
from subprocess import PIPE, run

from kexp.util.guis.dds.dds_gui_ExptBuilder import DDSGUIExptBuilder
from kexp.control.artiq.DDS import DDS
from kexp.config import dds_state

from kexp.config import dds_id

from kexp.config.expt_params import ExptParams 

__config_path__ = dds_state.__file__
expt_builder = DDSGUIExptBuilder()

p = ExptParams()
VPD_VALUES = [[dds.v_pd for dds in this_uru_dds] for this_uru_dds in dds_state.dds_state]
        
class DDSSpinner(QWidget):
    '''Frequency and amplitude spinbox widgets for a DDS channel'''
    def __init__(self,urukul_idx,ch_idx):
        super().__init__(parent=None)

        self.modelDDS = DDS(urukul_idx,ch_idx)

        layout = QVBoxLayout()
        labeltext = f'Urukul{urukul_idx}_Ch{ch_idx}'

        self.f = QDoubleSpinBox()
        self.f.setRange(0.,500.)
        self.f.setSuffix(" MHz")
        self.f.setDecimals(3)
        self.f.setSingleStep(3.)
        
        self.amp = QDoubleSpinBox()
        self.amp.setRange(0.,1.)
        # self.amp.setSuffix("")
        self.amp.setDecimals(4)

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
        layout.addWidget(self.amp)

        onofflayout = QHBoxLayout()
        # onofflayout.addWidget(self.onbutton)
        onofflayout.addWidget(self.offbutton)

        layout.addLayout(onofflayout)

        self.setLayout(layout)

    def submit_dds_off_job(self):
        expt_builder.execute_single_dds_off(self.modelDDS)

    # def submit_dds_on_job(self):
    #     freq_MHz = self.f.value()
    #     amp = self.amp.value()
    #     self.modelDDS.freq_MHz = freq_MHz
    #     self.modelDDS.amplitude = amplitude
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
        self.setFixedSize(300,600)

        self.N_urukul = dds_id.N_uru
        self.N_ch = dds_id.N_ch

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

        self.mot_observe_button = QToolButton()
        self.mot_observe_button.setText("MOT observe")
        self.mot_observe_button.clicked.connect(self.submit_mot_observe)
        self.mot_observe_button.setSizePolicy(sizePolicy)
        self.grid.addWidget(self.mot_observe_button,self.N_ch+3,0,1,self.N_urukul)

        self.hmot_observe_button = QToolButton()
        self.hmot_observe_button.setText("Hybrid MOT observe")
        self.hmot_observe_button.clicked.connect(self.submit_hybrid_mot_observe)
        self.hmot_observe_button.setSizePolicy(sizePolicy)
        self.grid.addWidget(self.hmot_observe_button,self.N_ch+4,0,1,self.N_urukul)

        self.imaging_beam_observe_button = QToolButton()
        self.imaging_beam_observe_button.setText("Imaging beam only")
        self.imaging_beam_observe_button.clicked.connect(self.submit_img_observe)
        self.imaging_beam_observe_button.setSizePolicy(sizePolicy)
        self.grid.addWidget(self.imaging_beam_observe_button,self.N_ch+5,0,1,self.N_urukul)

        self.all_on_button = QToolButton()
        self.all_on_button.setText("All on")
        self.all_on_button.clicked.connect(self.submit_all_on)
        self.all_on_button.setSizePolicy(sizePolicy)
        self.grid.addWidget(self.all_on_button,self.N_ch+6,0,1,self.N_urukul)

        self.setLayout(self.grid)

    def submit_all_on(self):
        __code_path__ = os.environ.get('code')
        __temp_exp_path__ = os.path.join(__code_path__,"k-exp","kexp","experiments","tools","set_all_dds.py")

        expt_path = __temp_exp_path__
        run_expt_command = r"%kpy% & artiq_run " + expt_path
        result = run(run_expt_command, stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
        self.message.msg_report(result.returncode)

    def submit_img_observe(self):
        __code_path__ = os.environ.get('code')
        __temp_exp_path__ = os.path.join(__code_path__,"k-exp","kexp","experiments","tools","imaging_beam_observe.py")

        expt_path = __temp_exp_path__
        run_expt_command = r"%kpy% & artiq_run " + expt_path
        result = run(run_expt_command, stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
        self.message.msg_report(result.returncode)

    def submit_mot_observe(self):
        __code_path__ = os.environ.get('code')
        __temp_exp_path__ = os.path.join(__code_path__,"k-exp","kexp","experiments","tools","mot_observe.py")

        expt_path = __temp_exp_path__
        run_expt_command = r"%kpy% & artiq_run " + expt_path
        result = run(run_expt_command, stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
        self.message.msg_report(result.returncode)

    def submit_hybrid_mot_observe(self):
        __code_path__ = os.environ.get('code')
        __temp_exp_path__ = os.path.join(__code_path__,"k-exp","kexp","experiments","tools","hybrid_mot_observe.py")

        expt_path = __temp_exp_path__
        run_expt_command = r"%kpy% & artiq_run " + expt_path
        result = run(run_expt_command, stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
        self.message.msg_report(result.returncode)

    def add_dds_to_grid(self):
        '''Populate grid layout with dds channels'''

        self.spinners = dds_id.dds_empty_frame()

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
        spin.amp.valueChanged.connect(self.valueChangedWarning)
        self.spinners[uru_idx][ch_idx] = spin

    def valueChangedWarning(self):
        self.message.setText("A value has been changed -- values shown may not reflect DDS settings.")

    def spinners_to_param_list(self):
        '''Convert gui values into parameter list'''
        param_list = dds_id.dds_empty_frame()
        for uru_idx in range(self.N_urukul):
            for ch_idx in range(self.N_ch):
                this_spinner = self.spinners[uru_idx][ch_idx]
                freq = this_spinner.f.value() * 1.e6
                amp = this_spinner.amp.value()
                param_list[uru_idx][ch_idx] = DDS(uru_idx,ch_idx,freq,amp)
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
        f = dds.frequency
        amp = dds.amplitude

        self.spinners[uru_idx][ch].f.setValue(f/1.e6)
        self.spinners[uru_idx][ch].amp.setValue(amp)

    def read_defaults(self):
        for dds_uru_list in dds_state.dds_state:
            for dds in dds_uru_list:
                self.update_dds(dds)
                self.message.msg_loadedText()

    def write_defaults(self):
        dds_strings = self.make_write_defaults_line()
        default_py = textwrap.dedent(
            f"""
            from kexp.control.artiq.DDS import DDS
            from artiq.experiment import *

            dds_state = [{dds_strings}]
            """
        )
        with open(__config_path__, 'w') as file:
            file.write(default_py)

    def make_write_defaults_line(self):
        lines = ""
        for uru_idx in range(self.N_urukul):
            lines += "["
            for ch in range(self.N_ch):
                frequency = self.spinners[uru_idx][ch].f.value()
                amp = self.spinners[uru_idx][ch].amp.value()
                vpd = VPD_VALUES[uru_idx][ch]
                linetoadd = f"""
                DDS({uru_idx:d},{ch:d},{frequency:.2f}*MHz,{amp:.4f},{vpd:.4f})"""
                if ch != (self.N_ch-1):
                    linetoadd += ","
                lines += linetoadd
            linetoadd = "]"
            if uru_idx != (self.N_urukul - 1):
                linetoadd += ","
            lines += linetoadd
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
