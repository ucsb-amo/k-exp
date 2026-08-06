from artiq.coredevice.core import Core

from waxx.control.artiq.dummy_core import DummyCore
from waxx.control.misc.sdg6000x import SDG6000X_CH, dv
from waxx.control.artiq.TTL import TTL_OUT
from waxx.control.artiq.DAC_CH import DAC_CH
from waxx.control.artiq.DDS import DDS

from waxx.control.misc.moglabs_wavemeter import WavemeterClient
from kexp.config.data_vault import DataContainer

from artiq.language import now_mu, kernel, delay, portable


class RydbergBeamBase():
    """Shared control for a Rydberg laser beam.

    Both beams share the same control topology:
    - Frequency is set at the wavemeter position by a siglent-driven fiber EO
      (and, when enabled, a cavity AO -- off for now, so ``cavity_ao_order``
      defaults to 0 and the term drops out).
    - Intensity is stabilized by a DDS+DAC PID: the setpoint is written to
      ``dac_pid`` and the integrator is cleared by pulsing ``ttl_pid_clear``.

    The only per-beam differences are the switch (TTL vs DDS) and the optional
    mechanical shutter, which the subclasses provide.
    """
    def __init__(self,
                 siglent_ch: SDG6000X_CH,
                 dac_pid: DAC_CH,
                 ttl_pid_clear: TTL_OUT,
                 eo_shift_direction,
                 wavemeter: WavemeterClient,
                 lock_data_container=DataContainer,
                 siglent_freq_data_container=DataContainer,
                 cavity_ao_frequency=0.,
                 cavity_ao_order=0,
                 ttl_shutter=None,
                 core: Core = DummyCore()):
        self.siglent = siglent_ch
        self.dac_pid = dac_pid
        self.ttl_pid_clear = ttl_pid_clear
        self.ttl_shutter = ttl_shutter

        self._eo_shift_direction = eo_shift_direction
        self._cavity_ao_frequency = cavity_ao_frequency
        self._cavity_ao_order = cavity_ao_order

        self._wavemeter = wavemeter
        self._lock_dc = lock_data_container
        self._siglent_freq_dc = siglent_freq_data_container
        self._core = core

        self._used = False

        self.siglent._stash_defaults()

    @portable
    def reset_used_flag(self):
        self._used = False

    @kernel
    def set_siglent(self, frequency=dv, amplitude=dv, init=False):
        self.siglent.set(frequency=frequency, amplitude=amplitude, init=init)

    @kernel
    def set_power(self, v_pd=dv, load_dac=True):
        self.dac_pid.set(v_pd, load_dac)
        self.ttl_pid_clear.pulse(10.e-6)

    @kernel
    def sweep_to(self, frequency_end=dv, frequency_step=1.e6, reset=False):
        self.siglent.sweep(frequency_end, frequency_step, reset)

    @kernel
    def lock_status(self, robust=True):
        """Record the wavemeter frequency and the siglent set frequency.

        The wavemeter target is shifted by the fiber-EO sideband and the cavity
        AO. Both beams are frequency controlled at the wavemeter purely by these
        elements, so this method is identical for every beam. The fetched siglent
        frequency is stored alongside the lock reading in a second container.
        """
        if self._used:
            self._core.wait_until_mu(now_mu())
            f_siglent = self.siglent.get_frequency()
            frequency_shift = ( self._eo_shift_direction * f_siglent
                                - self._cavity_ao_order * self._cavity_ao_frequency )
            f_fzw = self._wavemeter.lock_status(frequency_shift, robust)
            self._lock_dc.put_data(f_fzw)
            self._siglent_freq_dc.put_data(f_siglent)
            self._core.break_realtime()

class RydbergDDSSwitchBeam(RydbergBeamBase):
    """405 nm beam: DDS-switched (double-pass AOM) with a mechanical shutter.

    The double-pass switch AOM sits after the wavemeter pickoff, so its
    frequency does not enter ``lock_status``; the DDS class handles the
    double-pass detuning math for the switch itself.
    """
    def __init__(self,
                 siglent_ch: SDG6000X_CH,
                 dds_sw: DDS,
                 dac_pid: DAC_CH,
                 ttl_shutter: TTL_OUT,
                 ttl_pid_clear: TTL_OUT,
                 eo_shift_direction,
                 wavemeter: WavemeterClient,
                 lock_data_container=DataContainer,
                 siglent_freq_data_container=DataContainer,
                 cavity_ao_frequency=0.,
                 cavity_ao_order=0,
                 core: Core = DummyCore()):
        super().__init__(siglent_ch=siglent_ch,
                         dac_pid=dac_pid,
                         ttl_pid_clear=ttl_pid_clear,
                         eo_shift_direction=eo_shift_direction,
                         wavemeter=wavemeter,
                         lock_data_container=lock_data_container,
                         siglent_freq_data_container=siglent_freq_data_container,
                         cavity_ao_frequency=cavity_ao_frequency,
                         cavity_ao_order=cavity_ao_order,
                         ttl_shutter=ttl_shutter,
                         core=core)
        self.dds_sw = dds_sw

    @kernel
    def on(self):
        self.dds_sw.on()
        self._used = True

    @kernel
    def off(self):
        self.dds_sw.off()

    @kernel
    def pulse(self, t):
        self.dds_sw.on()
        delay(t)
        self.dds_sw.off()

    @kernel
    def init(self, init_siglent=False):
        if init_siglent:
            self.siglent.init()
        self.dds_sw._restore_defaults()
        self.dds_sw.set_dds(init=True)
        self.set_power(self.dac_pid.v)
        self.dds_sw.off()
        self.ttl_shutter.off()

    @kernel
    def reboot(self):
        self.dds_sw.set_dds(amplitude=self.dds_sw._amplitude_default)
        self.ttl_shutter.on()
        delay(3.e-3)


class RydbergTTLSwitchBeam(RydbergBeamBase):
    """980 nm beam: TTL-switched AO, siglent fiber EO frequency control."""
    def __init__(self,
                 siglent_ch: SDG6000X_CH,
                 ttl_sw: TTL_OUT,
                 dac_pid: DAC_CH,
                 ttl_pid_clear: TTL_OUT,
                 eo_shift_direction,
                 wavemeter: WavemeterClient,
                 lock_data_container=DataContainer,
                 siglent_freq_data_container=DataContainer,
                 cavity_ao_frequency=0.,
                 cavity_ao_order=0,
                 core: Core = DummyCore()):
        super().__init__(siglent_ch=siglent_ch,
                         dac_pid=dac_pid,
                         ttl_pid_clear=ttl_pid_clear,
                         eo_shift_direction=eo_shift_direction,
                         wavemeter=wavemeter,
                         lock_data_container=lock_data_container,
                         siglent_freq_data_container=siglent_freq_data_container,
                         cavity_ao_frequency=cavity_ao_frequency,
                         cavity_ao_order=cavity_ao_order,
                         core=core)
        self.ttl_sw = ttl_sw

    @kernel
    def on(self):
        self.ttl_sw.on()
        self._used = True

    @kernel
    def off(self):
        self.ttl_sw.off()

    @kernel
    def init(self, init_siglent=False):
        if init_siglent:
            self.siglent.init()
        self.dac_pid.set(self.dac_pid.v)
        self.ttl_sw.off()