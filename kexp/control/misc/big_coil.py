from kexp.control.artiq.DAC_CH import DAC_CH
from kexp.control.artiq.TTL import TTL
from kexp.config import ExptParams
from artiq.experiment import kernel, delay, parallel
import numpy as np

dv = -1.
dv_list = np.linspace(0.,1.,5)

class igbt_magnet():
    def __init__(self, v_control_dac:DAC_CH, i_control_dac:DAC_CH, igbt_ttl:TTL, expt_params:ExptParams):
        self.v_control_dac = v_control_dac
        self.i_control_dac = i_control_dac
        self.igbt_ttl = igbt_ttl
        self.params = expt_params

    def on(self,pretrigger=True):
        if pretrigger:
            delay(-self.params.t_keysight_analog_response)
        with parallel:
            self.v_control_dac.set(v=3.)
            self.igbt_ttl.on()

    def off(self):
        self.igbt_ttl.off()
        self.v_control_dac.set(v=0.)

class hbridge_magnet(igbt_magnet):
    def __init__(self, v_control_dac:DAC_CH, i_control_dac:DAC_CH,
                 hbridge_ttl:TTL, igbt_ttl:TTL,
                 expt_params:ExptParams):
        super().__init__(v_control_dac,i_control_dac,igbt_ttl,expt_params)
        self.v_control_dac = v_control_dac
        self.i_control_dac = i_control_dac
        self.igbt_ttl = igbt_ttl
        self.h_bridge_ttl = hbridge_ttl
        self.params = expt_params

    def switch_to_helmholtz(self):
        self.off()
        delay(self.params.t_hbridge_switch_delay)
        self.h_bridge_ttl.on()

    def switch_to_antihelmholtz(self):
        self.off()
        delay(self.params.t_hbridge_switch_delay)
        self.h_bridge_ttl.off()