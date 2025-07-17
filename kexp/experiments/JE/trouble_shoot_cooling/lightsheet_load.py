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

        self.p.t_tof = 800.e-6
        # self.xvar('t_tof',np.linspace(600,1500.,10)*1.e-6)
        # self.xvar('t_tof',np.linspace(5.,20.,10)*1.e-3)
        # self.xvar('dumy',np.linspace(1.,500.,200))

        # self.xvar('pfrac_c_gmramp_end',np.linspace(0.01,.15,8))
        # self.xvar('pfrac_r_gmramp_end',np.linspace(0.1,.7,8))
        # self.p.pfrac_c_gmramp_end = 0.03
        # self.p.pfrac_r_gmramp_end = 0.55

        # self.xvar('v_xshim_current_magtrap',np.linspace(0.,4.,8))
        # self.xvar('v_yshim_current_magtrap',np.linspace(0.,3.,10))

        # self.xvar('i_magtrap_init',np.linspace(75.,95.,15))
        # self.p.i_magtrap_init = 94.

        # self.xvar('t_magtrap_ramp',np.linspace(.02,.4,10))
        # self.p.t_magtrap_ramp = .4

        # self.xvar('t_lightsheet_rampup',np.linspace(20.,1000.,15)*1.e-3)
        self.xvar('v_pd_lightsheet_rampup_end',np.linspace(2.,8.,10))
        # self.p.t_lightsheet_rampup = .3
        self.p.v_pd_lightsheet_rampup_end = 5.

        # self.xvar('t_magtrap',np.linspace(.1,3.,15))
        self.p.t_magtrap = .5

        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(3.,8.,10))
        
        self.p.t_lightsheet_hold = .1

        # self.xvar('t_imaging_pulse',np.linspace(1.,20.,20)*1.e-6)
        # self.p.t_imaging_pulse = 2.e-5    
       
        # self.camera_params.exposure_time = 50.e-6
        # self.params.t_imaging_pulse = self.camera_params.exposure_time
        # self.camera_params.em_gain = 1.

        self.p.N_repeats = 1
        self.p.t_mot_load = 1.
        # self.p.amp_imaging = .1
        self.p.imaging_state = 2.

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False)

        delay(self.p.t_lightsheet_hold)

        self.lightsheet.off()

        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel(init_shuttler=False)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
