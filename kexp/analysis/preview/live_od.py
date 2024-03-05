import numpy as np
import sys
from subprocess import PIPE, run
from PyQt6.QtWidgets import (
    QApplication, QLabel, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QTextBrowser)
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QIcon

from kexp.util.data.camera_mother import CameraMother
import kexp.config.camera_params as cp
from kexp.control.cameras.dummy_cam import DummyCamera
from kexp.control.cameras.camera_nanny import CameraNanny

from kexp.base.sub import Scanner

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.camera_mother = CameraMother(start_watching=False)
        self.camera_nanny = self.camera_mother.camera_nanny

        self.conn_bar = CamConnBar(self.camera_nanny)

        self.setup_layout()

    def setup_layout(self):
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.conn_bar)
        self.setLayout(self.layout)

class ODviewer(QWidget):
    def __init__(self):
        super().__init__()

class AtomHistory(QWidget):
    def __init__(self):
        super().__init__()

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