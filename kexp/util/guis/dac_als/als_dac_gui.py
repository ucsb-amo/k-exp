from kexp.control.als_remote_control import als_power_to_voltage, als_voltage_to_power
import numpy as np

import sys
import os
import textwrap
from subprocess import PIPE, run
from PyQt6.QtWidgets import (
    QApplication, QLabel, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QPushButton, QMainWindow, QFileDialog, QFrame, QSpacerItem,
    QSizePolicy, QMessageBox, QComboBox, QDoubleSpinBox
)
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QIcon

DAC_CH_ALS = 4
    
class ALSControlWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.expt_builder = ALSGUIExptBuilder()
        self.make_layout()
        self.update_button_clicked()

    def make_layout(self):

        title = QLabel("ALS Power Control")

        power_label = QLabel("Power")
        self.power_value = QDoubleSpinBox()
        self.power_value.setKeyboardTracking(False)
        self.power_value.valueChanged.connect(self.update_dac_voltage_box)
        power_unit_label = QLabel("W")

        v_label = QLabel("DAC Volts")
        self.dac_value = QDoubleSpinBox()
        self.dac_value.setKeyboardTracking(False)
        self.dac_value.valueChanged.connect(self.update_power_box)
        v_unit_label = QLabel("V")

        self.set_button = QPushButton("Set")
        self.set_button.clicked.connect(self.set_button_clicked)

        self.off_button = QPushButton("Off")
        self.off_button.clicked.connect(self.off_button_clicked)

        current_dac_label = QLabel("Current DAC Voltage =")
        self.current_dac_value = QLabel("")
        self.current_dac_value.setStyleSheet("font-weight: bold")

        current_als_label = QLabel("Current ALS Power =")
        self.current_als_value = QLabel("")
        self.current_als_value.setStyleSheet("font-weight: bold")

        self.update_button = QPushButton("Update DAC Reading")
        self.update_button.clicked.connect(self.update_button_clicked)

        layout = QVBoxLayout()
        p_layout = QHBoxLayout()
        v_layout = QHBoxLayout()
        button_layout = QHBoxLayout()
        current_val_layout_1 = QHBoxLayout()
        current_val_layout_2 = QHBoxLayout()
        update_button_layout = QHBoxLayout()

        layout.addWidget(title)
        
        p_layout.addWidget(power_label)
        p_layout.addWidget(self.power_value)
        p_layout.addWidget(power_unit_label)

        v_layout.addWidget(v_label)
        v_layout.addWidget(self.dac_value)
        v_layout.addWidget(v_unit_label)
        
        button_layout.addWidget(self.set_button)
        button_layout.addWidget(self.off_button)

        current_val_layout_2.addWidget(current_als_label)
        current_val_layout_2.addWidget(self.current_als_value)

        current_val_layout_1.addWidget(current_dac_label)
        current_val_layout_1.addWidget(self.current_dac_value)

        update_button_layout.addWidget(self.update_button)

        layout.addLayout(p_layout)
        layout.addLayout(v_layout)
        layout.addLayout(button_layout)
        layout.addLayout(current_val_layout_2)
        layout.addLayout(current_val_layout_1)
        layout.addLayout(update_button_layout)
        self.layout = layout

        self.power_layout = current_val_layout_2

    def update_power_box(self):
        power = als_voltage_to_power(self.dac_value.value())
        self.power_value.setValue(power)

    def update_dac_voltage_box(self):
        voltage = als_power_to_voltage(self.power_value.value())
        self.dac_value.setValue(voltage)

    def set_button_clicked(self):
        voltage = self.dac_value.value()
        returncode, out = self.expt_builder.set_expt(voltage)
        self.returncode_feedback(returncode,self.set_button)
        self.update_current_value(out)

    def off_button_clicked(self):
        returncode, out = self.expt_builder.set_expt(0.0)
        self.returncode_feedback(returncode,self.off_button)
        self.update_current_value(out)

    def update_button_clicked(self):
        returncode, current_val = self.expt_builder.read_dac_expt()
        self.returncode_feedback(returncode,self.update_button)
        self.update_current_value(current_val)

    def update_current_value(self, dac_read_output):
        v_dac = self.dac_mu_to_voltage(int(dac_read_output))
        als_power = als_voltage_to_power(v_dac)
        self.current_dac_value.setText(f"{v_dac:1.3f} V")
        self.current_als_value.setText(f"{als_power:1.2f} W")
        if v_dac > 0.:
            self.current_als_value.setStyleSheet("background-color: #FC5656; font-weight: bold")
        elif v_dac == 0.:
            self.current_als_value.setStyleSheet("font-weight: bold")

    def dac_mu_to_voltage(self, dac_mu):
        V_abs_max = 10.
        return (dac_mu - 2**15) / 2**15 * V_abs_max
    
    def returncode_feedback(self, returncode, button:QPushButton, t=1000):
        if returncode == 0: 
            button.setStyleSheet("background-color: #FFA500")
            QTimer.singleShot(t, lambda: button.setStyleSheet(""))
        else:
            button.setStyleSheet("background-color: #FF4500")
            QTimer.singleShot(t, lambda: button.setStyleSheet(""))
        
