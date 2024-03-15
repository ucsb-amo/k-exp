from pypylon import pylon
from artiq.experiment import *
import numpy as np

from kexp.config.camera_params import xy_basler_params

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
    def __init__(self,ExposureTime=0.,TriggerSource='Line1',TriggerMode='On',BaslerSerialNumber=xy_basler_params.serial_no):

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
            print(f"Exposure time requested is below camera minimum. Setting to minimum exposure : {ExposureTime_us:1.0f} us")
        self.ExposureTime.SetValue(ExposureTime_us)

    def close(self):
        self.Close()

    def open(self):
        self.Open()

    def grab(self,timeout_s=10):
        """Starts the camera waiting for a trigger to take a single image.

        Returns:
            grab_success (bool): A boolean indicating whether or not the frame grab was successful.
            img (np.ndarray): The frame that was grabbed. dtype = np.uint8.
            img_t (float): The timestamp of the grame that was grabbed.
        """        
        img = []
        img_t = []

        grab_result = self.GrabOne(int(timeout_s*1000))
        img = np.uint8(grab_result.GetArray())
        img_t = grab_result.TimeStamp

        return img, img_t
    
    def is_opened(self):
        return self.IsOpen()