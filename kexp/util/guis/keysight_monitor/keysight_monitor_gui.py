import numpy as np

import sys

from subprocess import PIPE, run
from PyQt6.QtWidgets import (
    QApplication, QLabel, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QPushButton, QMainWindow, QFileDialog, QFrame, QSpacerItem,
    QSizePolicy, QMessageBox, QComboBox, QDoubleSpinBox
)
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QIcon

import vxi11
import time

T_UPDATE_MS = 500
FONTSIZE_PT = 18

class status_decoder():
    def __init__(self):
        self.error_codes = {
            0: 'OV',
            1: 'OC',
            2: 'PF',
            3: 'CP',
            4: 'OT',
            5: 'MSP',
            6: '',
            7: '',
            8: '',
            9: 'INH',
            10: 'UNR'}
    
    def check_bit(self, status, bit_idx):
        return status >> bit_idx & 1
    
    def decode_status(self, status):
        err_str = ""

        for bit in range(11):
            if self.check_bit(status, bit):
                err_str += self.error_codes[bit]
                err_str += " "
        
        return err_str

# one of these per current supply
class current_supply_widget(QWidget):
    def __init__(self,ip:str,max_current:int):
        super().__init__()
        self.ip = ip
        self.max_current = max_current
        self.supply = vxi11.Instrument(ip)
        self.status = 0
        self.err_str = ""
        self.init_device()
        self.init_UI()

        self.status_decoder = status_decoder()

    def init_device(self):
        # make sure the device is set up to listen to its inhibit pin
        self.supply.write("OUTP:INH:MODE LIVE")
        
    def read_current(self):
        # send the supply the query to measure the current
        v = self.supply.ask(":MEASure:CURRent:DC?")
        # convert it value to a number since it's a nasty string
        return float(v)
    
    def read_status(self):
        self.status = int(self.supply.ask("STAT:QUES:COND?"))
    
    def clear_protect_status(self):
        self.supply.write("OUTP:PROT:CLE")
        self.status = 0
    
    def update_UI(self):
        if not self.status:
            self.read_status()
            current = self.read_current()
            # set the value text of our box (see "init_UI") to the new current
            # the "1.4f" formats the number to a string as with 4 decimal places (f for "float")
            self.value_label.setText(f"{current:1.4f}")
        else:
            self.err_str = self.status_decoder.decode_status(self.status)
            self.value_label.setText(f"{self.err_str}")

        if 'UNR' in self.err_str:
            self.clear_protect_status()
    
    def init_UI(self):

        # this one gets "self" (is an attribute) since I'll need to update it
        # later when I check the current value
        self.value_label = QPushButton("")
        self.value_label.clicked.connect(self.clear_protect_status)
        self.value_label.setStyleSheet("font-weight: bold; font-size: {FONTSIZE_PT}pt")

        # these ones will remain the same forever so I just name them here and
        # don't bother to save them as an attribute (since I don't need to
        # reassign them later)
        text_label = QLabel(f"{self.max_current} A supply current = ")
        text_label.setStyleSheet("font-size: {FONTSIZE_PT}pt") # formatting

        unit_label = QLabel("A")

        unit_label.setStyleSheet("font-weight: bold; font-size: {FONTSIZE_PT}pt") # formatting

        # the overall layout of this part will have widgets in a horizontal line
        self.layout = QHBoxLayout() 
        # now I just stack the parts of this part of the GUI into the layout in order
        self.layout.addWidget(text_label)
        self.layout.addWidget(self.value_label)
        self.layout.addWidget(unit_label)

class Window(QWidget):
    def __init__(self):
        super().__init__()

        self.init_instruments()
        self.setup_timer_loop()
        self.set_layout()

    def setup_timer_loop(self):
        # the window gets a timer object, this runs the "connected" function
        # each time that the timer times out (exceeds T_UPDATE_MS), then runs
        # again. effect is to run the "connected" function repeatedly every
        # T_UPDATE_MS (defined way at top of file)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_UI)
        self.timer.start(T_UPDATE_MS)

    def init_instruments(self):
        current_supplies = [(170,"192.168.1.77"),
                            (500,"192.168.1.78")]
        self.supply_UIs = []
        for current, ip in current_supplies:
            self.supply_UIs.append(current_supply_widget(ip,current))

    def set_layout(self):
        self.layout = QVBoxLayout()
        # stack the layout for each of the supply UIs into the main window layout
        for supply_UI in self.supply_UIs:
            self.layout.addLayout(supply_UI.layout)

    def update_UI(self):
        for supply_UI in self.supply_UIs:
            supply_UI.update_UI()
    
def main():
    app = QApplication(sys.argv)

    app.setStyle("Windows") # fun formatting

    window = Window()
    window.setLayout(window.layout)
    window.setWindowTitle("Keysight PSU Monitor")
    window.setWindowIcon(QIcon('banana-icon.png'))
    window.setFixedSize(400, 100)

    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()