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

        self.p.t_tof = 50.e-6
        # self.p.t_tof = 10.e-3
        # self.xvar('t_tof',np.linspace(10,15.,20)*1.e-3)
        # self.xvar('t_tof',np.linspace(5.,10.,10)*1.e-3)
        self.xvar('dumy',[0]*1000)

        self.p.N_repeats = 1
        self.p.t_mot_load = .3

        # self.p.amp_imaging = .35
        self.p.imaging_state = 2.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.dds.mot_killer.set_dds_gamma(delta=0.,amplitude=.188)

        # self.set_imaging_detuning(amp=self.p.amp_imaging)
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        # self.switch_d2_2d(1)
        # self.mot(self.p.t_mot_load)
        # self.dds.push.off()
        # self.cmot_d1(self.p.t_d1cmot * s)
        
        # self.gm(self.p.t_gm * s)
        # self.gm_ramp(self.p.t_gmramp)

        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot)
        self.ttl.pd_scope_trig.pulse(1.e-6)

        self.dds.mot_killer.on()

        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)


        self.release()

        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()

        self.dds.mot_killer.off()

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
