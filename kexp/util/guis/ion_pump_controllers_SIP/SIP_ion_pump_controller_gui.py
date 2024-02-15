import socket
import sys
import os
from PyQt6.QtWidgets import (
    QApplication, QLabel, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QPushButton, QMainWindow, QFileDialog, QFrame, QSpacerItem,
    QSizePolicy, QMessageBox
)
import numpy as np
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon, QCloseEvent

import asyncio

DEFAULT_HOST_IP = '192.168.1.76'
IP_SOURCE = '192.168.1.81'
IP_CELL = '192.168.1.82'
UDP_PORT = 2572
T_UPDATE_MS = 5000

class ion_pump_data_dealer():
    def __init__(self):
        self.nA_per_torr = 65.e9 # default, see manual

    def decode_pressure(self,data):
        return self.decode_current(data) / self.nA_per_torr

    def decode_current(self,data):
        '''
        Returns the current in nA from the data output of the ion pump
        controller (READ_ALL_ANSWER format, response to Read All '/x01/x05')
        '''
        data_bytes = data[0]
        return self.payload_bits_to_int(data_bytes,80,32)
    
    def payload_bits_to_int(data_bytes,start_bit,bit_length):
        payload_length_bytes = bit_length // 8
        initial_offset_bytes = 2
        offset_bytes = initial_offset_bytes + start_bit // 8
        val = data_bytes[offset_bytes:(payload_length_bytes+offset_bytes)]
        return int.from_bytes(val,"big")
    
DEALER = ion_pump_data_dealer()

class ion_pump_panel(QWidget):
    def __init__(self,name,controller_ip,socket:socket.socket):
        super().__init__()
        self.ip = controller_ip
        self.sock = socket
        self.name = name

        self.pressure = 0.

        self.read_all_msg = bytes.fromhex("01 05")
        
        self.setup_gui_elems()
        self.setup_layout()

    def setup_gui_elems(self):
        self.label = QLabel(self.name)
        self.pressure_box = QLabel(0.)
        self.pressure_box_unit = QLabel("torr")

    def setup_layout(self):
        self.layout = QHBoxLayout()
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.pressure_box)
        self.layout.addWidget(self.pressure_box_unit)

    def update_pressure(self):
        self.pressure = self.get_pressure()
        if self.pressure == 0.:
            self.pressure_box.setText("<1.5e-11")
        else:
            self.pressure_box.setText(f"{self.pressure:1.3g}")
    
    def get_pressure(self):
        self.sock.sendto(self.read_all_msg,(self.ip,UDP_PORT))
        data = self.sock.recvfrom(302)
        pressure_torr = DEALER.decode_pressure(data)
        return pressure_torr

class app(QWidget):
    def __init__(self):
        super().__init__()
        self.setup_socket()
        self.setup_gui_elems()
        self.setup_layout()

    def setup_gui_elems(self):
        self.ip_box_label = QLabel("Host IP")
        self.ip_edit = QLineEdit(DEFAULT_HOST_IP)

        self.ip_box_cell = ion_pump_panel(name="Cell",ip=IP_CELL)
        self.ip_box_source = ion_pump_panel(name="Source",ip=IP_SOURCE)

    def setup_layout(self):

        self.ip_select_layout = QHBoxLayout()
        self.ip_select_layout.addWidget(self.ip_box_label)
        self.ip_select_layout.addWidget(self.ip_edit)

        self.layout = QVBoxLayout()
        self.layout.addLayout(self.ip_select_layout)
        self.layout.addWidget(self.ip_box_cell)
        self.layout.addWidget(self.ip_box_source)

    def setup_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_gui)
        self.timer.start(T_UPDATE_MS)

    def update_gui(self):
        self.ip_box_cell.update_pressure()
        self.ip_box_source.update_pressure()
        
    def setup_socket(self):
        self.sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.sock.bind((self.ip_edit.text(),UDP_PORT))

    def closeEvent(self):
        self.sock.close()

