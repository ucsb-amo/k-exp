
from PyQt6.QtWidgets import (QLabel, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QPlainTextEdit)

from kexp.util.live_od.live_od_plotting import *

import kexp.config.camera_params as cp
from kexp.control.cameras.dummy_cam import DummyCamera
from kexp.util.live_od import CameraNanny

from kexp.analysis.roi import ROI_CSV_PATH
import pandas as pd

class CamConnBar(QWidget):
    def __init__(self,camera_nanny,output_window):
        super().__init__()
        self.cn = camera_nanny
        self.output_window = output_window
        self.setup_camera_buttons()
        self.setup_layout()

    def setup_camera_buttons(self):
        self.xy_basler_button = CameraButton(cp.xy_basler_params,self.cn,self.output_window)
        self.xy2_basler_button = CameraButton(cp.xy2_basler_params,self.cn,self.output_window)
        self.x_basler_button = CameraButton(cp.x_basler_params,self.cn,self.output_window)
        self.z_basler_button = CameraButton(cp.z_basler_params,self.cn,self.output_window)
        self.andor = CameraButton(cp.andor_params,self.cn,self.output_window,open_camera_on_start=False)

    def setup_layout(self):
        self.layout = QVBoxLayout()
        label = QLabel("Camera connections")
        buttonlayout = QHBoxLayout()
        buttonlayout.addWidget(self.xy_basler_button)
        buttonlayout.addWidget(self.xy2_basler_button)
        buttonlayout.addWidget(self.z_basler_button)
        buttonlayout.addWidget(self.x_basler_button)
        buttonlayout.addWidget(self.andor)
        self.layout.addWidget(label)
        self.layout.addLayout(buttonlayout)
        self.setLayout(self.layout)

class CameraButton(QPushButton):
    def __init__(self,camera_params:cp.CameraParams,
                 camera_nanny:CameraNanny,
                 output_window:QPlainTextEdit,
                 open_camera_on_start:bool=False):
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
        self.load_roi_from_spreadsheet()
        self.crop_dropdown.addItems(self.roi_keys)
        
    def load_roi_from_spreadsheet(self):
        roicsv = pd.read_excel(ROI_CSV_PATH)
        self.roi_keys = roicsv['key'].to_list()

    def set_dropdown_to_key(self,key):
        idx = self.roi_keys.index(key)
        self.crop_dropdown.setCurrentIndex(idx)
        
    def setup_layout(self):
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.crop_dropdown)
        self.setLayout(self.layout)
