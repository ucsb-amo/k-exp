import socket
import sys
from PyQt6.QtWidgets import QApplication, QLabel, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon

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

class ion_pump_client(ion_pump_data_dealer):
    def __init__(self,ip,socket:socket.socket):
        super().__init__()
        self.ip = ip
        self.socket = socket
        self.read_all_msg = bytes.fromhex("01 05")

    def get_pressure(self):
        self.socket.sendto(self.read_all_msg,(self.ip,UDP_PORT))
        data = self.socket.recvfrom(302)
        pressure_torr = self.decode_pressure(data)
        return pressure_torr

class ion_pump_panel(QWidget):
    def __init__(self,name,controller_ip,socket:socket.socket):
        super().__init__()
        self.name = name
        self.pressure = 0.
        self.client = ion_pump_client(ip=controller_ip,socket=socket)
        
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
        self.pressure = self.client.get_pressure()
        if self.pressure == 0.:
            self.pressure_box.setText("<1.5e-11")
        else:
            self.pressure_box.setText(f"{self.pressure:1.3g}")

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setup_socket()
        self.setup_gui_elems()
        self.setup_layout()
        # self.setup_timer()

    def setup_gui_elems(self):
        self.ip_box_label = QLabel("Host IP")
        self.ip_edit = QLineEdit(DEFAULT_HOST_IP)

        self.ip_boxes = []
        self.ip_boxes.append(ion_pump_panel(name="Cell",ip=IP_CELL,socket=self.sock))
        self.ip_boxes.append(ion_pump_panel(name="Source",ip=IP_SOURCE,scoket=self.sock))

    def setup_layout(self):

        self.ip_select_layout = QHBoxLayout()
        self.ip_select_layout.addWidget(self.ip_box_label)
        self.ip_select_layout.addWidget(self.ip_edit)

        self.layout = QVBoxLayout()
        self.layout.addLayout(self.ip_select_layout)
        for ip_box in self.ip_boxes:
            self.layout.addWidget(ip_box)

    def setup_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_gui)
        self.timer.start(T_UPDATE_MS)

    def update_gui(self):
        for ip_box in self.ip_boxes:
            ip_box.update_pressure()
        
    def setup_socket(self):
        self.sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        print(self.ip_edit.text())
        self.sock.bind((self.ip_edit.text(),UDP_PORT))

    def closeEvent(self):
        self.sock.close()

def main():
    app = QApplication(sys.argv)
    app.setStyle("Windows")
    window = QWidget()
    main_window = MainWindow()
    window.setLayout(main_window.layout)
    window.setWindowTitle("SIP Ion Pump Monitor")
    window.setWindowIcon(QIcon('banana-icon.png'))
    window.show()
    sys.exit(app.exec())

if __name__ == "main":
    main()