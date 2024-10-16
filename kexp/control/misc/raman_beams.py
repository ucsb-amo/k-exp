from artiq.experiment import kernel, portable, delay, TArray, TFloat
import numpy as np
from kexp.control.artiq.DDS import DDS
from kexp.control.artiq.DAC_CH import DAC_CH

class RamanBeamPair():
    def __init__(self,dds0:DDS,dds1:DDS):
        self.dds0 = dds0
        self.dds1 = dds1

        self._frequency_center_dds0 = self.dds0.frequency
        self._frequency_center_dds1 = self.dds1.frequency
        if self._frequency_center_dds0 != self._frequency_center_dds1:
            raise ValueError("I didn't write this code to accout for different AO center frequencies. Ask me, or if I am gone, figure it out yourself. You'll have to update state_splitting_to_ao_frequency and decide how to divvy up the frequency difference between the two AOs -- maybe proportionally to their bandwidth.")

        self._relative_sign = self.dds0.aom_order * self.dds1.aom_order

        self._frequency_array = np.array([0.,0.])

    @portable(flags={"fast-math"})
    def state_splitting_to_ao_frequency(self,frequency_state_splitting) -> TArray(TFloat):
        frequency_difference_aos = frequency_state_splitting / 4
        self._frequency_array[0] = self._frequency_center_dds0 - self._relative_sign * frequency_difference_aos
        self._frequency_array[1] = self._frequency_center_dds1 + frequency_difference_aos
        return self._frequency_array
    
    @kernel
    def set_transition_frequency(self,frequency_transition):
        self._frequency_array = self.state_splitting_to_ao_frequency(frequency_transition)
        self.dds0.set_dds(frequency=self._frequency_array[0])
        self.dds1.set_dds(frequency=self._frequency_array[1])

    @kernel
    def pulse(self,t,frequency_transition,
              set_transition_frequency_bool=True):
        if set_transition_frequency_bool:
            self.set_transition_frequency(frequency_transition)
        self.dds0.on()
        self.dds1.on()
        delay(t)
        self.dds0.off()
        self.dds1.off()