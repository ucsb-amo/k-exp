from PyQt6 import QtCore
import pyqtgraph as pg
from random import randint
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDateTimeEdit,
    QDial,
    QDoubleSpinBox,
    QFontComboBox,
    QLabel,
    QLCDNumber,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)
# Only needed for access to command line arguments
import sys

import serial 
import time
import re
import codecs
import csv
import os
import textwrap
from subprocess import PIPE, run

from interlock_gui_expt_builder import CHDACGUIExptBuilder

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
#import space


# You need one (and only one) QApplication instance per application.
# Pass in sys.argv to allow command line arguments for your app.
# If you know you won't use command line arguments QApplication([]) works too.

test_arr = [[1721757533.8153138,'Temp', 0, 294.95074],[1721757534.8153138,'Temp', 0, 293.95074],[1721757535.8153138,'Temp', 0, 295.95074],[1721757536.8153138,'Temp', 0, 294.95074],[1721757537.8153138,'Temp', 0, 296.95074]]

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        #If error called here, check if something else is using comport, eg arduino serial monitor is open
        self.comPort = serial.Serial(port='COM5', baudrate=9600, timeout=1) 
        
        self.setWindowTitle("Interlock GUI")
        # button = QPushButton("RESET INTERLOCK!")
        # button.setCheckable(True)
        # button.clicked.connect(self.the_button_was_clicked)
        # button.setStyleSheet("""
        #     QPushButton {
        #         background-color: red;
        #         color: white;
        #         font-size: 24px;
        #         font-weight: bold;
        #         padding: 10px 20px;
        #     }
        # """)
        self.last_valid_data_time = time.time()
        self.timeout_threshold = 15  # 30 seconds
        
        # Timer for checking timeouts
        self.timeout_timer = QtCore.QTimer()
        self.timeout_timer.timeout.connect(self.check_data_timeout)
        self.timeout_timer.start(5000)  # Check every 5 seconds
        self.button = QPushButton("Interlock Active")
        self.button.setStyleSheet("""
            QPushButton {
                background-color: green;
                color: white;
                font-size: 24px;
                font-weight: bold;
                padding: 10px 20px;
            }
        """)
        self.button.setEnabled(False)


        layout = QVBoxLayout()
        layout.addWidget(self.button)
        
        # Set the central widget of the Window.
        #self.setLeftWidget(button)

        # Temperature vs time dynamic plot
        self.plot_graph = pg.PlotWidget()
        layout.addWidget(self.plot_graph)
        #self.setCentralWidget(self.plot_graph)
        self.plot_graph.setBackground("w")
        pen = pg.mkPen(color=(255, 0, 0))
        #self.plot_graph.setTitle("Chiller temperature and flow rate", color="b", size="20pt")
        styles = {"color": "red", "font-size": "18px"}
        self.plot_graph.setLabel("left", "Temperature (C)", **styles)
        self.plot_graph.setLabel("right", "Flow Rate (V)", **styles)
        self.plot_graph.setLabel("bottom", "Time (s)", **styles)
        self.plot_graph.addLegend()
        self.plot_graph.showGrid(x=True, y=True)
        self.plot_graph.setYRange(0, 40)
        
        self.plot_graph.getAxis('right').setLabel('Flow Meter value (v)', color='blue')
        self.plot_graph.getAxis('left').setLabel('Temp (c)', color='red')

        self.right_view = pg.ViewBox()
        self.plot_graph.scene().addItem(self.right_view)
        self.plot_graph.getAxis('right').linkToView(self.right_view)
        self.right_view.setXLink(self.plot_graph)

        self.has_sent_email = False

        self.plot_graph.getViewBox().sigResized.connect(self.update_views)

        self.right_view.setYRange(3, 8, padding=0)

        self.time = list(range(-1000,1))
        self.temperature = [0 for _ in range(1001)]
        self.flows = []
        for i in range(4):
            self.flows.append([0 for _ in range(1001)])
        # Get a line reference
        self.line = self.plot_graph.plot(
            self.time,
            self.temperature,
            pen='r'
        )
        self.line_2 = pg.PlotCurveItem(
            self.time,
            self.flows[0],
            name="Flow meter 1", pen = 'g')
        self.line_3 = pg.PlotCurveItem(
            self.time,
            self.flows[1], 
            name="Flow meter 2", pen = 'b')
        self.line_4 = pg.PlotCurveItem(
            self.time,
            self.flows[2] , 
            name="Flow meter 3", pen = 'cyan')
        self.line_5 = pg.PlotCurveItem(
            self.time,
            self.flows[3] ,
            name="Flow meter 4", pen = 'purple')
        self.right_view.addItem(self.line_2)
        self.right_view.addItem(self.line_3)
        self.right_view.addItem(self.line_4)
        self.right_view.addItem(self.line_5)

        # Add legends to the plot
        self.legend = pg.LegendItem((100, 60), offset=(70, 30))
        self.legend.setParentItem(self.plot_graph.graphicsItem())

        # Add items to the legend
        self.legend.addItem(self.line, "Temp")
        self.legend.addItem(self.line_2, "Flow Meter 1")
        self.legend.addItem(self.line_3, "Flow Meter 2")
        self.legend.addItem(self.line_4, "Flow Meter 3")
        self.legend.addItem(self.line_5, "Flow Meter 4")

        # Timer for live updating
        self.timer = QtCore.QTimer()
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.update_plot)
        self.timer.start()

        # Timer for saving data to CSV
        self.csv_timer = QtCore.QTimer()
        self.csv_timer.timeout.connect(self.save_to_csv)
        self.csv_timer.start(600000)  # Every 10 minutes (600,000 ms)

        widget = QWidget()
        widget.setLayout(layout)

        # Set the central widget of the Window. Widget will expand
        # to take up all the space in the window by default.
        self.setCentralWidget(widget)

    #Function that reads the PLCs serial output and parses to strings readable by the GUI
    def read_PLC(self):
        buffer = None
        
        try:
            buffer = self.comPort.read(200)
            decoded_string = codecs.decode(buffer, 'utf-8')
        except:
        # if not buffer:
            print("No data received from serial port.")
            #interlock is tripped
            self.button.setText("No serial from PLC - loss of power?")
            if not self.has_sent_email:
                self.send_email_check()
                self.has_sent_email = True
            self.button.setStyleSheet("""
                QPushButton {
                    background-color: orange;
                    color: white;
                    font-size: 24px;
                    font-weight: bold;
                    padding: 10px 20px;
                }
            """)
            self.button.setEnabled(True)
            self.button.clicked.connect(self.the_button_was_clicked)

        #print(buffer)
        #print(decoded_string)
        # time.sleep(0.1)
        # Decode the input bytes to string
        decoded_string = str(buffer)
        # Split the string by '/'
        #print(decoded_string)
        data_segments = re.split(r'/', decoded_string)
        # Initialize the 2D array
        data_array = []

        # Track if we received any valid data this cycle
        received_valid_data = False

        # Parse each segment
        for segment in data_segments:
            #print(segment)

            if 'Flowmeter' in segment:
                #print("jeff")
                received_valid_data = True
                flowmeter_match = re.search(r'Flowmeter (\d) reads ([\d\.]+)V', segment)
                if flowmeter_match:
                    meter_number = int(flowmeter_match.group(1))
                    value = float(flowmeter_match.group(2))
                    data_array.append([time.time(),'Flowmeter', meter_number, value])
            elif 'Temp' in segment:
                temp_match = re.search(r'Temp is ([\d\.]+)k', segment)
                if temp_match:
                    received_valid_data = True
                    value = float(temp_match.group(1))
                    data_array.append([time.time(),'Temp',0, value])
            elif 'TRIPPED' in segment:
                tripped = re.search(r'I TRIPPED', segment)    
                #print("TRIPPED")
                received_valid_data = True
                if tripped:
                    data_array.append('I-T')
        if received_valid_data:
            self.last_valid_data_time = time.time()
        return data_array


    def check_data_timeout(self):
        """Check if we haven't received any expected data within the timeout period"""
        current_time = time.time()
        time_since_last_data = current_time - self.last_valid_data_time
        
        if time_since_last_data > self.timeout_threshold:
            print("Timing out")
            self.button.setText("Trying to trip interlock")
            if not self.has_sent_email:
                self.send_email_check()
                self.has_sent_email = True
            self.button.setStyleSheet("""
                QPushButton {
                    background-color: orange;
                    color: white;
                    font-size: 24px;
                    font-weight: bold;
                    padding: 10px 20px;
                }
            """)
            self.button.setEnabled(True)
            self.button.clicked.connect(self.the_button_was_clicked)
        else:
            print("Recieving good data")


    def update_views(self):
        self.right_view.setGeometry(self.plot_graph.getViewBox().sceneBoundingRect())
        self.right_view.linkedViewChanged(self.plot_graph.getViewBox(), self.right_view.XAxis)

    def update_plot(self):
        #self.time = self.time[1:]
        #self.time.append(self.time[-1] + 1)
        ##Function needs to grab data until it gets all neccessary types
        data_inc = self.read_PLC()
        if data_inc:     
            for i in range(5):
                if(data_inc[i] != 'I-T'):
                    # print(data_inc[i])
                    if(data_inc[i][2] == 0):
                        self.temperature = self.temperature[1:]
                        self.temperature.append(data_inc[i][3]-273)
                    else:
                        self.flows[data_inc[i][2]-1] = self.flows[data_inc[i][2]-1][1:]
                        self.flows[data_inc[i][2]-1].append(data_inc[i][3])
                    #print(data_inc[i][3])
                elif(data_inc[i] == 'I-T'):
                    #interlock is tripped
                    self.button.setText("Interlock Tripped")
                    if not self.has_sent_email:
                        self.send_email_tripped()
                        self.has_sent_email = True
                    self.button.setStyleSheet("""
                        QPushButton {
                            background-color: red;
                            color: white;
                            font-size: 24px;
                            font-weight: bold;
                            padding: 10px 20px;
                        }
                    """)
                    self.button.setEnabled(True)
                    self.button.clicked.connect(self.the_button_was_clicked)
        print("Next dataset")
        print(self.temperature[-1])
        self.line.setData(self.time, self.temperature)
        self.line_2.setData(self.time, self.flows[0])
        self.line_3.setData(self.time, self.flows[1])
        self.line_4.setData(self.time, self.flows[2])
        self.line_5.setData(self.time, self.flows[3])
    #infrastructure-aaaaaxkptfownhvfr3q4he2qeu@weldlab.slack.com
    
    def the_button_was_clicked(self):
        print("Interlock reset")
        self.comPort.write(b'O')
        self.has_sent_email = False
        #print(time.time())
        self.button.setText("Interlock Active")
        self.button.setStyleSheet("""
            QPushButton {
                background-color: green;
                color: white;
                font-size: 24px;
                font-weight: bold;
                padding: 10px 20px;
            }
        """)
        self.button.setEnabled(False)
        self.button.clicked.disconnect(self.the_button_was_clicked)

    def send_email_tripped(self):
        self.switch_dacs_off()
        # # Create a MIME object
        msg = MIMEMultipart()
        msg['From'] = 'harry.who.is.ultra.cold@gmail.com'
        msg['To'] = 'infrastructure-aaaaaxkptfownhvfr3q4he2qeu@weldlab.slack.com'
        msg['Subject'] = 'K-Interlock Tripped'
        # Attach the message to the MIME object
        msg.attach(MIMEText('K-Interlock tripped due to too high temperature, too low flowrate or loss of power!', 'plain'))
        
        # Set up the SMTP server
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()  # Upgrade the connection to a secure encrypted SSL/TLS connection
        server.login('harry.who.is.ultra.cold@gmail.com', 'dvlw elsd mhqb mzfo')
        
        # Send the email
        server.sendmail('harry.who.is.ultra.cold@gmail.com', 'infrastructure-aaaaaxkptfownhvfr3q4he2qeu@weldlab.slack.com', msg.as_string())
        # server.sendmail('harry.who.is.ultra.cold@gmail.com', 'jackkingdon@ucsb.edu', msg.as_string())

        # Close the server connection
        server.quit()   
        print("Email sent successfully!")
        tries = 0
        try:
            self.switch_dacs_off()
            time.sleep(500)
            tries+=1
        except tries>200:
            pass
        pass
        pass

    def send_email_check(self):
        return_code = self.switch_dacs_off()
        # # Create a MIME object
        msg = MIMEMultipart()
        msg['From'] = 'harry.who.is.ultra.cold@gmail.com'
        msg['To'] = 'infrastructure-aaaaaxkptfownhvfr3q4he2qeu@weldlab.slack.com'
        msg['Subject'] = 'K-Interlock Lost connection with Kong'
        # Attach the message to the MIME object
        msg.attach(MIMEText('K Interlock has lost connection with kong -- check', 'plain'))
        
        # Set up the SMTP server
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()  # Upgrade the connection to a secure encrypted SSL/TLS connection
        server.login('harry.who.is.ultra.cold@gmail.com', 'dvlw elsd mhqb mzfo')
        
        # Send the email
        server.sendmail('harry.who.is.ultra.cold@gmail.com', 'infrastructure-aaaaaxkptfownhvfr3q4he2qeu@weldlab.slack.com', msg.as_string())
        # server.sendmail('harry.who.is.ultra.cold@gmail.com', 'jackkingdon@ucsb.edu', msg.as_string())

        # Close the server connection
        server.quit()
        print("Email sent successfully!")
        tries = 0
        while(return_code != 0):
            try:
                return_code = self.switch_dacs_off()
                time.sleep(500)
                tries+=1
            except tries>20:
                pass
        pass

    #switch DACs off
    def switch_dacs_off(self):
        eBuilder =  CHDACGUIExptBuilder()
        #Get parameters from the provided dictionary
        #eBuilder.execute_test('detune_gm',params[0])
        eBuilder.write_experiment_to_file(eBuilder.make_dac_voltage_expt())
        return eBuilder.run_expt()

    def save_to_csv(self):
        import os
        data_dir = os.getenv('data')
        subdir = 'interlock_logs'
        filename = 'plot_data.csv'
        savedir = os.path.join(data_dir,subdir,filename)
        with open(savedir, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['x', 'y1', 'y2'])
            for i in range(len(self.time)):
                writer.writerow([self.time[i], self.temperature[i], self.flows[0][i], self.flows[1][i], self.flows[2][i], self.flows[3][i]])

        print(f"Data saved to {filename}")

app = QApplication(sys.argv)

# Create a Qt widget, which will be our window.
window = MainWindow()
window.show()  # IMPORTANT!!!!! Windows are hidden by default.

# Start the event loop.
app.exec()
