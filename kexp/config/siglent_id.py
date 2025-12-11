from waxx.control.misc.sdg6000x import SDG6000X_CH
from artiq.coredevice.core import Core

class siglent_frame():
    def __init__(self, core=Core):

        self.core = core

        IP_RY_CAVITY_SIGLENT = "192.168.1.101"
        self.siglent_980 = self.assign_sdg6000x_ch(1,IP_RY_CAVITY_SIGLENT,
                                                   frequency=51.e6,
                                                   amplitude_vpp=0.885,
                                                   max_amplitude_vpp=1.)
        self.siglent_405 = self.assign_sdg6000x_ch(2,IP_RY_CAVITY_SIGLENT,
                                                   frequency=209.65e6,
                                                   amplitude_vpp=1.2,
                                                   max_amplitude_vpp=1.5)

    def assign_sdg6000x_ch(self, ch, ip,
                           frequency,
                           amplitude_vpp,
                           max_amplitude_vpp,
                           default_state=1) -> SDG6000X_CH:
        siglent_ch = SDG6000X_CH(ch=ch,ip=ip,
                           frequency=frequency,
                           amplitude_vpp=amplitude_vpp,
                           max_amplitude_vpp=max_amplitude_vpp,
                           default_state = default_state,
                           core=self.core)
        return siglent_ch