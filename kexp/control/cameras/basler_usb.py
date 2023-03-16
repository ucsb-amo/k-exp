from pypylon import pylon
from artiq.experiment import *

class BaslerUSB(pylon.InstantCamera):
    '''
    BaslerUSB is an InstantCamera object which initializes the connected Basler camera.
    Excercise caution if multiple cameras are connected.

    Args:
        ExposureTime (float): the exposure time in s. If below the minimum for the connected camera, sets to minimum value. (default: 0.)
        TriggerSource (str): picks the line that the camera triggers on. (default: 'Line1')
        TriggerMode (str): picks whether or not the camera waits for a trigger to capture frames. (default: 'On')
    '''
    def __init__(self,ExposureTime=0.,TriggerSource='Line1',TriggerMode='On'):

        super().__init__()

        ExposureTime_us = ExposureTime * 1.e6

        tl_factory = pylon.TlFactory.GetInstance()
        self.Attach(tl_factory.CreateFirstDevice())

        self.Open()

        self.UserSetSelector = "Default"
        self.UserSetLoad.Execute()

        self.LineSelector = TriggerSource
        self.LineMode = "Input"

        self.TriggerSelector = "FrameStart"
        self.TriggerMode = TriggerMode
        self.TriggerSource = TriggerSource
        if ExposureTime_us < self.ExposureTime.GetMin():
            ExposureTime = self.ExposureTime.GetMin()
        self.ExposureTime.SetValue(ExposureTime)

    def set_exposure_time(self,ExposureTime_s):
        self.ExposureTime = ExposureTime_s * 1.e6
        

