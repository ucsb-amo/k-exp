import numpy as np
import sys
from PyQt6.QtWidgets import (
    QApplication, QLabel, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QPlainTextEdit, QComboBox)
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal, QThread
from PyQt6.QtGui import QIcon
from queue import Queue

from kexp.util.data.camera_mother import CameraMother, CameraBaby, DataHandler
import kexp.config.camera_params as cp
from kexp.control.cameras.dummy_cam import DummyCamera
from kexp.control.cameras.camera_nanny import CameraNanny

import matplotlib
matplotlib.use('QtAgg')
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from kexp.analysis.image_processing import compute_ODs
import kexp.analysis.image_processing.roi_select as roi

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.queue = Queue()
        self.camera_mother = CameraMother(start_watching=False, manage_babies=False, output_queue=self.queue)
        self.camera_nanny = self.camera_mother.camera_nanny
        self.setup_widgets()
        self.setup_layout()

        self.analyzer = Analyzer()
        self.plotter = Plotter(self.viewer_window,self.analyzer)

        self.camera_mother.new_camera_baby.connect(self.create_camera_baby)
        self.camera_mother.start()

        self.img_count = 0

    def create_camera_baby(self,file,name):
        self.the_baby = CameraBaby(file, name, self.queue,
                                   self.camera_nanny)
        self.data_handler = DataHandler(self.queue,dataset_path=file)

        self.the_baby.camera_grab_start.connect(self.grab_start_msg)

        self.the_baby.image_captured.connect(self.data_handler.start)
        self.the_baby.image_captured.connect(self.gotem_msg)

        self.data_handler.got_image_from_queue.connect(self.analyzer.got_img)
        self.data_handler.got_image_from_queue.connect(self.count_images)

        self.the_baby.death_signal.connect(self.camera_mother.start)

        self.the_baby.run()

    def setup_widgets(self):
        self.conn_bar = CamConnBar(self.camera_nanny)
        
        self.crop_dropdown = QComboBox()
        self.crop_dropdown.addItems(['bigmot','mot','cmot','gm',
                                         'gm2','lightsheet','lightsheet_long',
                                         'lightsheet_short','tweezer'])
        self.crop_dropdown.currentIndexChanged.connect(self.update_crop)

        self.viewer_window = ODviewer()

        self.output_window = QPlainTextEdit()

    def setup_layout(self):
        self.layout = QVBoxLayout()

        self.top_row = QHBoxLayout()
        self.top_row.addWidget(self.conn_bar)
        self.top_row.addWidget(self.crop_dropdown)
        self.layout.addLayout(self.top_row)

        self.layout.addWidget(self.viewer_window)

        self.layout.addWidget(self.output_window)

        self.setLayout(self.layout)

    def count_images(self):
        self.img_count += 1
        if self.img_count == 3:
            self.plotter.run()
            self.img_count = 0

    def update_crop(self):
        self.analyzer.crop_type = self.crop_dropdown.currentText()

    def msg(self,msg):
        self.output_window.appendPlainText(msg)

    def grab_start_msg(self,Nimg):
        self.N_img = Nimg
        msg = f"Camera grabbing... Expecting {Nimg} images."
        self.msg(msg)

    def gotem_msg(self,count):
        msg = f"gotem (img {count}/{self.N_img})"
        self.msg(msg)

class Analyzer():

    def __init__(self):
        self.imgs = []
        self.crop_type = ''

    def got_img(self,img):
        self.imgs.append(np.asarray(img))
        if len(self.imgs) == 3:
            self.analyze()
            self.imgs = []

    def analyze(self):
        self.img_atoms = self.imgs[0]
        self.img_light = self.imgs[1]
        self.img_dark = self.imgs[2]

        self.fix_datatype()

        self.od_raw, self.od, self.sum_od_x, self.sum_od_y = \
            compute_ODs(self.img_atoms,
                        self.img_light,
                        self.img_dark,
                        self.crop_type)

    def fix_datatype(self):
        dtype = self.img_atoms.dtype
        if dtype == np.dtype('uint8'):
            self.img_atoms = self.img_atoms.astype(np.int16)
            self.img_light = self.img_light.astype(np.int16)
            self.img_dark = self.img_dark.astype(np.int16)
        elif dtype == np.dtype('uint16'):
            self.img_atoms = self.img_atoms.astype(np.int32)
            self.img_light = self.img_light.astype(np.int32)
            self.img_dark = self.img_dark.astype(np.int32)

