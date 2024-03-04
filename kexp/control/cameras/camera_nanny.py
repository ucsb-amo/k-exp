from kexp.control.cameras.dummy_cam import DummyCamera
from kexp.control.cameras.basler_usb import BaslerUSB
from kexp.control.cameras.andor import AndorEMCCD

from kexp.config import camera_params

import numpy as np
import pypylon.pylon as py
    
class CameraNanny():
    def __init__(self):
        super().__init__()
        self.camera_db = dict()

    def get_camera(self,camera_params:camera_params.CameraParams):
        camera_select = camera_params.camera_select
        if camera_select in self.camera_db.keys():
            camera = self.camera_db[camera_select]
            not_open = not camera.is_opened()
        else:
            not_open = True
        if not_open:
            camera = self.open(camera_params)
        return camera

    def open(self,camera_params:camera_params.CameraParams):
        camera_type = camera_params.camera_type
        if type(camera_type) == bytes: camera_type = camera_type.decode()

        try:
            if camera_type == "basler":
                camera = BaslerUSB(BaslerSerialNumber=camera_params.serial_no,
                                    ExposureTime=camera_params.exposure_time)
            elif camera_type == "andor":
                camera = AndorEMCCD(ExposureTime=camera_params.exposure_time,
                                    gain = camera_params.em_gain,
                                    vs_speed=camera_params.vs_speed,
                                    vs_amp=camera_params.vs_amp)
        except Exception as e:
            camera = DummyCamera()
            print(e)
            print(f"There was an issue opening the requested camera (key: {camera_params.camera_select}).")
        self.camera_db[camera_params.camera_select] = camera
        return camera
    
    def close_all(self):
        cameras = self.camera_db
        for k in self.camera_db:
            if cameras[k].is_opened():
                try:
                    cameras[k].close()
                except Exception as e:
                    print(e)
                    print(f"An error occurred closing camera {k}.")

    