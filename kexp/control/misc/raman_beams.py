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
        self.t_phase_origin_mu = np.int64(0)

        self.phase_mode = 0  # 0: independent, 1: synchronized

        self._frequency_center_dds = 0.
        self._frequency_array = np.array([0.,0.])

        self.t_timeline = np.zeros(5,dtype=np.int64)
        self.t_rtio = np.zeros(5,dtype=np.int64)
        self.t_idx = 0

    @kernel
    def get_t(self):
        self.t_timeline[self.t_idx] = now_mu()
        self.t_rtio[self.t_idx] = now_mu()
        self.t_idx += 1

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
    def set_phase(self,relative_phase=dv,global_phase=dv,
                  t_phase_origin_mu=np.int64(-1),
                  pretrigger=True):
        """Shifts the phase of the Raman beams. If pretrigger is True, the phase
        is set 5 us before the current timeline cursor position and the function
        does not change the timeline cursor position. Otherwise, introduces a 5
        us timeline delay.

        Minimum time between pulses when pretriggering to avoid phase skips is 3
        us.

        Args:
            relative_phase (float, optional): Relative phase between the raman
            beams. If left unset, does not change the relative phase.
            global_phase (_type_, optional): Global phase of the raman beams
            relative to t_phase_origin_mu. If left unset, does not change the
            global phase.
            t_phase_origin_mu (_type_, optional): The timestamp used for phase=0
            for each beam. If this timestamp is T, the phase at time t for a
            beam of frequency f' is phi(t) = global_phase + f' * (t - T). If
            unset, does not change the phase origin.
            pretrigger (bool, optional): Whether or not to pretrigger the set
            command. If pretrigger is True, the set command runs 5 us before the
            current timeline cursor position and the function does not change
            the timeline cursor position. Otherwise, introduces a 5 us timeline
            delay.
        """        
        
        t = now_mu()
        if pretrigger:
            delay(-5e-6)
        self.set(phase_mode=1,
                 global_phase=global_phase,
                 relative_phase=relative_phase,
                 t_phase_origin_mu=t_phase_origin_mu)
        at_mu(t)
        if not pretrigger:
            delay(5.e-6)

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
            global_phase=dv, relative_phase=dv,
            t_phase_origin_mu=np.int64(-1),
            phase_mode=0,
            init=False):
        """
        Set the parameters of the Raman beam pair and update the DDS channels as needed.

        This method updates the frequency, amplitude, phase mode, phase origin, global phase,
        and relative phase of the Raman beams. Only parameters that are explicitly changed
        (i.e., not left at their default values) will be updated. If `init` is True, all
        parameters are forced to update regardless of their current values.

        Args:
            frequency_transition (float, optional): The two-photon transition frequency (Hz).
                If negative or unchanged, the frequency is not updated.
            amp_raman (float, optional): The amplitude for the Raman beams.
                If negative or unchanged, the amplitude is not updated.
            global_phase (float, optional): The global phase of the Raman beams (radians).
                If negative or unchanged, the global phase is not updated.
            relative_phase (float, optional): The relative phase between the Raman beams (radians).
                If negative or unchanged, the relative phase is not updated.
            t_phase_origin_mu (int, optional): The phase origin timestamp in machine units.
                If zero or unchanged, the phase origin is not updated.
            phase_mode (int, optional): Phase mode (0: independent, 1: synchronized).
                If unchanged, the phase mode is not updated.
            init (bool, optional): If True, force all parameters to update regardless of their values.

        Side Effects:
            Updates the internal state of the object and calls the appropriate methods on the
            DDS channels to apply the new settings.
        """

        # Determine if frequency, amplitude, or v_pd should be updated
        freq_changed = (frequency_transition >= 0.) and (frequency_transition != self.frequency_transition)
        amp_changed = (amp_raman >= 0.) and (amp_raman != self.amplitude)
        phase_mode_changed = bool(phase_mode) != (self.phase_mode == 1)
        phase_origin_changed = t_phase_origin_mu >= 0. and (t_phase_origin_mu != self.t_phase_origin_mu)
        global_phase_changed = global_phase >= 0. and (global_phase != self.global_phase)
        relative_phase_changed = relative_phase >= 0. and (relative_phase != self.relative_phase)

        # Update stored values
        if freq_changed:
            self.frequency_transition = frequency_transition if frequency_transition >= 0. else self.frequency_transition
        if amp_changed:
            self.amplitude = amp_raman if amp_raman >= 0. else self.amplitude
        if phase_mode_changed:
            self.phase_mode = phase_mode
        if phase_origin_changed:
            self.t_phase_origin_mu = t_phase_origin_mu if t_phase_origin_mu > 0 else self.t_phase_origin_mu
        if global_phase_changed:
            self.global_phase = global_phase if global_phase >= 0. else self.global_phase
        if relative_phase_changed:
            self.relative_phase = relative_phase if relative_phase >= 0. else self.relative_phase

        if init:
            freq_changed = True
            amp_changed = True
            phase_mode_changed = True
            phase_origin_changed = True
            global_phase_changed = True
            relative_phase_changed = True
        
        if phase_mode_changed:
            self.dds_plus.set_phase_mode(self.phase_mode)
            self.dds_minus.set_phase_mode(self.phase_mode)

        if freq_changed or amp_changed or phase_origin_changed or global_phase_changed or relative_phase_changed:
            self._frequency_array = self.state_splitting_to_ao_frequency(self.frequency_transition)
            self.dds_plus.set_dds(self._frequency_array[0],
                                self.amplitude,
                                t_phase_origin_mu=self.t_phase_origin_mu,
                                phase=self.global_phase)
            self.dds_minus.set_dds(self._frequency_array[1],
                                self.amplitude,
                                t_phase_origin_mu=self.t_phase_origin_mu,
                                phase=self.global_phase+self.relative_phase)

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
        if self.phase_mode == 1:
            self.set(phase_mode=0)
        
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

