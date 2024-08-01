from kexp.control.artiq.DDS import DDS
from kexp.config import ExptParams
from artiq.experiment import kernel, delay, parallel, portable, TFloat
from artiq.experiment import *
import numpy as np

dv = -0.1
dv_list = np.linspace(0.,1.,5)

d_exptparams = ExptParams()

class doubled_rf():
    def __init__(self, dds_ch:DDS, expt_params:ExptParams = d_exptparams):
        self.dds = dds_ch
        self.params = expt_params

        self.params.frequency_rf_state_xfer_sweep_list = dv_list
        self.params.dt_rf_state_xfer_sweep = dv

    @kernel
    def set_rf(self,frequency=dv):
        if frequency == dv:
            frequency = self.params.frequency_rf_state_xfer_sweep_list[0]
        self.dds.dds_device.set(frequency=frequency/2,amplitude=self.params.amp_rf_source)

    @kernel
    def on(self):
        self.dds.dds_device.sw.on()

    @kernel
    def off(self):
        self.dds.dds_device.sw.off()


    @kernel
    def set_amplitude(self,amp):
        self.dds.set_dds(amplitude=amp)

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

        self.set_rf(frequency=frequency_sweep_list[0])
        self.on()
        for f in frequency_sweep_list:
            self.set_rf(frequency=f)
            delay(self.params.dt_rf_state_xfer_sweep)
        self.off()

    