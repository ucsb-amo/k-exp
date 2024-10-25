import numpy as np
import sys
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QComboBox)
from PyQt6.QtGui import QIcon, QFont
from queue import Queue

from kexp.util.live_od.live_od_plotting import *

from kexp.util.live_od.camera_mother import CameraMother, CameraBaby, DataHandler, CameraNanny
from kexp.util.live_od.camera_connection_widget import CamConnBar, ROISelector

from kexp.analysis.roi import ROI

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

        self.last_camera = ""

        self.img_count = 0
        self.img_count_run = 0

    ### On new data, create CameraBaby object
    def create_camera_baby(self,file,name):
        self.the_baby = CameraBaby(file, name, self.queue,
                                   self.camera_nanny)
        self.data_handler = DataHandler(self.queue,data_filepath=file)

        self.the_baby.save_data_bool_signal.connect(self.data_handler.get_save_data_bool)

        self.the_baby.camera_connect.connect(self.check_new_camera) # checks for camera switch
        self.the_baby.camera_connect.connect(self.set_default_roi) # checks camera type

        ### what to do when the camera starts grabbing
        self.the_baby.camera_grab_start.connect(self.grab_start_msg) # post a message
        self.the_baby.camera_grab_start.connect(self.data_handler.get_img_number) # send N_imgs to expect
        self.the_baby.camera_grab_start.connect(self.plotter.plotwindow.get_img_number) # ditto
        self.the_baby.camera_grab_start.connect(self.data_handler.start) # open data to save images
        self.the_baby.camera_grab_start.connect(self.reset_count) # reset counting

        self.data_handler.got_image_from_queue.connect(self.analyzer.got_img) # tell analyzer that a new image is here
        self.data_handler.got_image_from_queue.connect(self.count_images) # increase image count for user display

        self.the_baby.honorable_death_signal.connect(lambda: self.msg(f'Run complete. {name} has died honorably.'))
        self.the_baby.dishonorable_death_signal.connect(lambda: self.msg(f'{name} has died dishonorably. Incomplete data deleted.'))
        
        self.the_baby.honorable_death_signal.connect(self.restart_mother)
        self.the_baby.dishonorable_death_signal.connect(self.restart_mother)

        # self.the_baby.honorable_death_signal.connect(self.reset)
        # self.the_baby.dishonorable_death_signal.connect(self.reset)

        self.the_baby.start()

    def restart_mother(self):
        import time
        time.sleep(0.25)
        self.camera_mother.start()

    ### Plotter and ROI handling

    def check_new_camera(self,camera_select):
        if self.last_camera != camera_select:
            self.plotter.clear()
            self.last_camera = camera_select
            self.set_default_roi(camera_select)

    def update_roi(self):
        roi_key = self.roi_select.crop_dropdown.currentText()
        self.analyzer.roi = ROI(roi_key)

    def set_default_roi(self,camera_select):
        if 'andor' in camera_select:
            key = 'andor_all'    
        if 'basler' in camera_select:
            key = 'basler_all'
        self.analyzer.roi = ROI(key,use_saved_roi=False,suppress_print=True)
        self.roi_select.set_dropdown_to_key(key)

    ### Plot counter

    def count_images(self):
        self.img_count += 1
        self.img_count_run += 1
        self.plotter.plotwindow.update_image_count(self.img_count_run)
        if self.img_count == 3:
            self.img_count = 0
        
    def reset_count(self):
        self.img_count = 0
        self.img_count_run = 0
        self.analyzer.imgs = []

    ### Printouts
    def msg(self,msg):
        self.output_window.appendPlainText(msg)

    def grab_start_msg(self,Nimg):
        self.N_img = Nimg
        msg = f"Camera grabbing... Expecting {Nimg} images."
        self.msg(msg)

    def gotem_msg(self,count):
        msg = f"gotem (img {count}/{self.N_img})"
        self.msg(msg)

    ### GUI layout and widgets setup
    def setup_widgets(self):
        font = QFont()
        font.setPointSize(16)
        self.output_window = QPlainTextEdit()
        self.output_window.setFont(font)
        self.output_window.setReadOnly(True)

        self.camera_conn_bar = CamConnBar(self.camera_nanny,self.output_window)
        
        self.roi_select = ROISelector()
        self.roi_select.crop_dropdown.currentIndexChanged.connect(self.update_roi)

        self.viewer_window = ODviewer()

        self.plotting_queue = Queue()
        self.analyzer = Analyzer(self.plotting_queue)
        self.plotter = Plotter(self.viewer_window,self.plotting_queue)
        self.plotter.start()

        self.analyzer.analyzed.connect(lambda: self.msg('new OD!'))
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
    # window.setFixedSize(800,1370)

    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()