import numpy as np
from numpy import int64, int32

from artiq.coredevice.ad9910 import _AD9910_REG_FTW, _AD9910_REG_PROFILE0
from artiq.coredevice import ad9910
from artiq.coredevice import spi2 as spi
from artiq.coredevice import urukul
from artiq.experiment import TArray, TFloat, TTuple, parallel
from artiq.language.core import now_mu, at_mu, kernel, portable, delay, parallel, delay_mu, sequential

from waxx.control.artiq.DDS import DDS, T_AD9910_REGISTER_UPDATE_FROM_PHASE_ORIGIN_MU, T_AD9910_PIPELINE_LATENCY_MU
from waxx.config.expt_params import ExptParams

from waxx.util.artiq.async_print import aprint

dv = -0.1
dv_array = np.array([-0.1])
di = 0

TWOPI = 2*np.pi

DDS0_IDX = 0
DDS1_IDX = 1

class RamanBeamPair():
    kernel_invariants = {
        "_sysclk_per_mu"
    }
    def __init__(self,
                 dds0:DDS,
                 dds1:DDS,
                 dds_sw:DDS,
                 params=ExptParams(),
                 frequency_transition=0.,
                 fraction_power=0.):
        self.dds0 = dds0
        self.dds1 = dds1
        self.dds_sw = dds_sw
        self.params = params
        self.p = self.params

        self.frequency_transition = frequency_transition
        # self.amplitude = amplitude
        self.fraction_power = fraction_power

        self.global_phase = 0.
        self.relative_phase = 0.
        self.t_phase_origin_mu = np.int64(0)

        self.phase_mode = 0  # 0: independent, 1: synchronized

        # self._frequency_center_dds = 0.
        self._frequency_center_plus = 0.
        self._frequency_center_minus = 0.
        self._relative_sign_fcenter = 0
        self._frequency_array = np.array([0.,0.])
        self._amplitude_0 = 0.
        self._amplitude_1 = 0.

        self.t_timeline = np.zeros(5,dtype=np.int64)
        self.t_rtio = np.zeros(5,dtype=np.int64)
        self.t_idx = 0
        self._init()

        self._t = np.int64(0)

        self._dummy = np.zeros(3).astype(float)

        try:
            self._sysclk_per_mu = self.dds0.dds_device.sysclk_per_mu
        except Exception as e:
            print(e)
        self._f_to_ftw = self.dds0.dds_device.frequency_to_ftw
        self._turns_to_pow = self.dds0.dds_device.turns_to_pow
        self._amp_to_asf = self.dds0.dds_device.amplitude_to_asf
        self._pow_relphase = np.int32(0)
        self._asf0 = np.int32(0)
        self._new_ftw0 = np.int32(0)
        self._new_f0 = 0.

        self._fast_freq_stage_valid = np.int32(0)
        self._fast_freq_aggressive_enabled = np.int32(0)
        self._fast_freq_event_token = np.int32(0)
        self._fast_freq_pending_token = np.int32(-1)
        self._fast_freq_addr_pending0 = np.int32(0)
        self._aggressive_config_pending0 = np.int32(0)

    @kernel
    def get_t(self):
        self.t_timeline[self.t_idx] = now_mu()
        self.t_rtio[self.t_idx] = now_mu()
        self.t_idx += 1

    def _init(self):
        self._frequency_center_0 = self.dds0.frequency
        self._frequency_center_1 = self.dds1.frequency
        self._amplitude_0 = self.dds0.amplitude
        self._amplitude_1 = self.dds1.amplitude

        self._frequency_ratio = self._frequency_center_1/self._frequency_center_0

        fc0 = self._frequency_center_0
        fc1 = self._frequency_center_1

        self._frequency_diff_sign = np.sign(fc0 - fc1)

    @kernel
    def init(self,
            frequency_transition,
            fraction_power,
            global_phase=0.,relative_phase=0.,
            t_phase_origin_mu=np.int64(-1),
            phase_mode=1):
        if t_phase_origin_mu < 0:
            t_phase_origin_mu = now_mu()
        self.set(frequency_transition=frequency_transition,
                 fraction_power_raman=fraction_power,
                 global_phase=global_phase,
                 relative_phase=relative_phase,
                 t_phase_origin_mu=t_phase_origin_mu,
                 phase_mode=phase_mode,
                 init=True)
        self.dds_sw._restore_defaults()
        self.dds_sw.set_dds(init=True)
        self.dds0.on()
        self.dds1.on()

    @portable(flags={"fast-math"})
    def state_splitting_to_ao_frequency(self,
                                        frequency_state_splitting):

        a0 = self.dds0.aom_order
        a1 = self.dds1.aom_order

        delta = frequency_state_splitting

        fc0 = self._frequency_center_0
        fc1 = self._frequency_center_1

        sgn = float(self._frequency_diff_sign)

        # dds1 stays fixed at fc1; dds0 absorbs the entire transition-frequency change.
        if a0 * a1 > 0:
            df_0 = delta/2 - sgn * (fc0 - fc1)
            c0 = sgn
        else:
            df_0 = delta/2 - (fc0 + fc1)
            c0 = 1.

        self._dummy[DDS0_IDX] = fc0 + c0 * df_0
        self._dummy[DDS1_IDX] = fc1

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
        self.dds_sw.on()

    @kernel
    def off(self):
        self.dds_sw.off()

    @kernel
    def reset_phase(self):
        self.dds0.reset_phase()
        self.dds1.reset_phase()

    @kernel
    def _configure_ffua_profile(self):
        # In fast mode, source frequency from the FTW register and keep POW constant from RAM.
        # Use the ASF register for amplitude so RAM profile setup does not clobber the active
        # single-tone profile amplitude on shared-profile Urukul cards.
        # Only dds0 is driven in fast mode; dds1 stays at its fixed single-tone frequency.
        ram_word0 = int32((self.dds0._pow << 16))  # ASF bits ignored in RAM_DEST_POW mode

        dt0 = int64(self.dds0.dds_device.sync_data.io_update_delay)

        self.dds0.dds_device.set_cfr2(asf_profile_enable=0)

        self.dds0.dds_device.set_cfr1(
            ram_enable=1,
            ram_destination=ad9910.RAM_DEST_POW,
            osk_enable=1
        )

        self.dds0.dds_device.set_profile_ram(
            start=0, end=0, step=1, profile=urukul.DEFAULT_PROFILE,
            mode=ad9910.RAM_MODE_DIRECTSWITCH
        )

        self.dds0.dds_device.write_ram([ram_word0])

        self.dds0.dds_device.set_mu(ftw=self.dds0._ftw, asf=self._asf0,
                                    ram_destination=ad9910.RAM_DEST_POW,
                                    phase_mode=0)

    @kernel
    def set_up_fast_frequency_update(self, aggressive_mode=0):
        # aggressive_mode options:
        # 0 -> safe mode: address+data written inside set_frequency_fast
        # 1 -> aggressive mode: address/config prewritten in slack, data-only hot path

        self._configure_ffua_profile()

        at_mu(now_mu() & ~7)

        self._invalidate_fast_frequency_update_state()
        self._fast_freq_aggressive_enabled = np.int32(aggressive_mode)

        # First stage happens here so callers do not need to stage immediately after setup.
        if self._fast_freq_aggressive_enabled == 1:
            self.stage_ffua()
        else:
            self.stage_ffu()

        at_mu(now_mu() & ~7)

    @kernel
    def _invalidate_fast_frequency_update_state(self):
        self._fast_freq_event_token = np.int32(self._fast_freq_event_token + 1)
        self._fast_freq_pending_token = np.int32(-1)
        self._fast_freq_stage_valid = np.int32(0)
        self._fast_freq_addr_pending0 = np.int32(0)
        self._aggressive_config_pending0 = np.int32(0)

    @kernel
    def reset_fast_frequency_update_stage(self):
        self._fast_freq_pending_token = np.int32(-1)
        self._fast_freq_stage_valid = np.int32(0)
        self._fast_freq_addr_pending0 = np.int32(0)
        self._aggressive_config_pending0 = np.int32(0)

    @kernel
    def enable_aggressive_fast_frequency_update(self, enable=1):
        # enable options:
        # 0 -> disable aggressive mode
        # 1 -> enable aggressive mode
        self._fast_freq_aggressive_enabled = np.int32(enable)
        self.reset_fast_frequency_update_stage()

    @kernel
    def stage_ffu(self):
        # Stage 8-bit header-write config for the next FTW transaction.
        if self._fast_freq_addr_pending0 == 1:
            self._invalidate_fast_frequency_update_state()
        self.dds0.dds_device.bus.set_config_mu(
            urukul.SPI_CONFIG, 8, urukul.SPIT_DDS_WR, self.dds0.dds_device.chip_select
        )
        self._fast_freq_stage_valid = np.int32(1)

    @kernel
    def stage_ffua(self):
        # Aggressive: prewrite FTW address and 32-bit SPI_END config in slack.
        # Consume with data write only, no config needed in hot path.
        if self._fast_freq_aggressive_enabled == 0:
            self.stage_ffu()
            return

        # Guard: do not prewrite twice before a consume.
        if self._fast_freq_addr_pending0 == 1:
            return

        self._fast_freq_stage_valid = np.int32(0)
        self.dds0.dds_device.bus.set_config_mu(
            urukul.SPI_CONFIG, 8, urukul.SPIT_DDS_WR, self.dds0.dds_device.chip_select
        )
        self.dds0.dds_device.bus.write(_AD9910_REG_FTW << 24)
        self.dds0.dds_device.bus.set_config_mu(
            urukul.SPI_CONFIG | spi.SPI_END, 32, urukul.SPIT_DDS_WR, self.dds0.dds_device.chip_select
        )
        self._fast_freq_pending_token = np.int32(self._fast_freq_event_token)
        self._fast_freq_addr_pending0 = np.int32(1)
        self._aggressive_config_pending0 = np.int32(1)

    @kernel
    def _finish_pending_fast_frequency_update(self):
        token_ok = self._fast_freq_pending_token == self._fast_freq_event_token
        if token_ok and self._fast_freq_addr_pending0 == 1:
            self.dds0.dds_device.bus.set_config_mu(
                urukul.SPI_CONFIG | spi.SPI_END, 32, urukul.SPIT_DDS_WR, self.dds0.dds_device.chip_select
            )
            self.dds0.dds_device.bus.write(self.dds0._ftw)
        self.reset_fast_frequency_update_stage()

    @kernel
    def _restore_default_profile_mode(self):
        self.dds0.dds_device.set_cfr1(
            phase_autoclear=1,
            internal_profile=0,
            ram_enable=0,
            ram_destination=0
        )

        self.io_update()

    @kernel
    def clean_up_fast_frequency_update(self):
        if self._fast_freq_aggressive_enabled == 1:
            self._finish_pending_fast_frequency_update()
        self._invalidate_fast_frequency_update_state()
        self._fast_freq_aggressive_enabled = np.int32(0)
        self._aggressive_config_pending0 = np.int32(0)
        self._restore_default_profile_mode()

    @kernel
    def io_update(self):
        at_mu(now_mu() & ~7)

        dt0 = int64(self.dds0.dds_device.sync_data.io_update_delay)

        delay_mu(dt0)
        self.dds0.dds_device.cpld.io_update.pulse_mu(8)
    
        at_mu(now_mu() & ~7)

        self.dds0.frequency = self._new_f0
        self.dds0._ftw = self._new_ftw0
        # self.dds0.update_phase_at_set()

    @kernel(flags={"fast-math"})
    def set_frequency_fast_dumb(self,
                                frequency_transition):
        asf0 = self.dds0._asf

        pow0 = 0

        self.state_splitting_to_ao_frequency(frequency_transition)
        f0 = self._dummy[DDS0_IDX]
        ftw0 = int32(self.dds0.dds_device.ftw_per_hz * f0)
        
        at_mu(now_mu() & ~7)
        
        self.dds0.dds_device.write64(_AD9910_REG_PROFILE0 + 7,
                        (asf0 << 16) | (pow0 & 0xffff), ftw0)

        delay_mu(int64(self.dds0.dds_device.sync_data.io_update_delay))
        self.dds0.dds_device.cpld.io_update.pulse_mu(8)
    
        at_mu(now_mu() & ~7)
        
    @kernel(flags={"fast-math"})
    def set_frequency_fast(self,
                 frequency_transition,
                 do_io_update=True):
        
        self.dds0._last_ftw = self.dds0._ftw    

        self.frequency_transition = frequency_transition

        self.state_splitting_to_ao_frequency(frequency_transition)
        f0 = self._dummy[DDS0_IDX]
        ftw0 = int32(self.dds0.dds_device.ftw_per_hz * f0)

        self._new_f0 = f0
        self._new_ftw0 = ftw0

        at_mu(now_mu() & ~7)

        # Aggressive: only write data + io_update if address and config pre-staged.
        use_aggressive = (
            self._fast_freq_aggressive_enabled == 1 and
            self._fast_freq_addr_pending0 == 1 and
            self._aggressive_config_pending0 == 1 and
            self._fast_freq_pending_token == self._fast_freq_event_token
        )

        if use_aggressive:
            self.dds0.dds_device.bus.write(ftw0)
            self.reset_fast_frequency_update_stage()
        else:
            if self._fast_freq_addr_pending0 == 1:
                self._invalidate_fast_frequency_update_state()
            if self._fast_freq_stage_valid == 0:
                self.stage_ffu()

            self.dds0.dds_device.bus.write(_AD9910_REG_FTW << 24)
            self.dds0.dds_device.bus.set_config_mu(
                urukul.SPI_CONFIG | spi.SPI_END, 32, urukul.SPIT_DDS_WR, self.dds0.dds_device.chip_select
            )
            self.dds0.dds_device.bus.write(ftw0)
            self._fast_freq_stage_valid = np.int32(0)
            
        if do_io_update:
            self.io_update()

    @kernel(flags={"fast-math"})
    def set(self,
            frequency_transition=dv,
            fraction_power_raman=dv,
            global_phase=dv, relative_phase=dv,
            t_phase_origin_mu=np.int64(-1),
            phase_mode=-1,
            init=False,
            dt_phase_origin_shift_mu=T_AD9910_REGISTER_UPDATE_FROM_PHASE_ORIGIN_MU):
        """
        Set the parameters of the Raman beam pair and update the DDS channels as needed.

        This method updates the frequency, amplitude, phase mode, phase origin, global phase,
        and relative phase of the Raman beams. Only parameters that are explicitly changed
        (i.e., not left at their default values) will be updated. If `init` is True, all
        parameters are forced to update regardless of their current values.

        Args:
            frequency_transition (float, optional): The two-photon transition frequency (Hz).
                If negative or unchanged, the frequency is not updated.
            
            fraction_power_raman (float, optional): The fractional power for the Raman beams.
                If negative or unchanged, the power is not updated.
            
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

        self._invalidate_fast_frequency_update_state()

        # Determine if frequency, amplitude, or v_pd should be updated

        if init:
            freq_changed = True
            fraction_power_changed = True
            phase_mode_changed = True
            phase_origin_changed = True
            global_phase_changed = True
            relative_phase_changed = True
        else:
            freq_changed = (frequency_transition >= 0.) and (frequency_transition != self.frequency_transition)
            fraction_power_changed = (fraction_power_raman >= 0.) and (fraction_power_raman != self.fraction_power)
            phase_mode_changed = (phase_mode >= 0) and (phase_mode != self.phase_mode)
            phase_origin_changed = t_phase_origin_mu >= 0. and (t_phase_origin_mu != self.t_phase_origin_mu)
            global_phase_changed = global_phase >= 0. and (global_phase != self.global_phase)
            relative_phase_changed = relative_phase >= 0. and (relative_phase != self.relative_phase)

        # Update stored values
        if freq_changed:
            self.frequency_transition = frequency_transition if frequency_transition >= 0. else self.frequency_transition
        if fraction_power_changed:
            self.fraction_power = fraction_power_raman if fraction_power_raman >= 0. else self.fraction_power
            
        if phase_mode_changed:
            self.phase_mode = phase_mode if phase_mode >= 0 else self.phase_mode
        if phase_origin_changed:
            self.t_phase_origin_mu = t_phase_origin_mu if t_phase_origin_mu > 0 else self.t_phase_origin_mu
        if global_phase_changed:
            self.global_phase = global_phase if global_phase >= 0. else self.global_phase
        if relative_phase_changed:
            self.relative_phase = relative_phase if relative_phase >= 0. else self.relative_phase
            self._pow_relphase = self._turns_to_pow(self.relative_phase/(4*np.pi))
        if phase_mode_changed:
            self.dds0.set_phase_mode(self.phase_mode)
            self.dds1.set_phase_mode(self.phase_mode)

        # t0 = now_mu()
        if freq_changed or fraction_power_changed or phase_origin_changed or global_phase_changed or relative_phase_changed:
            self.state_splitting_to_ao_frequency(self.frequency_transition)

            amp0 = np.sqrt(self.fraction_power) * self._amplitude_0
            amp1 = np.sqrt(self.fraction_power) * self._amplitude_1
            self._asf0 = self._amp_to_asf(amp0)

            self._frequency_array[DDS0_IDX] = self._dummy[DDS0_IDX]
            self._frequency_array[DDS1_IDX] = self._dummy[DDS1_IDX]

            with sequential:
                self.dds0.set_dds(self._frequency_array[DDS0_IDX],
                                    amp0,
                                    t_phase_origin_mu=self.t_phase_origin_mu,
                                    dt_phase_origin_shift_mu=dt_phase_origin_shift_mu,
                                    phase=self.global_phase/2)
                self.dds1.set_dds(self._frequency_array[DDS1_IDX],
                                    amp1,
                                    t_phase_origin_mu=self.t_phase_origin_mu,
                                    dt_phase_origin_shift_mu=dt_phase_origin_shift_mu,
                                    phase=(self.global_phase+self.relative_phase)/2)

        self.dds0.on()
        self.dds1.on()
    
    @kernel(flags={"fast-math"})
    def get_phase(self,
               t_mu=np.int64(-1),
               t_mu_origin=np.int64(-1),
               frequency_transition=dv,
               relative_phase=dv) -> int32:
        """
        Get the current relative phase of the Raman beams at time t_mu relative
        to t_mu_origin. Defined as phi_0 - phi_1 (where phi_i is the phase of ddsi).
        
        Accounts for the fact that the AOMs are double-passed, such
        that the phase accumulated by each beam is twice that expected from the
        oscillator frequency.

        Args:
            t_mu (int, optional): The time at which to get the phase in machine units.
            t_mu_origin (int, optional): The time origin for the phase calculation in machine units.
            frequency_transition (float, optional): The two-photon transition frequency (Hz).
                If negative or unchanged, uses the current AO values.
            relative_phase (float, optional): The relative phase between the Raman beams (radians).
                If negative or unchanged, uses the current relative phase.

        Returns:
            A tuple containing the phase of each Raman beam (p0, p1) at time t_mu relative to t_mu_origin.
        """
        if self.phase_mode == 1:
            # aprint(self.frequency_transition - frequency_transition, self.frequency_transition, frequency_transition)
            if frequency_transition == dv or frequency_transition == self.frequency_transition:
                f0 = self._frequency_array[DDS0_IDX]
                f1 = self._frequency_array[DDS1_IDX]
            else:
                self.state_splitting_to_ao_frequency(frequency_transition)
                f0 = self._dummy[DDS0_IDX]
                f1 = self._dummy[DDS1_IDX]
            relative_phase = relative_phase if relative_phase >= 0. else self.relative_phase
        
            # aprint(frequency_transition,f0,f1,relative_phase)
            p0 = self.dds0.get_phase(t_mu,
                                    t_mu_origin,
                                    ftw=self.dds0.dds_device.frequency_to_ftw(f0),
                                    pow=self.dds0.dds_device.turns_to_pow(self.global_phase/TWOPI))
            p1 = self.dds1.get_phase(t_mu,
                                    t_mu_origin,
                                    ftw=self.dds1.dds_device.frequency_to_ftw(f1),
                                    pow=self.dds1.dds_device.turns_to_pow((self.global_phase+relative_phase)/TWOPI))
        else:
            p0 = self.dds0.get_phase()
            p1 = self.dds1.get_phase()
        return (2*(p0-p1)) & int32(0xffff)
    
    @portable(flags={"fast-math"})
    def pow_to_phase(self, pow) -> TFloat:
        return self.dds0.dds_device.pow_to_turns(pow) * TWOPI
        
    @kernel
    def pulse(self,t):
        """Pulses the raman beam. Does not set the DDS channels -- use
        init_raman_beams for this.

        Args:
            t (float): The pulse duration in seconds.
        """        
        # self.on()
        self.dds_sw.dds_device.sw.on()
        delay(t)
        self.dds_sw.dds_device.sw.off()
        # self.off()

    @kernel
    def sweep(self,t,
              frequency_center,
              frequency_sweep_fullwidth,
              n_steps=100):
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
