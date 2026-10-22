import numpy as np
from artiq.experiment import kernel, TFloat, TArray
from artiq.coredevice.sampler import Sampler

from waxx.config.sampler_id import sampler_frame as sampler_frame_waxx
from waxx.control.artiq.Sampler_CH import Sampler_CH

class sampler_frame(sampler_frame_waxx):
    def __init__(self, sampler_device = Sampler):

        self.setup(sampler_device)

        ### gains:
        # gain = 0: +/- 10.0 V
        # gain = 1: +/- 1.0 V
        # gain = 2: +/- 0.1 V
        # gain = 2: +/- 0.01 V
        
        ### begin assignments
 
        # self.reference_beam_pd = self.sampler_assign(0,gain=0) # ch0 -> tweezer PID1 PD, 2026-10-20

    # tweezer servo photodiodes (kexp.control.awg_tweezer.tweezer.read_pds)
        self.tweezer_pid1_pd = self.sampler_assign(0,gain=0)
        self.tweezer_pid2_pd = self.sampler_assign(1,gain=0)

        # coil current transducers (user, 2026-10-21; for the coil-reset
        # timing measurement). Not read by any sequence yet.
        # Inner: 20 A/V (user 2026-10-21) -> 8.5 V at the 170 A max_current.
        # Outer: 40 A/V (user 2026-10-21; a different transducer from the
        # 60 A/V one that experiments/calibration/
        self.inner_coil_transducer = self.sampler_assign(2,gain=0)
        self.outer_coil_transducer = self.sampler_assign(3,gain=0)

        self.apd_integrator = self.sampler_assign_lastch(7,gain=0)

        ### end assignments

        self.cleanup()