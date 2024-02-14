import sys
import os

from pylablib.devices import Newport

from PyQt6.QtCore import Qt, QSize, QMargins
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication, QLabel, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QPushButton, QMainWindow, QFileDialog, QFrame, QSpacerItem,
    QSizePolicy, QMessageBox, QDoubleSpinBox)

import numpy as np

CONTROLLER_HOSTNAME = "192.168.1.80"
CONTROLLER_ADDR = 4
N_MIRRORS = 2
MIRROR_NAMES = ["turning","kick-up"]
AXES_LISTS = [[1,2],[3,4]]
AXES_NAME_LIST = [["x","y"],["x","y"]]

class updown_button_set(QWidget):
    def __init__(self,name:str,axis:int,controller:Newport.Picomotor8742,N_big=1000,N_small=100):
        super().__init__()

        self.name = name
        self.controller = controller
        self.axis = axis
        self.N_big = N_big
        self.N_small = N_small

        self.create_buttons()
        self.setup_layout()
        self.connect_methods()

        self.cust_value_box.setValue(10)
        self.update_custom_step()

    def move(self,N_steps):
        self.controller.move_by(self.axis,N_steps,addr=CONTROLLER_ADDR)
        print(self.axis,N_steps)

    def create_buttons(self):
        self.big_up_button = QPushButton(f"+{self.N_big}")
        self.big_down_button = QPushButton(f"-{self.N_big}")
    
        self.small_up_button = QPushButton(f"+{self.N_small}")
        self.small_down_button = QPushButton(f"-{self.N_small}")

        self.cust_up_button = QPushButton("+")
        self.cust_down_button = QPushButton("-")
        self.cust_value_box = QDoubleSpinBox()
        self.cust_value_box.setSingleStep(10)
        self.cust_value_box.setDecimals(0)
        self.cust_value_box.setMaximum(50000.)

    def setup_layout(self):

        title = QLabel(self.name)

        big_layout = QVBoxLayout()
        big_layout.addWidget(self.big_up_button)
        big_layout.addWidget(self.big_down_button)

        small_layout = QVBoxLayout()
        small_layout.addWidget(self.small_up_button)
        small_layout.addWidget(self.small_down_button)

        cust_updown_layout = QVBoxLayout()
        cust_updown_layout.addWidget(self.cust_up_button)
        cust_updown_layout.addWidget(self.cust_down_button)
        cust_layout = QVBoxLayout()
        cust_layout.addWidget(self.cust_value_box)
        cust_layout.addLayout(cust_updown_layout)

        hlayout = QHBoxLayout()
        hlayout.addLayout(big_layout)
        hlayout.addLayout(small_layout)
        hlayout.addLayout(cust_layout)

        vlayout = QVBoxLayout(self)
        vlayout.addWidget(title)
        vlayout.addLayout(hlayout)

        self.layout = vlayout

    def update_custom_step(self):
        self.cust_step_size = self.cust_value_box.value()

    def connect_methods(self):
        self.small_up_button.pressed.connect(lambda: self.move(N_steps=self.N_small))
        self.small_down_button.pressed.connect(lambda: self.move(N_steps=-self.N_small))

        self.big_up_button.pressed.connect(lambda: self.move(N_steps=self.N_big))
        self.big_down_button.pressed.connect(lambda: self.move(N_steps=-self.N_big))

        self.cust_value_box.valueChanged.connect(self.update_custom_step)
        self.cust_up_button.pressed.connect(lambda: 
            self.move(N_steps=self.cust_step_size))
        self.cust_down_button.pressed.connect(lambda: 
            self.move(N_steps=-self.cust_step_size))

class mirror_panel(QWidget):
    def __init__(self,controller:Newport.Picomotor8742,name,axis_list,axes_name_list):
        super().__init__()

        self.name = name

        self.axis_control_sets = []
        for idx in range(len(axis_list)):
            self.axis_control_sets.append( updown_button_set(axes_name_list[idx],axis_list[idx],controller) )

        self.setup_layout()

    def setup_layout(self):
        
        title = QLabel(self.name)

        self.glayout = QVBoxLayout(self)
        self.glayout.addWidget(title)
        for idx in range(len(self.axis_control_sets)):
            self.glayout.addWidget(self.axis_control_sets[idx])

        self.layout = self.glayout

class main_window(QWidget):
    def __init__(self):
        super().__init__()
        
        self.stage = Newport.Picomotor8742(CONTROLLER_HOSTNAME,multiaddr=True,scan=False)

        self.panels = []
        for idx in range(N_MIRRORS):
            self.panels.append( mirror_panel(self.stage,MIRROR_NAMES[idx],AXES_LISTS[idx],AXES_NAME_LIST[idx]) )

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
