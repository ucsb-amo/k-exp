from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class mag_trap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=False)

        self.p.t_tof = 20.e-6
        # self.xvar('t_tof',np.linspace(10,15.,20)*1.e-3)
        # self.xvar('t_tof',np.linspace(5.,20.,10)*1.e-3)
        self.xvar('dumy',[0]*5000)

        # self.xvar('t_pump_to_F1',np.linspace(0.05,10.,10)*1.e-6)

        self.p.t_magtrap_hold = .5

        # self.xvar('i_magtrap_init',np.linspace(22.,90,15))
        self.p.i_magtrap_init = 90.

        # self.p.v_yshim_current = 2.2

        # self.p.v_zshim_current_gm = 0.68
        # self.p.v_xshim_current_gm = 0.5 

        # self.p.pfrac_c_gmramp_end = 0.3
        # self.p.pfrac_r_gmramp_end = 0.2

        # self.xvar('v_zshim_current_magtrap',np.linspace(0.,3.,15))
        # self.xvar('v_xshim_current_magtrap',np.linspace(0.,9.,8))
        # self.xvar('v_yshim_current_magtrap',np.linspace(0.,9.,8))
        # self.p.v_zshim_current_magtrap_init = 0.
        # self.p.v_yshim_current_magtrap = 6.
        # self.p.v_xshim_current_magtrap = 0.5
        # self.xvar('t_shim_delay',np.linspace(0.05,15.,20)*1.e-3)
        self.p.t_shim_delay = 3.4e-3

        # self.xvar('t_lightsheet_rampup',np.linspace(10.,2000.,30)*1.e-3)
        self.p.t_lightsheet_rampup = .013
        self.p.v_pd_lightsheet_rampup_end = 3.5

        # self.xvar('t_lightsheet_hold',np.linspace(10.,100.,30)*1.e-3)
        self.p.t_lightsheet_hold = .017

        # self.p.t_magtrap_ramp = .5

        self.p.N_repeats = 1
        self.p.t_mot_load = .75

        self.p.amp_imaging = .35
        self.p.imaging_state = 2.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.set_imaging_detuning(amp=self.p.amp_imaging)
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        # self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.switch_d2_3d(0)
        self.switch_d1_3d(0)

        self.dds.power_down_cooling()

        self.lightsheet.ramp(self.p.t_lightsheet_rampup,
                                self.p.v_pd_lightsheet_rampup_start,
                                self.p.v_pd_lightsheet_rampup_end)

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
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
