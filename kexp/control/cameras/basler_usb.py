from pypylon import pylon
from artiq.experiment import *
import numpy as np

from queue import Queue
from PyQt6.QtCore import QThread, pyqtSignal

from kexp.config.camera_id import cameras
from kexp.config.timeouts import (CAMERA_GRAB_TIMEOUT_BASLER_INIT as TIMEOUT_INIT,
                                  CAMERA_GRAB_TIMEOUT_BASLER_RUN as TIMEOUT_RUN)

def nothing():
    return False

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
    def __init__(self,ExposureTime=0.,Gain=0.,TriggerSource='Line1',TriggerMode='On',BaslerSerialNumber=cameras.xy_basler.serial_no):

        super().__init__()

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
        
        self.set_exposure(ExposureTime)
        self.set_gain(Gain)

    def set_exposure(self,ExposureTime):
        ExposureTime_us = ExposureTime * 1.e6
        if ExposureTime_us < self.ExposureTime.GetMin():
            ExposureTime_us = self.ExposureTime.GetMin()
            print(f"Exposure time requested is below camera minimum. Setting to minimum exposure : {ExposureTime_us:1.0f} us")
        if ExposureTime_us > self.ExposureTime.GetMax():
            ExposureTime_us = self.ExposureTime.GetMax()
            print(f"Exposure time requested is above camera maximum. Setting to maximum exposure : {ExposureTime_us:1.0f} us")
        self.ExposureTime.SetValue(ExposureTime_us)

    def set_gain(self,Gain):
        if Gain > self.Gain.GetMax():
            Gain = self.Gain.GetMax()
            print(f"Gain requested is above camera maximum. Setting to maximum gain : {Gain:1.0f} dB")
        if Gain > self.Gain.GetMax():
            Gain = self.Gain.GetMin()
            print(f"Gain requested is below camera minimum. Setting to minimum gain : {Gain:1.0f} dB")
        self.Gain.SetValue(Gain)

    def close(self):
        self.Close()

    def open(self):
        self.Open()
    
    def is_opened(self):
        return self.IsOpen()
    
    def start_grab(self,N_img,output_queue:Queue,
                   check_interrupt_method=nothing):
        this_timeout = TIMEOUT_INIT # initial timeout
        Nimg = int(N_img)
        self.StartGrabbingMax(Nimg, pylon.GrabStrategy_LatestImages)
        count = 0
        while self.IsGrabbing():
            if check_interrupt_method():
                break
            grab = self.RetrieveResult(int(this_timeout*1000), pylon.TimeoutHandling_ThrowException)
            if grab.GrabSucceeded():
                this_timeout = TIMEOUT_RUN
                print(f'gotem (img {count+1}/{Nimg})')
                img = np.uint8(grab.GetArray())
                img_t = grab.TimeStamp
                output_queue.put((img,img_t,count))
                count += 1
            if count >= Nimg:
                break
        self.StopGrabbing()

    def stop_grab(self):
        try:
            self.StopGrabbing()
        except Exception as e:
            print(f"Error stopping grab: {e}")
            pass