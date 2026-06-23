from waxx.control.misc.moglabs import MOGDevice
from waxx.control.misc.moglabs_wavemeter import WavemeterClient as WavemeterWaxx, WavemeterController, DummyWavemeterController, DummyWavemeterClient
from kexp.config.ip import WAVEMETER_MOGLABS_IP
from kexp.config.expt_params import ExptParams

LOCK_TOLERANCE = 30.e6

class Wavemeter(WavemeterWaxx):
    def __init__(self,
                 ch,target_freq,
                 wavemeter_device: WavemeterController,
                 locked_tolerance=LOCK_TOLERANCE):
        super().__init__(ch,target_freq,wavemeter_device,locked_tolerance)

class fzw_frame():
    def __init__(self, params=ExptParams()):

        p = params

        try:
            self._fzw = WavemeterController(WAVEMETER_MOGLABS_IP)
        except:
            print('Failed to connect to wavemeter -- please close wavemeter software if it is open. Lock status will not be checked.')
            self._fzw = DummyWavemeterController()

        self.ry_405 = self.add_wavemeter(2, target_frequency=p.frequency_target_405_lock)
        self.ry_980 = self.add_wavemeter(5, target_frequency=p.frequency_target_980_lock)

        self.write_keys()

    def write_keys(self):
        for key in self.__dict__.keys():
            if isinstance(self.__dict__[key], Wavemeter):
                self.__dict__[key].key = key

    def add_wavemeter(self, ch, target_frequency) -> Wavemeter:
        if isinstance(self._fzw, WavemeterController):
            return Wavemeter(ch=ch, target_freq=target_frequency,
                        wavemeter_device=self._fzw)
        else:
            return DummyWavemeterClient()