from kexp.control.artiq.DDS import DDS
from kexp.config import ExptParams
from artiq.experiment import kernel, delay, parallel, portable, TFloat
from artiq.experiment import *
import numpy as np

dv = -0.1
di = 0
dv_list = np.linspace(0.,1.,5)

d_exptparams = ExptParams()

class doubled_rf():
    def __init__(self, dds_ch:DDS, expt_params:ExptParams = d_exptparams):
        self.dds = dds_ch
        self.params = expt_params

        self.params.frequency_rf_state_xfer_sweep_list = dv_list
        self.params.dt_rf_state_xfer_sweep = dv

    @kernel(flags={"fast-math"})
    def set_rf(self,frequency=dv):
        if frequency == dv:
            frequency = self.params._frequency_rf_state_xfer_sweep_start
        self.dds.dds_device.set(frequency=frequency/2,
                                amplitude=self.params.amp_rf_source)

    @kernel
    def on(self):
        self.dds.dds_device.sw.on()

    @kernel
    def off(self):
        self.dds.dds_device.sw.off()

    @kernel
    def set_amplitude(self,amp):
        self.dds.set_dds(amplitude=amp)

    @kernel(flags={"fast-math"})
    def sweep(self,t,frequency_start=dv,frequency_end=dv,n_steps=di):
        """Sweeps the lower sideband freuqency over the specified range.

        The sweep time is controlled by ExptParams.t_rf_state_xfer_sweep, and
        the sweep step time is controlled by ExptParams.dt_rf_state_xfer_sweep.
        Adjust those to change the ramp times.

        Args:
            t (float): The time (in seconds) for the sweep.
            frequency_start (float, optional): The initial frequency (in Hz) for the sweep.
            frequency_end (float, optional): The end frequency (in Hz) for the sweep.
            n_steps (int, optional): The number of steps for the frequency sweep.
        """        
        if frequency_start == dv:
            frequency_start = self.params._frequency_rf_state_xfer_sweep_start
        if frequency_end == dv:
            frequency_end = self.params._frequency_rf_state_xfer_sweep_end
        if n_steps == di:
            n_steps = self.params.n_rf_sweep_steps

        f0 = frequency_start
        ff = frequency_end
        df = (ff-f0)/(n_steps-1)
        dt = t / n_steps

        self.set_rf(frequency=f0)
        self.on()
        for i in range(n_steps):
            self.set_rf(frequency=f0+i*df)
            delay(dt)
        self.off()

    