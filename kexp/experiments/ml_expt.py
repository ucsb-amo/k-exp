
from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning
from kexp import Base, img_types, cameras

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class mag_trap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                    camera_select=cameras.xy_basler,
                    imaging_type=img_types.ABSORPTION)

        self.p.t_tof = 1000.e-6
        # self.xvar('t_tof',np.linspace(30.,800.,10)*1.e-6)


        self.p.detune_d2_c_mot = -2.332302064638446
        self.p.detune_d2_r_mot = -3.444983275369704
        self.p.i_mot = 18.817406988865596
        self.p.v_zshim_current = 0.8750233625808322
        self.p.v_xshim_current = 4.872896494456264
        self.p.v_yshim_current = 0.38120271821203144
        self.p.detune_d1_c_d1cmot = 6.42211080739627
        self.p.detune_d2_r_d1cmot = -3.1210092125229347
        self.p.pfrac_d1_c_d1cmot = 0.39788228108742474
        self.p.amp_d2_r_d1cmot = 0.04634979088196418
        self.p.v_zshim_current_gm = 0.7308106708244009
        self.p.v_xshim_current_gm = 0.15605981817747916
        self.p.v_yshim_current_gm = 2.8274886450273353
        self.p.pfrac_d1_c_gm = 0.35542517161859927
        self.p.pfrac_d1_r_gm = 0.5569322341760277
        self.p.pfrac_c_gmramp_end = 0.9092736467351692
        self.p.pfrac_r_gmramp_end = 0.8829975205123101
        self.p.i_magtrap_init = 64.93300962581476
        self.p.v_xshim_current_magtrap = 2.782658114907693
        self.p.v_yshim_current_magtrap = 2.209217395048822
        self.p.t_magtrap = 1.8053964648583072
        self.p.v_pd_lightsheet_rampup_end = 6.071651954258954

        self.p.t_magtrap_hold = .15

        self.p.imaging_state = 2.

        self.p.N_repeats = 3
        self.p.t_mot_load = 1.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot)
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False)
        self.set_shims(0.,0.,0.)

        delay(self.p.t_lightsheet_hold)

        self.lightsheet.off()

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

