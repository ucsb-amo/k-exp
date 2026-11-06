from waxx.control.misc.sdg6000x import SDG6000X_CH
from waxx.config.siglent_id import siglent_frame as siglent_frame_waxx
from artiq.coredevice.core import Core

IP_RY_CAVITY_SIGLENT = "192.168.1.101"
IP_LIGHTSHEET_SIGLENT = "192.168.1.126"   # drives the lightsheet AO (2026-11-05)

class siglent_frame(siglent_frame_waxx):
    def __init__(self, core=Core):

        self.setup(core)

        self.siglent_980 = self.assign_sdg6000x_ch(1,IP_RY_CAVITY_SIGLENT,
                                                   frequency=417.0e6,
                                                   amplitude_vpp=0.190,
                                                   max_amplitude_vpp=0.632,
                                                   min_frequency=50.e6,
                                                   max_frequency=499.e6)
        self.siglent_405 = self.assign_sdg6000x_ch(2,IP_RY_CAVITY_SIGLENT,
                                                   frequency=459.0e6,
                                                   amplitude_vpp=0.125,
                                                   max_amplitude_vpp=1.0,
                                                   max_frequency=500.e6,
                                                   min_frequency=65.e6)

        # Lightsheet AO RF, painting test: fixed 80 MHz carrier, sine FM for
        # painting. Never more than 2 Vpp: a request above it is refused
        # before anything is sent. FM defaults (applied by init()) are the
        # siglent_fm_control.ipynb targets: 100 kHz rate, 2 MHz deviation
        # (carrier swings 78-82 MHz). Guards: deviation <= 10 MHz, rate <= 1 MHz.
        self.siglent_lightsheet_paint = self.assign_sdg6000x_fm_ch(1, IP_LIGHTSHEET_SIGLENT,
                                                   frequency_carrier=80.e6,
                                                   max_amplitude_vpp=2.0,
                                                   fm_deviation=2.e6,
                                                   fm_rate=100.e3,
                                                   max_fm_deviation=10.e6,
                                                   max_fm_rate=1.e6)

        self.cleanup()