from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
import sys

from make_dds_expt import *
        
class DDSSpinner(QWidget):
    def __init__(self,urukul_idx,ch_idx):
        super().__init__(parent=None)

        layout = QVBoxLayout()
        flayout = QHBoxLayout()
        attlayout = QHBoxLayout()
        labeltext = f'Urukul{urukul_idx}_Ch{ch_idx}'

        self.f = QDoubleSpinBox()
        self.f.setDecimals(1)
        self.f.setRange(0.,500.)
        self.f.setSuffix(" MHz")
        
        self.att = QDoubleSpinBox()
        self.att.setRange(0.,60.)
        self.att.setSuffix(" dB")

        label = QLabel(labeltext)
        layout.addWidget(label, alignment=Qt.AlignCenter)
        layout.addWidget(self.f)
        layout.addWidget(self.att)

        self.setLayout(layout)

    #     self.fspin.returnPressed.connect(lambda: self.return_pressed())

    # def return_pressed(self,exp_builder):
    #     exp_builder.execute_expt()

class SubmitButton(QToolButton):
    def __init__(self):
        super().__init__(parent=None)

        self.setText("Set")
        self.setToolTip("Submit the changes")
        
    # def set_clicked(self,exp_builder):
    #     exp_builder.execute_expt()

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DDS Control")
        grid = QGridLayout()

        self.expt_builder = ExptBuilder()
        
        self.spinners = [[None,None,None,None],[None,None,None,None],[None,None,None,None]]
        for uru_idx in range(3):
            for ch_idx in range(4):
                self.make_spinner(uru_idx,ch_idx)
                this_spinner = self.spinners[uru_idx][ch_idx]
                grid.addWidget(this_spinner,ch_idx,uru_idx)

        self.button = SubmitButton()
        self.button.pressed.connect(self.submit_job)
        self.button.setShortcut("Return")

        self.set_default_params()

        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.button.setSizePolicy(sizePolicy)
        grid.addWidget(self.button,4,0,1,3)
        self.setLayout(grid)

    def make_spinner(self,uru_idx,ch_idx):
        self.spinners[uru_idx][ch_idx] = DDSSpinner(uru_idx,ch_idx)

    def spinners_to_param_list(self):
        param_list = []
        for uru_idx in range(3):
            for ch_idx in range(4):
                this_spinner = self.spinners[uru_idx][ch_idx]
                freq = this_spinner.f.value()
                att = this_spinner.att.value()
                param_list.append(ParamList(uru_idx,ch_idx,freq,att))
        return param_list

    def submit_job(self):
        '''Submit job when clicked or when hotkey is pressed'''
        param_list = self.spinners_to_param_list()
        self.expt_builder.execute_expt(param_list)

    def set_default_params(self):
        '''Set the default params'''
        self.dds(0,0,98.,14.5)
        self.dds(0,1,98.,14.5)
        self.dds(0,2,125.4,13.7)
        self.dds(0,3,98.,14.5)
        self.dds(1,0,125.4,13.7)
        self.dds(1,2,20.,13.7)
        self.dds(1,3,5.,13.7)

    def dds(self,uru_idx,ch,f,att):
        '''Set default values for when the gui opens'''
        self.spinners[uru_idx][ch].f.setValue(f)
        self.spinners[uru_idx][ch].att.setValue(att)

if __name__ == "__main__":
    app = QApplication([])
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
