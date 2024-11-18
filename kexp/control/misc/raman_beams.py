from artiq.experiment import kernel, portable, delay, TArray, TFloat
import numpy as np
from kexp.control.artiq.DDS import DDS
from kexp.control.artiq.DAC_CH import DAC_CH
from kexp.config.expt_params import ExptParams

dv = -0.1
di = 0

class RamanBeamPair():
    def __init__(self,dds_plus:DDS,dds_minus:DDS,params:ExptParams):
        self.dds_plus = dds_plus
        self.dds_minus = dds_minus
        self.params = params

        self._frequency_center_dds_plus = self.dds_plus.frequency
        self._frequency_center_dds_minus = self.dds_minus.frequency
        if self._frequency_center_dds_plus != self._frequency_center_dds_minus:
            raise ValueError("I didn't write this code to accout for different AO center frequencies. Ask me, or if I am gone, figure it out yourself. You'll have to update state_splitting_to_ao_frequency and decide how to divvy up the frequency difference between the two AOs -- maybe proportionally to their bandwidth.")

        self._frequency_array = np.array([0.,0.])

    @portable(flags={"fast-math"})
    def state_splitting_to_ao_frequency(self,frequency_state_splitting) -> TArray(TFloat):

        order_plus = self.dds_plus.aom_order
        order_minus = self.dds_minus.aom_order

        df = frequency_state_splitting / 4

        if order_plus * order_minus == -1:
            self._frequency_array[0] = df
            self._frequency_array[1] = df
        else:
            self._frequency_array[0] = self._frequency_center_dds_plus + df
            self._frequency_array[1] = self._frequency_center_dds_minus - df

        return self._frequency_array
    
    @kernel
    def set_transition_frequency(self,frequency_transition):
        self._frequency_array = self.state_splitting_to_ao_frequency(frequency_transition)
        self.dds_plus.set_dds(frequency=self._frequency_array[0])
        self.dds_minus.set_dds(frequency=self._frequency_array[1])

    @kernel
    def on(self):
        self.dds_plus.on()
        self.dds_minus.on()

    @kernel
    def off(self):
        self.dds_plus.off()
        self.dds_minus.off()

    @kernel
    def pulse(self,t,frequency_transition,
              set_transition_frequency_bool=True):
        if set_transition_frequency_bool:
            self.set_transition_frequency(frequency_transition)
        self.on()
        delay(t)
        self.off()

    @kernel
    def sweep(self,t,
              frequency_center=dv,
              frequency_sweep_fullwidth=dv,
              n_steps=di):
        """Sweeps the transition frequency of the two-photon transition over the
        specified range.

        Args:
            t (float): The time (in seconds) for the sweep.
            frequency_center (float, optional): The center frequency (in Hz) for the sweep range.
            frequency_sweep_fullwidth (float, optional): The full width (in Hz) of the sweep range.
            n_steps (int, optional): The number of steps for the frequency sweep.
        """
        if frequency_center == dv:
            frequency_center = self.params.frequency_raman_zeeman_state_xfer_sweep_center
        if frequency_sweep_fullwidth == dv:
            frequency_sweep_fullwidth = self.params.frequency_raman_zeeman_state_xfer_sweep_fullwidth
        if n_steps == di:
            n_steps = self.params.n_raman_sweep_steps

        f0 = frequency_center - frequency_sweep_fullwidth / 2
        ff = frequency_center + frequency_sweep_fullwidth / 2
        df = (ff-f0)/(n_steps-1)
        dt = t / n_steps

        self.set_transition_frequency(frequency_transition=f0)
        self.on()
        for i in range(n_steps):
            self.set_transition_frequency(frequency_transition=f0+i*df)
            delay(dt)
        self.off()

        