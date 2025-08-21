from artiq.experiment import kernel, portable, delay, TArray, TFloat, parallel
import numpy as np
from kexp.control.artiq.DDS import DDS
from kexp.control.artiq.DAC_CH import DAC_CH
from kexp.config.expt_params import ExptParams
from kexp.util.artiq.async_print import aprint
from artiq.language.core import now_mu, at_mu

dv = -0.1
di = 0

class RamanBeamPair():
    def __init__(self,dds_plus=DDS,dds_minus=DDS,params=ExptParams):
        self.dds_plus = dds_plus
        self.dds_minus = dds_minus
        self.params = params
        self.p = self.params
        self._frequency_center_dds = 0.

        self._frequency_array = np.array([0.,0.])

    def _init(self):
        self._frequency_center_dds = (self.dds_plus.frequency + self.dds_minus.frequency)/2
        if abs(self._frequency_center_dds - self.dds_plus.frequency) != abs(self._frequency_center_dds - self.dds_minus.frequency):
            raise ValueError("The - and + DDS frequencies should be equidistant from their mean for optimal efficiency.")

    @portable(flags={"fast-math"})
    def state_splitting_to_ao_frequency(self,frequency_state_splitting) -> TArray(TFloat):

        order_plus = self.dds_plus.aom_order
        order_minus = self.dds_minus.aom_order

        df = frequency_state_splitting / 4

        if order_plus * order_minus == -1:
            self._frequency_array[0] = df
            self._frequency_array[1] = df
        else:
            self._frequency_array[0] = self._frequency_center_dds + df
            self._frequency_array[1] = self._frequency_center_dds - df

        return self._frequency_array
    
    @kernel
    def init(self,frequency_transition=dv,amp_raman=dv,
             sync_phase=True, phase_offset=0.):
        """_summary_

        Args:
            frequency_transition (float, optional): The two-photon transition
            frequency to be addressed. Defaults to ExptParams.frequency_raman_transition.
            amp_raman (float, optional): Amplitude for the raman beam DDSs.
            Defaults to ExptParams.amp_raman.
            sync_phase (bool, optional): Sets the DDSs to tracking phase mode
            and syncs the phase origin to the same timestamp. Defaults to True.
            phase_offset (float, optional): Phase between dds plus and dds
            minus. Defaults to 0. Meaningful only if sync_phase is True.
        """        
        if frequency_transition == dv:
            frequency_transition = self.p.frequency_raman_transition
        if amp_raman == dv:
            amp_raman = self.p.amp_raman
        if sync_phase:
            self.dds_plus.set_phase_mode(1)
            self.dds_minus.set_phase_mode(1)
            t0 = now_mu()
        else:
            t0 = 0
        self._frequency_array = self.state_splitting_to_ao_frequency(frequency_transition)
        self.dds_plus.set_dds(self._frequency_array[0],amp_raman,
                              t_phase_origin_mu=t0,
                              phase_offset=0.)
        self.dds_minus.set_dds(self._frequency_array[1],amp_raman,
                               t_phase_origin_mu=t0,
                               phase_offset=phase_offset)
    
    @kernel
    def set_transition_frequency(self,frequency_transition=dv):
        if frequency_transition == dv:
            frequency_transition = self.p.frequency_raman_transition
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
    def pulse(self,t):
        """Pulses the raman beam. Does not set the DDS channels -- use
        init_raman_beams for this.

        Args:
            t (float): The pulse duration in seconds.
        """        
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

        