from artiq.coredevice.grabber import Grabber as grabber_artiq, OutOfSyncException, GrabberTimeoutException
from artiq.coredevice.rtio import rtio_output, rtio_input_timestamped_data
from artiq.language import delay, kernel
import numpy as np
from kexp.util.artiq.async_print import aprint

T_GRABBER_SETUP = 10.e-6

db = 100

class NoGrabberROIsException(Exception):
    """Raised when the ROI read is called but no ROIs have been set up."""
    pass

class Grabber(grabber_artiq):
    kernel_invariants = {"_channel_base", "_sentinel"}
    def __init__(self, expt):

        self.init_grabber(expt)

        self._roi_counter = -1
        self._gate_on = False

        self.timestamps = np.zeros((16),dtype=np.int64)
        self.data = np.zeros((16),dtype=np.int32)

    def init_grabber(self,expt):
        self.grabber_device:grabber_artiq = expt.get_device("grabber0")
        self._sentinel = self.grabber_device.sentinel
        self._channel_base = self.grabber_device.channel_base
        
    @kernel
    def setup_roi(self,x0,y0,x1,y1):
        self._roi_counter = self._roi_counter + 1
        self.grabber_device.setup_roi(self._roi_counter,
                                      x0,y0,x1,y1)
        delay(T_GRABBER_SETUP)

    @kernel
    def gate_roi(self,mask=db):
        if mask == db:
            if self._gate_on:
                mask = 0
            else:
                mask = (2 << self._roi_counter) - 1
        self.grabber_device.gate_roi(mask)
        self._gate_on = (mask > 0)
        
    @kernel
    def read_roi(self, timeout_mu=-1):
        """
        Retrieves the accumulated values for one frame from the ROI engines.
        Blocks until values are available or timeout is reached.
        
        If the timeout is reached before data is available, the exception
        :exc:`GrabberTimeoutException` is raised.

        :param timeout_mu: Timestamp at which a timeout will occur. Set to -1
                           (default) to disable timeout. 
        """
        if self._roi_counter == -1:
            raise NoGrabberROIsException
        
        channel = self.grabber_device.channel_base + 1

        timestamp, sentinel = rtio_input_timestamped_data(timeout_mu, channel)
        if timestamp == -1:
            raise GrabberTimeoutException("Timeout before Grabber frame available")
        if sentinel != self.grabber_device.sentinel:
            raise OutOfSyncException

        for i in range(self._roi_counter+1):
            timestamp, roi_output = rtio_input_timestamped_data(timeout_mu, channel)
            if roi_output == self.grabber_device.sentinel:
                raise OutOfSyncException
            if timestamp == -1:
                raise GrabberTimeoutException(
                    "Timeout retrieving ROIs (attempting to read more ROIs than enabled?)")
            self.data[i] = roi_output
            self.timestamps[i] = timestamp