class ODviewer(QWidget):
    def __init__(self):
        super().__init__()
        self.setup_widgets()
        self.setup_layout()

    def setup_widgets(self):
        self.img_atoms_plot = PlotPanel()
        self.img_light_plot = PlotPanel()
        self.img_dark_plot = PlotPanel()

        self.od_plot = PlotPanel()
        self.sum_od_x_plot = PlotPanel()
        self.sum_od_y_plot = PlotPanel()
    
    def setup_layout(self):
        self.layout = QGridLayout()
        self.layout.addWidget(self.img_atoms_plot,0,0,1,1)
        self.layout.addWidget(self.img_light_plot,0,1,1,1)
        self.layout.addWidget(self.img_dark_plot,0,2,1,1)
        self.layout.addWidget(self.od_plot,1,0,2,2)
        self.layout.addWidget(self.sum_od_y_plot,1,2,2,1)
        self.layout.addWidget(self.sum_od_x_plot,3,0,1,2)
        self.setLayout(self.layout)

class Plotter(QThread):
    def __init__(self,plotwindow:ODviewer,analyzer:Analyzer):
        super().__init__()
        self.plotwindow = plotwindow
        self.analyzer = analyzer

    def run(self):
        self.plotwindow.img_atoms_plot.imshow(self.analyzer.img_atoms)
        self.plotwindow.img_light_plot.imshow(self.analyzer.img_atoms)
        self.plotwindow.img_dark_plot.imshow(self.analyzer.img_dark)
        self.plotwindow.od_plot.imshow(self.analyzer.od)
        self.plotwindow.sum_od_x_plot.plot(self.analyzer.sum_od_x)
        self.plotwindow.sum_od_y_plot.plot(self.analyzer.sum_od_y)

class AtomHistory(QWidget):
    def __init__(self):
        super().__init__()

class PlotPanel(FigureCanvasQTAgg):
    def __init__(self):
        fig = Figure()
        self.axes = fig.add_subplot(111)
        super(FigureCanvasQTAgg,self).__init__(fig)
        self._plot_ref = None

    def process_imgs(self):
        pass
        
    def imshow(self,img):
        if self._plot_ref == None:
            self._plot_ref = self.axes.imshow(img)
        else:
            self._plot_ref.set_data(img)
        self.draw()

    def plot(self,ydata):
        if self._plot_ref == None:
            self._plot_ref, = self.axes.plot(ydata)
        else:
            self._plot_ref.set_ydata(ydata)
        self.draw()

# Maybe hard, need to iterate through xvars in same order that the data is being taken
# or, once have communication working, just send over the xvars real time
#
# class XvarViewer(QWidget):
#     def __init__(self,):
#         super().__init__()
    
#     def setup_layout(self):
#         self.layout = QVBoxLayout()
#         label = QLabel("xvars")

class CamConnBar(QWidget):
    def __init__(self,camera_nanny):
        super().__init__()
        self.cn = camera_nanny
        self.setup_camera_buttons()
        self.setup_layout()

    def setup_camera_buttons(self):
        self.xy_basler_button = CameraButton(cp.xy_basler_params,self.cn)
        self.z_basler_button = CameraButton(cp.z_basler_params,self.cn)
        # self.andor = CameraButton(cp.andor_params,self.cn)

    def setup_layout(self):
        self.layout = QHBoxLayout()
        self.layout.addWidget(self.xy_basler_button)
        self.layout.addWidget(self.z_basler_button)
        # self.layout.addWidget(self.andor)
        self.setLayout(self.layout)

class CameraButton(QPushButton):
    def __init__(self,camera_params:cp.CameraParams,
                 camera_nanny:CameraNanny):
        super().__init__()
        self.camera_params = camera_params
        self.camera_name = self.camera_params.camera_select
        self.cn = camera_nanny
        self.camera = DummyCamera
        
        self.setText(self.camera_name)
        self.open_camera()

        self.is_grabbing = False

        self.clicked.connect(self.button_pressed)

    def button_pressed(self):
        if self.camera.is_opened():
            self.close_camera()
        else:
            self.open_camera()
    
    def close_camera(self):
        if self.camera.is_opened():
            self._set_color_closed()
            self.camera.close()

    def open_camera(self):
        self._set_color_loading()
        camera = self.cn.get_camera(self.camera_params)
        if type(camera) == DummyCamera:
            self._set_color_failed()
        elif camera.is_opened():
            self._set_color_success()
        self.camera = camera

    def toggle_grabbing(self,success_bool=True):
        self.is_grabbing = not self.is_grabbing
        if self.is_grabbing:
            self._set_color_grabbing()
        elif not success_bool:
            self._set_color_failed()
        else:
            self._set_color_success()

    def _set_color_loading(self):
        self.setStyleSheet("background-color: yellow")

    def _set_color_failed(self):
        self.setStyleSheet("background-color: red")

    def _set_color_success(self):
        self.setStyleSheet("background-color: green")

    def _set_color_grabbing(self):
        self.setStyleSheet("background-color: blue")

    def _set_color_closed(self):
        self.setStyleSheet("background-color: gray")

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

    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()