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
        button = QPushButton("RESET INTERLOCK!")
        button.setCheckable(True)
        button.clicked.connect(self.the_button_was_clicked)
        button.setStyleSheet("""
            QPushButton {
                background-color: red;
                color: white;
                font-size: 24px;
                font-weight: bold;
                padding: 10px 20px;
            }
        """)
        layout = QVBoxLayout()
        layout.addWidget(button)
        
        # Set the central widget of the Window.
        #self.setLeftWidget(button)

        # Temperature vs time dynamic plot
        self.plot_graph = pg.PlotWidget()
        layout.addWidget(self.plot_graph)
        #self.setCentralWidget(self.plot_graph)
        self.plot_graph.setBackground("w")
        pen = pg.mkPen(color=(255, 0, 0))
        self.plot_graph.setTitle("Chiller temperature and flow rate", color="b", size="20pt")
        styles = {"color": "red", "font-size": "18px"}
        self.plot_graph.setLabel("left", "Temperature / K", **styles)
        self.plot_graph.setLabel("right", "Flow Rate / V", **styles)
        self.plot_graph.setLabel("bottom", "Time / S", **styles)
        self.plot_graph.addLegend()
        self.plot_graph.showGrid(x=True, y=True)
        self.plot_graph.setYRange(270, 310)
        
        self.plot_graph.getAxis('right').setLabel('Flow Meter value/V', color='blue')
        self.plot_graph.getAxis('left').setLabel('Temp/K', color='red')

        self.right_view = pg.ViewBox()
        self.plot_graph.scene().addItem(self.right_view)
        self.plot_graph.getAxis('right').linkToView(self.right_view)
        self.right_view.setXLink(self.plot_graph)


        self.plot_graph.getViewBox().sigResized.connect(self.update_views)

        self.right_view.setYRange(3, 8, padding=0)

        self.time = list(range(1001))
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
            name="Flow meter 3", pen = 'orange')
        self.line_5 = pg.PlotCurveItem(
            self.time,
            self.flows[3] ,
            name="Flow meter 4", pen = 'yellow')
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
        buffer = self.comPort.read(200)
        decoded_string = codecs.decode(buffer, 'utf-8')
        #print(buffer)
        #print(decoded_string)
        time.sleep(0.1)
        # Decode the input bytes to string
        decoded_string = str(buffer)
        # Split the string by '/'
        #print(decoded_string)
        data_segments = re.split(r'/', decoded_string)
        # Initialize the 2D array
        data_array = []
        # Parse each segment
        for segment in data_segments:
            #print(segment)
            if 'Flowmeter' in segment:
                #print("jeff")
                flowmeter_match = re.search(r'Flowmeter (\d) reads ([\d\.]+)V', segment)
                if flowmeter_match:
                    meter_number = int(flowmeter_match.group(1))
                    value = float(flowmeter_match.group(2))
                    data_array.append([time.time(),'Flowmeter', meter_number, value])
            elif 'Temp' in segment:
                temp_match = re.search(r'Temp is ([\d\.]+)k', segment)
                if temp_match:
                    value = float(temp_match.group(1))
                    data_array.append([time.time(),'Temp',0, value])
        return data_array

    def update_views(self):
        self.right_view.setGeometry(self.plot_graph.getViewBox().sceneBoundingRect())
        self.right_view.linkedViewChanged(self.plot_graph.getViewBox(), self.right_view.XAxis)

    def update_plot(self):
        #self.time = self.time[1:]
        #self.time.append(self.time[-1] + 1)
        ##Function needs to grab data until it gets all neccessary types
        data_inc = self.read_PLC()
        for i in range(5):
            print(data_inc[i])
            if(data_inc[i][2] == 0):
                self.temperature = self.temperature[1:]
                self.temperature.append(data_inc[i][3])
            else:
                self.flows[data_inc[i][2]-1] = self.flows[data_inc[i][2]-1][1:]
                self.flows[data_inc[i][2]-1].append(data_inc[i][3])
                #print(data_inc[i][3])
        print("Next dataset")
        self.line.setData(self.time, self.temperature)
        self.line_2.setData(self.time, self.flows[0])
        self.line_3.setData(self.time, self.flows[1])
        self.line_4.setData(self.time, self.flows[2])
        self.line_5.setData(self.time, self.flows[3])

    def the_button_was_clicked(self):
        print("Interlock reset")
        self.comPort.write(b'O')
        #print(time.time())

    def save_to_csv(self):
        filename = 'plot_data.csv'
        with open(filename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
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