from waxx.control.misc.moglabs import MOGDevice
from waxx.control.misc.moglabs_wavemeter import WavemeterClient as WavemeterWaxx, WavemeterController, DummyWavemeterController, DummyWavemeterClient
from kexp.config.ip import WAVEMETER_MOGLABS_IP

LOCK_TOLERANCE = 15.e6

class Wavemeter(WavemeterWaxx):
    def __init__(self,
                 ch,target_freq,
                 wavemeter_device: WavemeterController,
                 locked_tolerance=LOCK_TOLERANCE):
        super().__init__(ch,target_freq,wavemeter_device,locked_tolerance)

class fzw_frame():
    def __init__(self):
        try:
            _fzw = WavemeterController(WAVEMETER_MOGLABS_IP)
            self.ry_405 = Wavemeter(ch=2, target_freq=741.09120e12,
                        wavemeter_device=_fzw)
            self.ry_980 = Wavemeter(ch=5, target_freq=307.45730e12,
                                    wavemeter_device=_fzw)
        except:
            print('Failed to connect to wavemeter -- please close wavemeter software if it is open. Lock status will not be checked.')
            self.ry_405 = DummyWavemeterClient()
            self.ry_980 = DummyWavemeterClient()

    def write_keys(self):
        for key in self.__dict__.keys():
            if isinstance(self.__dict__[key], Wavemeter):
                self.__dict__[key].key = key