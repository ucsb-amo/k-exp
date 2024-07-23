
from PyQt6.QtWidgets import (QLabel, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QPlainTextEdit)

from kexp.util.live_od.live_od_plotting import *

import kexp.config.camera_params as cp
from kexp.control.cameras.dummy_cam import DummyCamera
from kexp.util.live_od import CameraNanny

class CamConnBar(QWidget):
    def __init__(self,camera_nanny,output_window):
        super().__init__()
        self.cn = camera_nanny
        self.output_window = output_window
        self.setup_camera_buttons()
        self.setup_layout()

    def setup_camera_buttons(self):
        self.xy_basler_button = CameraButton(cp.xy_basler_params,self.cn,self.output_window)
        self.z_basler_button = CameraButton(cp.z_basler_params,self.cn,self.output_window)
        self.andor = CameraButton(cp.andor_params,self.cn,self.output_window,open_camera_on_start=False)

    def setup_layout(self):
        self.layout = QVBoxLayout()
        label = QLabel("Camera connections")
        buttonlayout = QHBoxLayout()
        buttonlayout.addWidget(self.xy_basler_button)
        buttonlayout.addWidget(self.z_basler_button)
        buttonlayout.addWidget(self.andor)
        self.layout.addWidget(label)
        self.layout.addLayout(buttonlayout)
        self.setLayout(self.layout)

class CameraButton(QPushButton):
    def __init__(self,camera_params:cp.CameraParams,
                 camera_nanny:CameraNanny,
                 output_window:QPlainTextEdit,
                 open_camera_on_start:bool=True):
        super().__init__()
        self.camera_params = camera_params
        self.camera_name = self.camera_params.camera_select
        self.cn = camera_nanny
        self.camera = DummyCamera()
        self.output_window = output_window
        
        self.setText(self.camera_name)
        if open_camera_on_start:
            self.open_camera()

        self.is_grabbing = False

        self.clicked.connect(self.button_pressed)

    def msg(self,txt):
        self.output_window.appendPlainText(txt)

    def button_pressed(self):
        if self.camera.is_opened():
            self.close_camera()
            self.msg(f'Connection to {self.camera_params.camera_select} closed.')
        else:
            self.open_camera()
    
    def close_camera(self):
        if self.camera.is_opened():
            self._set_color_closed()
            self.camera.close()

    def open_camera(self):
        self._set_color_loading()
        camera = self.cn.get_camera(self.camera_params)
        if not camera.is_opened():
            self._set_color_failed()
            self.msg(f'Failed to open camera {self.camera_params.camera_select}')
        else:
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
        self.setStyleSheet("background-color: orchid")

    def _set_color_failed(self):
        self.setStyleSheet("background-color: red")

    def _set_color_success(self):
        self.setStyleSheet("background-color: green")

    def _set_color_grabbing(self):
        self.setStyleSheet("background-color: blue")

    def _set_color_closed(self):
        self.setStyleSheet("background-color: gray")

class ROISelector(QWidget):
    def __init__(self):
        super().__init__()
        self.setup_widgets()
        self.setup_layout()

    def setup_widgets(self):
        self.label = QLabel("ROI Selection")
        self.crop_dropdown = QComboBox()
        self.crop_dropdown.addItems(['','gm','mot','cmot','bigmot','lightsheet',
                                         'gm2','lightsheet_long',
                                         'lightsheet_short','xy_tweezer',
                                         'andor_single_tweezer_tight',
                                         'lightsheet_short','andor_single_tweezer','andor_lightsheet'])
        
    def setup_layout(self):
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.crop_dropdown)
        self.setLayout(self.layout)
