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
    def __init__(self,dds_plus=DDS,dds_minus=DDS,params=ExptParams,
                 frequency_transition=0., amplitude=0.):
        self.dds_plus = dds_plus
        self.dds_minus = dds_minus
        self.params = params
        self.p = self.params

        self.frequency_transition = frequency_transition
        self.amplitude = amplitude

        self.global_phase = 0.
        self.relative_phase = 0.

        self.phase_mode = 0  # 0: independent, 1: synchronized

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
    def set_transition_frequency(self,frequency_transition=dv):
        self.set(frequency_transition)

    @kernel
    def set_phase(self,relative_phase=dv,global_phase=dv):
        self.set(sync_phase=True,global_phase=global_phase,relative_phase=relative_phase)

    @kernel
    def on(self):
        self.dds_plus.on()
        self.dds_minus.on()

    @kernel
    def off(self):
        self.dds_plus.off()
        self.dds_minus.off()

    @kernel
    def set(self,
            frequency_transition=dv,
            amp_raman=dv,
            sync_phase=True,
            global_phase=0., relative_phase=0.,
            init=False):
        # Determine if frequency, amplitude, or v_pd should be updated
        freq_changed = (frequency_transition >= 0.) and (frequency_transition != self.frequency_transition)
        amp_changed = (amp_raman >= 0.) and (amp_raman != self.amplitude)
        sync_phase_mode_changed = sync_phase != (self.phase_mode == 1)
        global_phase_changed = global_phase_changed >= 0. and (global_phase != self.global_phase)
        relative_phase_changed = relative_phase >= 0. and (global_phase != self.global_phase)
    
        # Update stored values
        if freq_changed:
            self.frequency_transition = frequency_transition if frequency_transition >= 0. else self.frequency_transition
        if amp_changed:
            self.amplitude = amp_raman if amp_raman >= 0. else self.amplitude
        if sync_phase_mode_changed:
            self.phase_mode = 1 if sync_phase else self.phase_mode
        if global_phase_changed:
            self.global_phase = global_phase if global_phase >= 0. else self.global_phase
        if relative_phase_changed:
            self.relative_phase = relative_phase if relative_phase >= 0. else self.relative_phase

        if init:
            freq_changed = True
            amp_changed = True
            sync_phase_mode_changed = True
            global_phase_changed = True
            relative_phase_changed = True

        t0 = now_mu()
        if sync_phase_mode_changed or init:
            self.dds_plus.set_phase_mode(self.phase_mode)
            self.dds_minus.set_phase_mode(self.phase_mode)

        if freq_changed or amp_changed or global_phase_changed or init:
            self._frequency_array = self.state_splitting_to_ao_frequency(self.frequency_transition)
            self.dds_plus.set_dds(self._frequency_array[0],
                                self.amplitude,
                                t_phase_origin_mu=t0,
                                phase_offset=self.global_phase)
            self.dds_minus.set_dds(self._frequency_array[1],
                                self.amplitude,
                                t_phase_origin_mu=t0,
                                phase_offset=self.global_phase+self.relative_phase)

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

        self.set(frequency_transition=f0)
        self.on()
        for i in range(n_steps):
            self.set(frequency_transition=f0+i*df)
            delay(dt)
        self.off()

        