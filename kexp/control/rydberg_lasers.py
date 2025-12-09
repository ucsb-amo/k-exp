from waxx.control.misc.sdg6000x import SDG6000X_CH, dv
from waxx.control.artiq.TTL import TTL_OUT
from waxx.control.artiq.DAC_CH import DAC_CH

class RydbergLasers():
    def __init__(self,
                 siglent_405_cavity:SDG6000X_CH,
                 dac_pid_setpoint_405:DAC_CH,
                 ttl_sw_405:TTL_OUT,
                 siglent_980_cavity:SDG6000X_CH,
                 dac_pid_setpoint_980:DAC_CH,
                 ttl_sw_980:TTL_OUT):
        
        self.siglent_cavity_405 = siglent_405_cavity
        self.dac_pid_setpoint_405 = dac_pid_setpoint_405
        self.ttl_sw_405 = ttl_sw_405

        self.siglent_cavity_980 = siglent_980_cavity
        self.dac_pid_setpoint_980 = dac_pid_setpoint_980
        self.ttl_sw_980 = ttl_sw_980

    def set_405(self,frequency=dv,amplitude=dv):
        