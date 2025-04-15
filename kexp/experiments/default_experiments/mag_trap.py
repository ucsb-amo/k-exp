from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class mag_trap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        self.p.t_tof = 6000.e-6
        self.xvar('t_tof',np.linspace(7.5,15.,10)*1.e-3)
        # self.xvar('dumy',[0]*1000)

        # self.xvar('v_zshim_current_magtrap_init',np.linspace(0.,3.5,8))
        # self.p.v_zshim_current_magtrap_init = 0.

        # self.xvar('i_magtrap_init',np.linspace(18.,70,8))
        # self.p.i_magtrap_init = 28.

        # self.xvar('v_zshim_current_magtrap',np.linspace(0.,7.,8))
        # self.p.v_zshim_current_magtrap = self.p.v_zshim_current_magtrap_init

        # self.xvar('t_lightsheet_rampup',np.linspace(0.05,1.,10))
        # self.p.t_lightsheet_rampup = 

        # self.p.t_magtrap_ramp = .5

        self.p.N_repeats = 3
        self.p.t_mot_load = .2

        self.p.amp_imaging = .15
        self.p.imaging_state = 2.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.set_imaging_detuning(amp=self.p.amp_imaging)
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet(do_lightsheet_ramp=False,do_magtrap_rampdown=False)
        self.inner_coil.snap_off()

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
