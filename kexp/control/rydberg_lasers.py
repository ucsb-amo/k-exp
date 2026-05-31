from artiq.language import TFloat
from artiq.coredevice.core import Core

from waxx.control.artiq.dummy_core import DummyCore
from waxx.control.misc.sdg6000x import SDG6000X_CH, dv, SDG6000X_Params
from waxx.control.artiq.TTL import TTL_OUT
from waxx.control.artiq.DAC_CH import DAC_CH
from waxx.control.artiq.DDS import DDS

from waxx.control.misc.moglabs_wavemeter import WavemeterClient, DummyWavemeterClient
from kexp.config.ip import WAVEMETER_MOGLABS_IP
from kexp.config.data_vault import DataVault, DataContainer

from artiq.language import now_mu, kernel, delay, portable

def remap_class(base_obj, target_class):
    return target_class(**base_obj.__dict__)

class SiglentPID_Params(SDG6000X_Params):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.v_pd = 0.

class SiglentBeamBase():
    def __init__(self,siglent_ch:SDG6000X_CH):
        self.siglent = siglent_ch
        self._p_siglent = siglent_ch._p

    @kernel
    def init(self):
        self.siglent.init()

    @kernel
    def set_siglent(self,
            frequency=dv,
            amplitude=dv,
            init=False):
        self.siglent.set(frequency=frequency,
                         amplitude=amplitude,
                         init=init)
        
class SiglentDDSBeam(SiglentBeamBase):
    def __init__(self,
                  siglent_ch:SDG6000X_CH,
                  dds_sw:DDS):
        super().__init__(siglent_ch=siglent_ch)
        self.dds_sw = dds_sw
    
    @kernel
    def init(self):
        SiglentBeamBase.init(self)
        # self.siglent.init()
        self.dds_sw.set_dds(init=True)

    @kernel
    def on(self):
        self.dds_sw.on()

    @kernel
    def off(self):
        self.dds_sw.off()

    @kernel
    def pulse(self,t):
        self.dds_sw.on()
        delay(t)
        self.dds_sw.off()

    @kernel
    def set_power(self,amplitude):
        self.dds_sw.set_dds(amplitude=amplitude)

class SiglentTTLBeam(SiglentBeamBase):
    def __init__(self,
                  siglent_ch:SDG6000X_CH,
                  ttl_sw:TTL_OUT):
        super().__init__(siglent_ch=siglent_ch)
        self.ttl_sw = ttl_sw

    @kernel
    def init(self):
        SiglentBeamBase.init(self)

    @kernel
    def on(self):
        self.ttl_sw.on()

    @kernel
    def off(self):
        self.ttl_sw.off()

    @kernel
    def set_power(self):
        raise ValueError('No power control configured!')

class SiglentBeamPID(SiglentBeamBase):
    def __init__(self,
                 siglent_ch:SDG6000X_CH,
                 dac_pid_setpoint:DAC_CH):
        super().__init__(self,siglent_ch)

        self.dac_pid = dac_pid_setpoint

        self._p = remap_class(self._p_siglent, SiglentPID_Params)
        self._p.v_pd = self.dac_pid.v

    @kernel
    def set_power(self, v_pd=dv, load_dac=True):
        self.dac_pid.set(v_pd, load_dac)

class SiglentDDSBeamPID(SiglentDDSBeam,SiglentBeamPID):
    def __init__(self,
                  siglent_ch:SDG6000X_CH,
                  dds_sw:DDS,
                  dac_pid_setpoint:DAC_CH):
        super().__init__(siglent_ch=siglent_ch,
                         dds_sw=dds_sw,
                         dac_pid_setpoint=dac_pid_setpoint)

class SiglentTTLBeamPID(SiglentTTLBeam,SiglentBeamPID):
    def __init__(self,
                  siglent_ch:SDG6000X_CH,
                  dac_pid_setpoint:DAC_CH,
                  ttl_sw:TTL_OUT):
        super().__init__(siglent_ch=siglent_ch,
                         ttl_sw=ttl_sw,
                         dac_pid_setpoint=dac_pid_setpoint)

class RydbergLaser_Params():
    def __init__(self,
                ry_405_params: SiglentPID_Params,
                ry_980_params: SiglentPID_Params):
        self._p_405 = ry_405_params
        self._p_980 = ry_980_params
        
class FixedRyDDSBeamPID():
    def __init__(self,
                dds_sw:DDS,
                dac_pid:DAC_CH,
                ttl_shutter:TTL_OUT,
                wavemeter:WavemeterClient,
                lock_data_container = DataContainer,
                core:Core = DummyCore()
                ):
        self.dds_sw = dds_sw
        self.dac_pid = dac_pid
        self.ttl_shutter = ttl_shutter
        self._wavemeter = wavemeter
        self._core = core
        self._dc = lock_data_container

    @kernel
    def set_power(self, v):
        self.dac_pid.set(v)

    @kernel
    def on(self):
        self.dds_sw.on()

    @kernel
    def off(self):
        self.dds_sw.off()
    
    @kernel
    def init(self):
        self.dds_sw._restore_defaults()
        self.dds_sw.set_dds(init=True)
        self.set_power(self.dac_pid.v)
        self.dds_sw.off()
        self.ttl_shutter.off()

    @kernel
    def reboot(self):
        self.dds_sw.set_dds(amplitude=self.dds_sw._amplitude_default)
        self.ttl_shutter.on()

    @kernel
    def lock_status(self):
        self._core.wait_until_mu(now_mu())
        lock_bool = self._wavemeter.lock_status()
        self._dc.put_data(lock_bool)
        self._core.break_realtime()

