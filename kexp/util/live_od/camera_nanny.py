from kexp.control.cameras.dummy_cam import DummyCamera
from kexp.control.cameras.basler_usb import BaslerUSB
from kexp.control.cameras.andor import AndorEMCCD

from kexp.config import camera_params

import numpy as np
import pypylon.pylon as py

import time

CHECK_EVERY = 0.2
CHECK_PERIOD = 2.0
N_NOTIFY = CHECK_PERIOD // CHECK_EVERY
    
class CameraNanny():

    def persistent_get_camera(self,camera_params) -> DummyCamera:
        got_camera = False
        count = 1
        while not got_camera:
            camera = self.get_camera(camera_params)
            if type(camera) == DummyCamera:
                count += 1
                time.sleep(CHECK_PERIOD)
                if np.mod(count,N_NOTIFY) == 0:
                    count = 1
                    print("Can't reach camera. Make it available to continue, or Ctrl+C to stop the process.")
            else:
                return camera

    def get_camera(self,camera_params:camera_params.CameraParams) -> DummyCamera:
        camera_select = camera_params.camera_select
        need_to_open = True
        if type(camera_select) == bytes: 
            camera_select = camera_select.decode()
        if camera_select in self.__dict__.keys():
            camera = vars(self)[camera_select]
            need_to_open = not camera.is_opened()
        if need_to_open:
            camera = self.open(camera_params)
            if type(camera) != DummyCamera:
                vars(self)[camera_select] = camera
        return camera

    def open(self,camera_params:camera_params.CameraParams):
        camera_type = camera_params.camera_type
        if type(camera_type) == bytes: 
            camera_type = camera_type.decode()
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
        return camera
    
    def close_all(self):
        for k in vars(self).keys():
            obj = vars(self)[k]
            if type(obj) == BaslerUSB or type(obj) == AndorEMCCD:
                try:
                    obj.close()
                except Exception as e:
                    print(e)
                    print(f"An error occurred closing camera {k}.")

    