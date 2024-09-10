import numpy as np
from artiq.experiment import kernel, portable

from artiq.coredevice.zotino import Zotino
from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

from kexp.control.artiq.Shuttler_CH import Shuttler_CH

class shuttler_frame():
    def __init__(self):

        ### Setup

        self._STATE_BASE = np.array([1<<n for n in range(16)])

        self.shuttler_list = []
        self._relay_state = np.zeros(16,dtype=int)

        self._config = Config
        self._trigger = Trigger
        self._relay = Relay

        ### Channel assignment

        self.tweezer_mod = self._assign_ch(1)

        ###

        self._write_dds_keys()

    def _write_dds_keys(self):
        '''Adds the assigned keys to the DDS objects so that the user-defined
        names (keys) are available with the DDS objects.'''
        for key in self.__dict__.keys():
            if isinstance(self.__dict__[key],Shuttler_CH):
                self.__dict__[key].key = key

    def _assign_ch(self,ch) -> Shuttler_CH:
        shuttler_ch = Shuttler_CH(ch, relay_state=self._relay_state)
        shuttler_ch._relay = self._relay
        shuttler_ch._trigger = self._trigger
        self.shuttler_list.append(shuttler_ch)
        return shuttler_ch
    
    @portable
    def _relay_state_to_int(self):
        return self._STATE_BASE @ self._relay_state

    @kernel
    def update_relay(self,chs,states):
        self._relay_state[chs] = states
        self._relay.enable(self._relay_state_to_int())

    @kernel
    def trigger(self):
        self._trigger(self._relay_state_to_int())

    @kernel
    def set_gain(self,ch,gain_mu):
        self._config.set_gain(ch,gain_mu)

    @kernel
    def init(self):
        for ch in range(16):
            self.set_gain(ch,0)
            delay(10.e-6)
        self._relay.init()