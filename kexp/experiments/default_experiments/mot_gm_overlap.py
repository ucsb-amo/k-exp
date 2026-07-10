from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, cameras, img_types
import numpy as np
from kexp.calibrations import high_field_imaging_detuning

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class mag_trap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      setup_camera=True,
                      camera_select=cameras.xy_basler,
                      save_data=False)

        self.p.t_tof = 15.e-3
        # self.xvar('t_tof',np.linspace(4,20.,14)*1.e-3)
        # self.xvar('dumy',[0,1,2,3])
        # self.xvar('dumy',[0,1]*500)
        # self.p.dumy=1

        self.p.t_magtrap_hold = .15
        
        self.p.t_magtrap = .1

        self.p.t_lightsheet_hold = .15

        self.p.N_repeats = 1
        self.p.t_mot_load = 1.0

        # self.camera_params.exposure_time = 100.e-6
        # self.params.t_imaging_pulse = self.camera_params.exposure_time
        # self.camera_params.gain = 1.


        self.p.pfrac_d1_c_gm = 0.94
        self.p.pfrac_d1_r_gm = 0.9

        self.p.pfrac_c_gmramp_end = 0.46
        self.p.pfrac_r_gmramp_end = 0.25

        self.p.amp_imaging = .2
        self.p.imaging_state = 2.

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        if self.p.dumy == 0:
            self.mot(self.p.t_mot_load)
            self.dds.push.off()
            self.release()
            
        elif self.p.dumy == 1:
            self.mot(self.p.t_mot_load)
            self.dds.push.off()
            self.cmot_d1(self.p.t_d1cmot * s,)
            
            self.gm(self.p.t_gm * s)
            self.gm_ramp(self.p.t_gmramp)
            self.release()

        
        # self.dds.mot_killer.on()

        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()

        # self.dds.mot_killer.off()

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
