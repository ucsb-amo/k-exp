from waxx.control.misc.sdg6000x import SDG6000X_CH
from waxx.config.siglent_id import siglent_frame as siglent_frame_waxx
from artiq.coredevice.core import Core

class siglent_frame(siglent_frame_waxx):
    def __init__(self, core=Core):

        self.setup(core)

        IP_RY_CAVITY_SIGLENT = "192.168.1.101"
        self.siglent_980 = self.assign_sdg6000x_ch(1,IP_RY_CAVITY_SIGLENT,
                                                   frequency=51.e6,
                                                   amplitude_vpp=0.885,
                                                   max_amplitude_vpp=1.)
        self.siglent_405 = self.assign_sdg6000x_ch(2,IP_RY_CAVITY_SIGLENT,
                                                   frequency=80.0e6,
                                                   amplitude_vpp=0.362,
                                                   max_amplitude_vpp=1.0)
        
        self.cleanup()