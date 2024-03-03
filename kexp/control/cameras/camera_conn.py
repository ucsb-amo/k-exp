from kexp.control.cameras.dummy_cam import DummyCamera
from kexp.control.cameras.basler_usb import BaslerUSB
from kexp.control.cameras.andor import AndorEMCCD

from kexp.config import camera_params

from numpy import np
import pypylon.pylon as py
    
class CameraConn():
    def __init__(self):
        super().__init__(self)
        self.camera_db = dict()

    def get_camera(self,camera_params:camera_params.CameraParams):
        camera_select = camera_params.camera_select
        if camera_select in self.camera_db.keys():
            camera = self.camera_db[camera_select]
        else:
            print("")
            try:
                self.open(camera_params)
            except Exception as e:
                print(e)
                print(f"There was an issue opening the requested camera (key: {camera_select}).")
            

    def open(self,camera_params:camera_params.CameraParams):
        camera_type = camera_params.camera_type
        if type(camera_type) == bytes: camera_type = camera_type.decode()

        if camera_type == "basler":
            camera = BaslerUSB(BaslerSerialNumber=camera_params.serial_no,
                                ExposureTime=camera_params.exposure_time)
        elif camera_type == "andor":
            camera = AndorEMCCD(ExposureTime=camera_params.exposure_time,
                                gain = camera_params.em_gain,
                                vs_speed=camera_params.vs_speed,
                                vs_amp=camera_params.vs_amp)
        self.camera_db[camera_params.camera_select] = camera
        return camera
    
    def close_all(self):
        for camera in self.cameras:
            camera.close()

    