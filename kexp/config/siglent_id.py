from waxx.control.misc.sdg6000x import SDG6000X_CH
from waxx.config.siglent_id import siglent_frame as siglent_frame_waxx
from artiq.coredevice.core import Core

class siglent_frame(siglent_frame_waxx):
    def __init__(self, core=Core):

        self.setup(core)
        
        self.cleanup()