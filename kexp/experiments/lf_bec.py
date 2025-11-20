from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)


        # self.xvar('frequency_detuned_imaging',np.arange(280.,300.,1)*1.e6)
        # self.xvar('beans',[0]*50)

        # self.xvar('hf_imaging_detuning', [340.e6,420.e6]*1)

        # self.xvar('t_tof',np.linspace(50.,1000.,10)*1.e-6)
        self.p.t_tof = 500.e-6

        # self.xvar('t_tweezer_hold',np.logspace(np.log10(2.e-3), np.log10(100.e-3), 20))
        self.xvar('t_tweezer_hold',np.linspace(2.e-3,100.e-3,20))
        
        self.p.t_tweezer_hold = 3.e-3

        self.p.amp_imaging = .35
        # self.xvar('amp_imaging',np.linspace(0.15,.5,15))

        self.p.t_mot_load = 1.

        self.p.imaging_state = 2
        
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        # self.set_imaging_detuning(frequency_detuned = self.p.frequency_detuned_imaging_m1)
        # self.set_high_field_imaging(i_outer=self.p.i_lf_tweezer_evap2_current,
        #                             pid_bool=False)
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        self.prepare_lf_tweezers()
        
        delay(5.e-3)
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.outer_coil.snap_off()

        delay(self.p.t_tweezer_hold)

        self.tweezer.off()

        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel(setup_slm=False)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)