class FiberEORyDDSBeamPID(SiglentTTLBeam):
    def __init__(self,
                siglent_ch:SDG6000X_CH,
                dac_pid:DAC_CH,
                ttl_ao_sw:TTL_OUT,
                eo_sideband_order,
                wavemeter:WavemeterClient,
                lock_data_container = DataContainer,
                core:Core = DummyCore()
                ):
        super().__init__(siglent_ch=siglent_ch,
                         ttl_sw=ttl_ao_sw)

        self.dac_pid = dac_pid
        self.siglent._stash_defaults()

        self._eo_order = eo_sideband_order

        self._wavemeter = wavemeter
        self._dc = lock_data_container
        self._core = core

    @kernel
    def set_power(self, v_pd=dv, load_dac=True):
        self.dac_pid.set(v_pd, load_dac)
    
    @kernel
    def init(self):
        self.siglent.init()
        self.dac_pid.set(self.dac_pid.v)
        self.ttl_sw.off()

    @kernel
    def sweep_to(self,
                frequency_end=dv,
                frequency_step=1.e6,
                reset=False):
        self.siglent.sweep(frequency_end, frequency_step, reset)

    @kernel
    def lock_status(self, robust=True):
        self._core.wait_until_mu(now_mu())
        self.siglent.fetch_state()
        frequency_shift = - self._eo_order * self.siglent._p.frequency
        lock_bool = self._wavemeter.lock_status(frequency_shift, robust)
        self._dc.put_data(lock_bool)
        self._core.break_realtime()

# class FiberEOControlledRyDDSBeam(SiglentTTLBeam):
#     def __init__(self,
#                 siglent_ch:SDG6000X_CH,
#                 ttl_ao_sw=TTL_OUT):
#         super().__init__(siglent_ch=siglent_ch,
#                          ttl_sw=ttl_ao_sw)

#         self.siglent._stash_defaults()
    
#     @kernel
#     def init(self):
#         self.siglent.init()
#         self.ttl_sw.off()

#     @kernel
#     def sweep_to(self,
#                 frequency_end=dv,
#                 frequency_step=1.e6,
#                 reset=False):
#         self.siglent.sweep(frequency_end, frequency_step, reset)

# class CavityAOControlledRyDDSBeam(SiglentDDSBeam):
#     def __init__(self,
#                 siglent_ch:SDG6000X_CH,
#                 dds_sw:DDS,
#                 # wavemeter_object,
#                 ao_order_cavity=-1,
#                 ao_order_pid=1,
#                 frequency_pid_ao=80.e6):
#         super().__init__(siglent_ch,dds_sw=dds_sw)

#         self._ao_order_cavity = ao_order_cavity
#         self._ao_order_pid = ao_order_pid
#         self._frequency_pid_ao = frequency_pid_ao
#         self._f_siglent_detuning_reference = self.siglent._p.frequency

#         # self.wavemeter = wavemeter_object

#         self.siglent._stash_defaults()

#     @kernel
#     def set_detuning(self,frequency_detuned):
#         f_ao = self.detuning_to_cavity_ao_frequency(frequency_detuned)
#         self.siglent.set(frequency=f_ao)

#     @portable(flags={"fast-math"})
#     def detuning_to_cavity_ao_frequency(self,frequency_detuned) -> TFloat:
#         delta = frequency_detuned
#         a_c = self._ao_order_cavity
#         f_0 = self._f_siglent_detuning_reference
#         a_pid = self._ao_order_pid
#         f_pid = self._frequency_pid_ao
#         a_sw = self.dds_sw.aom_order
#         f_sw = self.dds_sw.frequency
#         f_ao = f_0 + (delta-2*a_pid*f_pid-2*a_sw*f_sw)/(-2*a_c)
#         return f_ao

# class RydbergLasers():
#     def __init__(self,
#                  siglent_405_cavity:SDG6000X_CH,
#                  dac_pid_setpoint_405:DAC_CH,
#                  dds_sw_405:TTL_OUT,
#                  siglent_980_cavity:SDG6000X_CH,
#                  dac_pid_setpoint_980:DAC_CH,
#                  ttl_sw_980:TTL_OUT):
        
#         self.beam_405 = SiglentDDSBeam(siglent_ch=siglen t_405_cavity,
#                                     dac_pid_setpoint=dac_pid_setpoint_405,
#                                     dds_sw=dds_sw_405)
#         self.beam_980 = SiglentTTLBeam(siglent_ch=siglent_980_cavity,
#                                     dac_pid_setpoint=dac_pid_setpoint_980,
#                                     ttl_sw=ttl_sw_980)
        
#         self._p = RydbergLaser_Params(ry_405_params=self.beam_405._p,
#                                       ry_980_params=self.beam_980._p)