from kexp.control.artiq.DDS import DDS
from kexp.control.artiq.mirny import Mirny
from kexp.control.artiq.TTL import TTL
from kexp.config import ExptParams
from artiq.experiment import kernel, delay, parallel, portable, TFloat
import numpy as np

dv = -0.1
dv_list = np.linspace(0.,1.,5)

class mixer_rf():
    def __init__(self, mirny_ch:Mirny, dds_ch:DDS, ttl_rf_sw:TTL, expt_params:ExptParams = ExptParams):
        self.mirny = mirny_ch
        self.dds = dds_ch
        self.rf_sw = ttl_rf_sw
        self.params = expt_params

    @kernel
    def init(self):
        self.rf_sw.off()
        self.mirny.init()
        self.mirny.set(frequency=self.params.frequency_mirny_carrier)
        self.mirny.on()
        self.dds.on()

    @kernel
    def set_rf(self,frequency=dv):
        if frequency == dv:
            frequency = self.params.frequency_rf_state_xfer_sweep_start
        freq_mirny = self.params.frequency_mirny_carrier
        freq_dds = freq_mirny - frequency
        # print(frequency,freq_mirny,freq_dds)
        if freq_dds < 0:
            freq_dds = -freq_dds
        self.dds.set_dds(frequency=freq_dds)

    @kernel
    def on(self):
        self.mirny.on()
        self.dds.on()
        self.rf_sw.on()

    @kernel
    def off(self):
        self.rf_sw.off()
        self.mirny.off()
        self.dds.off()

    @kernel
    def sweep(self,frequency_sweep_list=dv_list):
        """Sweeps the lower sideband freuqency over the specified range.

        The sweep time is controlled by ExptParams.t_rf_state_xfer_sweep, and
        the sweep step time is controlled by ExptParams.dt_rf_state_xfer_sweep.
        Adjust those to change the ramp times.

        Args:
            frequency_sweep_list (1D array, optional): The list of frequencies
            (in Hz) to be swept over.
        """        
        if frequency_sweep_list == dv_list:
            frequency_sweep_list = self.params.frequency_rf_state_xfer_sweep_list

        self.on()
        for f in frequency_sweep_list:
            self.set_rf(frequency=f)
            delay(self.params.dt_rf_state_xfer_sweep)
        self.off()

    