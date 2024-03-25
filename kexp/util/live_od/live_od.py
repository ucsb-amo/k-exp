import numpy as np
import sys
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QComboBox)
from PyQt6.QtGui import QIcon, QFont
from queue import Queue

from kexp.util.live_od.live_od_plotting import *

from kexp.util.live_od.camera_mother import CameraMother, CameraBaby, DataHandler, CameraNanny
from kexp.util.live_od.camera_connection_widget import CamConnBar, ROISelector

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.queue = Queue()
        self.camera_nanny = CameraNanny()
        self.camera_mother = CameraMother(start_watching=False,
                                           manage_babies=False,
                                           output_queue=self.queue,
                                             camera_nanny=self.camera_nanny,
                                               N_runs=1)
        self.setup_widgets()
        self.setup_layout()

        self.camera_mother.new_camera_baby.connect(self.create_camera_baby)
        self.camera_mother.start()

        self.img_count = 0

    def create_camera_baby(self,file,name):
        self.the_baby = CameraBaby(file, name, self.queue,
                                   self.camera_nanny)
        self.data_handler = DataHandler(self.queue,data_filepath=file)

        self.the_baby.camera_grab_start.connect(self.grab_start_msg)
        self.the_baby.camera_grab_start.connect(self.data_handler.get_img_number)
        self.the_baby.camera_grab_start.connect(self.data_handler.start)

        self.the_baby.image_captured.connect(self.gotem_msg)

        self.data_handler.got_image_from_queue.connect(self.analyzer.got_img)
        self.data_handler.got_image_from_queue.connect(self.count_images)

        self.the_baby.honorable_death_signal.connect(lambda: self.msg(f'Run complete. {name} has died honorably.'))
        self.the_baby.dishonorable_death_signal.connect(lambda: self.msg(f'{name} has died dishonorably. Incomplete data deleted.'))
        
        self.the_baby.honorable_death_signal.connect(self.camera_mother.start)
        self.the_baby.dishonorable_death_signal.connect(self.camera_mother.start)

        self.the_baby.honorable_death_signal.connect(self.reset_plotter)
        self.the_baby.dishonorable_death_signal.connect(self.reset_plotter)

        self.the_baby.start()

    def reset_plotter(self):
        self.analyzer.imgs = []
        self.img_count = 0

    def setup_widgets(self):

        font = QFont()
        font.setPointSize(16)
        self.output_window = QPlainTextEdit()
        self.output_window.setFont(font)
        self.output_window.setReadOnly(True)

        self.camera_conn_bar = CamConnBar(self.camera_nanny,self.output_window)
        
        self.roi_select = ROISelector()
        self.roi_select.crop_dropdown.currentIndexChanged.connect(self.update_crop)

        self.viewer_window = ODviewer()
        self.analyzer = Analyzer()

        self.plotter = Plotter(self.viewer_window,self.analyzer)
        self.roi_select.crop_dropdown.currentIndexChanged.connect(self.plotter.clear)

    def setup_layout(self):
        self.layout = QVBoxLayout()

        self.top_row = QHBoxLayout()
        self.top_row.addWidget(self.camera_conn_bar)
        self.top_row.addWidget(self.roi_select)
        self.layout.addLayout(self.top_row)
        self.layout.addWidget(self.viewer_window)
        self.layout.addWidget(self.output_window)

        self.setLayout(self.layout)

    def count_images(self):
        self.img_count += 1
        if self.img_count == 3:
            self.plotter.run()
            self.msg('new OD!')
            self.img_count = 0

    def update_crop(self):
        self.analyzer.crop_type = self.roi_select.crop_dropdown.currentText()

    def msg(self,msg):
        self.output_window.appendPlainText(msg)

    def grab_start_msg(self,Nimg):
        self.N_img = Nimg
        msg = f"Camera grabbing... Expecting {Nimg} images."
        self.msg(msg)

    def gotem_msg(self,count):
        msg = f"gotem (img {count}/{self.N_img})"
        self.msg(msg)

# Maybe hard, need to iterate through xvars in same order that the data is being taken
# or, once have communication working, just send over the xvars real time
#
# class XvarViewer(QWidget):
#     def __init__(self,):
#         super().__init__()
    
#     def setup_layout(self):
#         self.layout = QVBoxLayout()
#         label = QLabel("xvars")

def main():
    app = QApplication(sys.argv)
    window = QWidget()

    # Set the style
    # app.setStyle("Fusion")  # Set the style to Fusion

    mainwindow = MainWindow()
    app.aboutToQuit.connect(mainwindow.camera_nanny.close_all)
    window.setLayout(mainwindow.layout)
    window.setWindowTitle("LiveOD")
    window.setWindowIcon(QIcon('banana-icon.png'))

    # Set the window position at the top of the screen
    window.setGeometry(window.x(), 0, window.width(), window.height())
    window.setFixedSize(800,1370)

    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()