from pypylon import pylon
from artiq.experiment import *

from kexp.config.camera_params import basler_absorp_camera_params as bcp

class BaslerUSB(pylon.InstantCamera):
    '''
    BaslerUSB is an InstantCamera object which initializes the connected Basler camera.
    Excercise caution if multiple cameras are connected.

    Args:
        ExposureTime (float): the exposure time in s. If below the minimum for the connected camera, sets to minimum value. (default: 0.)
        TriggerSource (str): picks the line that the camera triggers on. (default: 'Line1')
        TriggerMode (str): picks whether or not the camera waits for a trigger to capture frames. (default: 'On')
        BaslerSerialNumber (str): identifies which camera should be used via the serial number. (default: ExptParams.basler_serial_no_absorption)
    '''
    def __init__(self,ExposureTime=0.,TriggerSource='Line1',TriggerMode='On',BaslerSerialNumber=bcp.serial_no):

        super().__init__()

        ExposureTime_us = ExposureTime * 1.e6

        tl_factory = pylon.TlFactory.GetInstance()
        if BaslerSerialNumber == '':
            self.Attach(tl_factory.CreateFirstDevice())
        else:
            di = pylon.DeviceInfo()
            di.SetSerialNumber(BaslerSerialNumber)
            self.Attach(tl_factory.CreateFirstDevice(di))

        self.Open()

        self.UserSetSelector = "Default"
        self.UserSetLoad.Execute()

        self.LineSelector = TriggerSource
        self.LineMode = "Input"

        self.TriggerSelector = "FrameStart"
        self.TriggerMode = TriggerMode
        self.TriggerSource = TriggerSource
        if ExposureTime_us < self.ExposureTime.GetMin():
            ExposureTime_us = self.ExposureTime.GetMin()
        self.ExposureTime.SetValue(ExposureTime_us)

    def set_exposure_time(self,ExposureTime_s):
        self.ExposureTime = ExposureTime_s * 1.e6

    def close(self):
        self.Close()
        

