from artiq.language import TFloat

from waxx.control.misc.sdg6000x import SDG6000X_CH, dv, SDG6000X_Params
from waxx.control.artiq.TTL import TTL_OUT
from waxx.control.artiq.DAC_CH import DAC_CH
from waxx.control.artiq.DDS import DDS
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
    def set_power(self,amplitude):
        self.dds_sw.set_dds(amplitude=amplitude)

class SiglentTTLBeam(SiglentBeamBase):
    def __init__(self,
                  siglent_ch:SDG6000X_CH,
                  ttl_sw:TTL_OUT):
        super().__init__(siglent_ch=siglent_ch)
        self.ttl_sw = ttl_sw

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

class RydbergLasers():
    def __init__(self,
                 siglent_405_cavity:SDG6000X_CH,
                 dac_pid_setpoint_405:DAC_CH,
                 dds_sw_405:TTL_OUT,
                 siglent_980_cavity:SDG6000X_CH,
                 dac_pid_setpoint_980:DAC_CH,
                 ttl_sw_980:TTL_OUT):
        
        self.beam_405 = SiglentDDSBeam(siglent_ch=siglent_405_cavity,
                                    dac_pid_setpoint=dac_pid_setpoint_405,
                                    dds_sw=dds_sw_405)
        self.beam_980 = SiglentTTLBeam(siglent_ch=siglent_980_cavity,
                                    dac_pid_setpoint=dac_pid_setpoint_980,
                                    ttl_sw=ttl_sw_980)
        
        self._p = RydbergLaser_Params(ry_405_params=self.beam_405._p,
                                      ry_980_params=self.beam_980._p)
        
class CavityAOControlledRyDDSBeam(SiglentDDSBeam):
    def __init__(self,
                siglent_ch:SDG6000X_CH,
                dds_sw:DDS,
                ao_order_cavity=-1,
                ao_order_pid=1,
                frequency_pid_ao=80.e6):
        super().__init__(siglent_ch,dds_sw=dds_sw)

        self._ao_order_cavity = ao_order_cavity
        self._ao_order_pid = ao_order_pid
        self._frequency_pid_ao = frequency_pid_ao
        self._f_siglent_detuning_reference = self.siglent._p.frequency

    @kernel
    def set_detuning(self,frequency_detuned):
        f_ao = self.compute_detuning(frequency_detuned)
        self.siglent.set(frequency=f_ao)

    @portable(flags={"fast-math"})
    def compute_detuning(self,frequency_detuned) -> TFloat:
        delta = frequency_detuned
        a_c = self._ao_order_cavity
        f_0 = self._f_siglent_detuning_reference
        a_pid = self._ao_order_pid
        f_pid = self._frequency_pid_ao
        a_sw = self.dds_sw.aom_order
        f_sw = self.dds_sw.frequency
        # print(delta,a_c,f_0,a_pid,f_pid,a_sw,f_sw)
        f_ao = f_0 + (delta-2*a_pid*f_pid-2*a_sw*f_sw)/(-2*a_c)
        return f_ao