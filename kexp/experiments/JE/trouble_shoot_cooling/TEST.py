from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning
from kexp import Base, img_types, cameras
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class mag_trap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                    camera_select=cameras.xy_basler,
                    imaging_type=img_types.ABSORPTION)
        
        self.p.t_tof = 9000.e-6
        # self.xvar('t_tof',np.linspace(30.,800.,10)*1.e-6)
                        
        # {assignment_lines}

        self.p.t_magtrap_hold = .15

        self.p.imaging_state = 2.

        self.p.N_repeats = 1
        self.p.t_mot_load = .3

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot)
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet(do_lightsheet_ramp=False,
                            do_magtrap_rampup=False,
                            do_magtrap_hold=False,
                            do_magtrap_rampdown=False)
        delay(self.p.t_magtrap_hold)
        self.inner_coil.snap_off()

        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        # self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)