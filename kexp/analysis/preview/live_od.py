import numpy as np
import sys
from subprocess import PIPE, run
from PyQt6.QtWidgets import (
    QApplication, QLabel, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton)
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QIcon

from kexp.util.data.camera_mother import CameraMother
import kexp.config.camera_params as cp
from kexp.control.cameras.dummy_cam import DummyCamera
from kexp.control.cameras.camera_nanny import CameraNanny

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.camera_mother = CameraMother()
        self.camera_nanny = self.camera_mother.camera_nanny

class CamConnBar(QWidget):
    def __init__(self,camera_nanny):
        super().__init__()
        self.cn = camera_nanny

    def setup_camera_buttons(self):
        self.xy_basler_button = CameraButton(cp.xy_basler_params,self.cn)
        self.z_basler_button = CameraButton(cp.z_basler_params,self.cn)
        self.andor = CameraButton(cp.andor_params,self.cn)

    def setup_layout(self):
        self.layout = QHBoxLayout()
        self.layout.addWidget(self.xy_basler_button)
        self.layout.addWidget(self.z_basler_button)
        self.layout.addWidget(self.andor)

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
        self.open_bool = False

    def setup_button_press(self):
        if self.camera.is_opened():
            self.close_camera()
        else:
            self.open_camera()
    
    def close_camera(self):
        if self.camera.is_opened():
            self.camera.close()

    def open_camera(self):
        self._set_color_loading()
        camera = self.cn.get_camera()
        if type(camera == DummyCamera):
            self._set_color_failed()
        elif camera.is_opened():
            self._set_color_open()
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