from waxx.control.misc.sdg6000x import SDG6000X_CH, dv
from waxx.control.artiq.TTL import TTL_OUT
from waxx.control.artiq.DAC_CH import DAC_CH
from waxx.control.artiq.DDS import DDS
from artiq.language import now_mu, kernel, delay, portable

class SiglentPIDBeam():
    def __init__(self,
                 siglent_ch:SDG6000X_CH,
                 dac_pid_setpoint:DAC_CH):
        self.siglent = siglent_ch
        self.dac_pid = dac_pid_setpoint
        self._sync_params()
        
    @kernel
    def init(self):
        self.set_siglent(init=True)
        self.siglent.set_output(1)

    @kernel
    def set_siglent(self,
            frequency=dv,
            amplitude=dv,
            init=False):
        self.siglent.set(frequency=frequency,
                         amplitude=amplitude,
                         init=init)
        self._sync_params()

    @kernel
    def set_power(self, v_pd=dv, load_dac=True):
        self.dac_pid.set(v_pd, load_dac)
        self._sync_params()
        
    @portable
    def _sync_params(self):
        self.frequency = self.siglent.frequency
        self.amplitude_vpp = self.siglent.amplitude_vpp
        self.siglent_output = self.siglent.state
        self.v_pd = self.dac_pid.v

class SiglentDDSBeam(SiglentPIDBeam):
    def __init__(self,
                  siglent_ch:SDG6000X_CH,
                  dac_pid_setpoint:DAC_CH,
                  dds_sw:DDS):
        super().__init__(siglent_ch=siglent_ch,
                         dac_pid_setpoint=dac_pid_setpoint)
        self.dds_sw = dds_sw
    
    @kernel
    def init(self):
        super().init()
        self.dds_sw.set_dds(init=True)

    def on(self):
        self.dds_sw.on()

    def off(self):
        self.dds_sw.off()

class SiglentTTLBeam(SiglentPIDBeam):
    def __init__(self,
                  siglent_ch:SDG6000X_CH,
                  dac_pid_setpoint:DAC_CH,
                  ttl_sw:TTL_OUT):
        super().__init__(siglent_ch=siglent_ch,
                         dac_pid_setpoint=dac_pid_setpoint)
        self.ttl_sw = ttl_sw

    def on(self):
        self.ttl_sw.on()

    def off(self):
        self.ttl_sw.off()

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