from kexp.control.artiq.DDS import DDS
from kexp.config.expt_params import ExptParams
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

    @kernel(flags={"fast-math"})
    def set_rf(self,frequency=dv):
        """Sets the lower sideband frequency of the frequency doubled RF to be
        equal to the specified frequency.

        Args:
            frequency (float): Defaults to the start point of the sweep
            (center-fullwidth/2).
        """        
        if frequency == dv:
            frequency = self.params.frequency_rf_state_xfer_sweep_center \
                - self.params.frequency_rf_state_xfer_sweep_fullwidth/2
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
    def sweep(self,t,frequency_center=dv,frequency_sweep_fullwidth=dv,n_steps=di):
        """Sweeps the lower sideband frequency of the frequency doubled DDS over
        the specified range.

        Args:
            t (float): The time (in seconds) for the sweep.
            frequency_center (float, optional): The center frequency (in Hz) for the sweep range.
            frequency_sweep_fullwidth (float, optional): The full width (in Hz) of the sweep range.
            n_steps (int, optional): The number of steps for the frequency sweep.
        """        
        if frequency_center == dv:
            frequency_center = self.params.frequency_rf_state_xfer_sweep_center
        if frequency_sweep_fullwidth == dv:
            frequency_sweep_fullwidth = self.params.frequency_rf_state_xfer_sweep_fullwidth
        if n_steps == di:
            n_steps = self.params.n_rf_sweep_steps

        f0 = frequency_center - frequency_sweep_fullwidth / 2
        ff = frequency_center + frequency_sweep_fullwidth / 2
        df = (ff-f0)/(n_steps-1)
        dt = t / n_steps

        self.set_rf(frequency=f0)
        self.on()
        for i in range(n_steps):
            self.set_rf(frequency=f0+i*df)
            delay(dt)
        self.off()

    