class ALSGUIExptBuilder():
    def __init__(self):
        self.__code_path__ = os.environ.get('code')
        self.__temp_exp_path__ = os.path.join(self.__code_path__,"k-exp","kexp","experiments","als_dac_expt.py")

    def write_experiment_to_file(self,program):
        with open(self.__temp_exp_path__, 'w') as file:
            file.write(program)

    def run_expt(self):
        expt_path = self.__temp_exp_path__
        run_expt_command = r"%kpy% & ar " + expt_path
        result = run(run_expt_command, stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
        print(result.returncode, result.stdout, result.stderr)
        os.remove(self.__temp_exp_path__)
        return result.returncode, result.stdout
    
    def execute(self,script):
        self.write_experiment_to_file(script)
        returncode, out = self.run_expt()
        return returncode, out
    
    def set_expt(self, voltage):
        script = textwrap.dedent(f"""
                    from artiq.experiment import *
                    from kexp import Base
                    class StartUp(EnvExperiment,Base):
                        def build(self):
                            Base.__init__(self,setup_camera=False)
                            self.out = 0
                        @kernel
                        def run(self):
                            self.init_kernel(run_id = False, init_dds = False, init_dac = True, dds_set = False, dds_off = False, beat_ref_on=False)
                            self.dac.dac_device.write_dac({DAC_CH_ALS}, {voltage:1.3f})
                            self.dac.dac_device.load()
                            delay(1*ms)
                            self.out = self.dac.dac_device.read_reg(channel={DAC_CH_ALS})
                        def analyze(self):
                            print(self.out)
                    """)
        returncode, out = self.execute(script)
        return returncode, out
    
    def read_dac_expt(self):
        script = textwrap.dedent(f"""
                    from artiq.experiment import *
                    from kexp import Base
                    class StartUp(EnvExperiment,Base):
                        def build(self):
                            Base.__init__(self,setup_camera=False)
                            self.out = 0
                        @kernel
                        def run(self):
                            self.init_kernel(run_id = False, init_dds = False, init_dac = True, dds_set = False, dds_off = False, beat_ref_on=False)
                            self.out = self.dac.dac_device.read_reg(channel={DAC_CH_ALS})
                        def analyze(self):
                            print(self.out)
                    """)
        returncode, out = self.execute(script)
        return returncode, out
        
def main():
    app = QApplication(sys.argv)
    window = QWidget()

    # app.setStyle("Windows")

    grid = ALSControlWindow()
    window.setLayout(grid.layout)
    window.setWindowTitle("ALS Control Panel")
    window.setWindowIcon(QIcon('banana-icon.png'))

    window.setFixedSize(266, 200)

    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()