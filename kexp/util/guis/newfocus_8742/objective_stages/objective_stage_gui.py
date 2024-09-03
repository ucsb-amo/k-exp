import sys
import os

from pylablib.devices import Newport

from PyQt6.QtCore import Qt, QSize, QMargins, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication, QLabel, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QPushButton, QMainWindow, QFileDialog, QFrame, QSpacerItem,
    QSizePolicy, QMessageBox, QDoubleSpinBox, QSpinBox)

import numpy as np

CONTROLLER_HOSTNAME = "192.168.1.80"
N_OBJECTIVES = 2
OBJECTIVE_NAMES = ["n","s"]
AXES_LISTS = [[1,2,3],[4,5,6]]
AXES_NAME_LIST = [["x","y",'z'],["x","y",'z']]

class motor_axis():
    def __init__(self,controller_addr,motor_idx,stage_obj:Newport.Picomotor8742):
        self.addr = controller_addr
        self.motor_idx = motor_idx
        self.stage = stage_obj
        self.position = 0

    def move(self,N_steps):
        self.stage.move_by(self.motor_idx,N_steps,addr=self.addr)
        print(self.axis,N_steps)
        self.position += N_steps

    def reset_position(self):
        self.position = 0

class controller():
    
    axis_moved = pyqtSignal(int)

    def __init__(self):
        self.setup_axes()

    def setup_axes(self):
        self.axes = dict()
        n_obj = dict()
        n_obj['+y'] = motor_axis(1,1)
        n_obj['+z'] = motor_axis(1,2)
        n_obj['-z'] = motor_axis(1,3)
        n_obj['-x'] = motor_axis(2,1)
        n_obj['+x'] = motor_axis(2,2)

        s_obj = dict()
        s_obj['+x'] = motor_axis(2,4)
        s_obj['-x'] = motor_axis(3,1)
        s_obj['-y'] = motor_axis(3,2)
        s_obj['+z'] = motor_axis(3,3)
        s_obj['-z'] = motor_axis(3,4)
        
        self.axes['n'] = n_obj
        self.axes['s'] = s_obj

    def translate(self,N_steps,obj:str,axis:str):
        if obj == 'n':
            objective = self.axes['n']
            ysign = 1
        elif obj == 's':
            objective = self.axes['s']
            ysign = -1

        if '+' in axis:
            sign = 1
        elif '-' in axis:
            sign = -1

        axes_to_move = []
        if 'x' in axis:
            axes_to_move.append(objective['+z'])
            axes_to_move.append(objective['-z'])
        elif 'y' in axis:
            axes_to_move.append(objective['y'])
            N_steps = ysign * N_steps
        elif 'z' in axis:
            axes_to_move.append(objective['+x'])
            axes_to_move.append(objective['-x'])

        for axis in axes_to_move:
            axis: motor_axis
            axis.move(sign * N_steps)

    def move(self,N_steps,obj:str,axis:str):
        if obj == 'n':
            objective = self.axes['n']
            ysign = 1
        elif obj == 's':
            objective = self.axes['s']
            ysign = -1

        if '+' in axis:
            sign = 1
        elif '-' in axis:
            sign = -1

        

class objective_panel(QWidget):
    def __init__(self):
        super().__init__()
        self.setup_widgets()
        self.setup_layout()

    def setup_widgets(self):
        self.n_obj_buttons = dict()

        self.s_obj_buttons = dict()

    def setup_layout(self):
        self.layout

class motor_panel(QWidget):
    def __init__(self,axis,N_steps_spinner:QSpinBox,
                 translation_bool,
                 controller:controller):
        super().__init__()
        
        self.position = QSpinBox()
        self.button = QPushButton(axis)
        self.setup_widgets()

        if translation_bool:
            self.button.clicked.connect(
                lambda: controller.translate(N_steps_spinner.value()))
        else:
            self.button.clicked.connect(
                lambda: 
            )

    def setup_widgets(self):
        self.position.setValue(0)
        self.position.setSingleStep(50)

    def setup_layout(self):
        self.layout = QHBoxLayout()
        self.layout.addWidget(self.position)
        self.layout.addWidget(self.button)
            
class main_window(QWidget):
    def __init__(self):
        super().__init__()
        
        self.stage = Newport.Picomotor8742(CONTROLLER_HOSTNAME,multiaddr=True,scan=False)
        self.setup_layout()

    def setup_layout(self):
        self.grid = QHBoxLayout(self)
        for panel in self.panels:
            self.grid.addWidget(panel)
        self.layout = self.grid

def close_connection(stage):
    stage.close()

def main():
    app = QApplication(sys.argv)
    
    window = QWidget()
    grid = main_window()
    # app.aboutToQuit.connect(close_connection(grid.stage))

    window.setLayout(grid.layout)
    window.setWindowTitle("ODT Mirror Control")
    window.setWindowIcon(QIcon('banana-icon.png'))

    # window.setFixedSize(266, 200)

    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
