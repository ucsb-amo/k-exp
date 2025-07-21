
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


        self.p.detune_d2_c_mot = -4.1721607748274385
        self.p.detune_d2_r_mot = -4.543539276702662
        self.p.i_mot = 14.491834920959395
        self.p.v_zshim_current = 0.35307322260919705
        self.p.v_xshim_current = 1.4504538744093922
        self.p.v_yshim_current = 3.779290168959914
        self.p.detune_d1_c_d1cmot = 6.982392033562361
        self.p.detune_d2_r_d1cmot = -2.193051583254427
        self.p.pfrac_d1_c_d1cmot = 0.20656842106067091
        self.p.amp_d2_r_d1cmot = 0.08107506467001911
        self.p.v_zshim_current_gm = 0.8988008778048011
        self.p.v_xshim_current_gm = 0.42162187983303423
        self.p.v_yshim_current_gm = 3.9899973058395206
        self.p.pfrac_d1_c_gm = 0.3329266263580387
        self.p.pfrac_d1_r_gm = 0.22287920865008354
        self.p.pfrac_c_gmramp_end = 0.12440349170460346
        self.p.pfrac_r_gmramp_end = 0.17777274359373202
        self.p.i_magtrap_init = 69.2140627489045
        self.p.v_xshim_current_magtrap = 1.8454681843789633
        self.p.v_yshim_current_magtrap = 1.0104601540986202

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

