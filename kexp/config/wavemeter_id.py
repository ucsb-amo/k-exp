from mogdevice import MOGDevice
from waxx.control.misc.moglabs_wavemeter import WavemeterClient as WavemeterWaxx, WavemeterController
from kexp.config.ip import WAVEMETER_MOGLABS_IP

LOCK_TOLERANCE = 600.e6

class Wavemeter(WavemeterWaxx):
    def __init__(self,
                 ch,target_freq,
                 wavemeter_device: WavemeterController,
                 locked_tolerance=LOCK_TOLERANCE):
        super().__init__(ch,target_freq,wavemeter_device,locked_tolerance)

class fzw_frame():
    def __init__(self):

        self._fzw = WavemeterController(WAVEMETER_MOGLABS_IP)
        self.ry_405 = Wavemeter(ch=2, target_freq=741.09000e12,
                                wavemeter_device=self._fzw)
        self.ry_980 = Wavemeter(ch=5, target_freq=307.45715e12,
                                wavemeter_device=self._fzw)

    def write_keys(self):
        for key in self.__dict__.keys():
            if isinstance(self.__dict__[key], Wavemeter):
                self.__dict__[key].key = key