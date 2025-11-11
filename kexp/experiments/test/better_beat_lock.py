from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.util.artiq.async_print import aprint

class beat_lock_improvement(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)
        
        self.camera_params.exposure_time = 20.e-6
        self.params.t_imaging_pulse = self.camera_params.exposure_time

        self.p.beans = 0

        self.p.t_tof = 2.e-6

        self.p.frequency_raman_transition = 41.2e6
        self.p.amp_raman = 0.35
        
        self.p.t_tweezer_hold = .01e-3

        self.p.amp_imaging = .5

        self.p.phase_slm_mask = .5 * np.pi
        self.p.t_mot_load = 1.
        
        self.p.N_repeats = 1

        # self.dds.imaging.frequency = 375.e6
        self.xvar('new_ao_img_setting',[0,1])
        self.p.new_ao_img_setting = 1

        self.xvar('frequency_detuned_imaging',np.arange(620,648,6)*1.e6)
        # self.p.frequency_detuned_imaging = 632.e6

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        if self.p.new_ao_img_setting:
            self.dds.imaging.set_dds(frequency=375.e6)
            self.p.amp_imaging = 0.5
        else:
            self.dds.imaging.set_dds(frequency=350.e6)
            self.p.amp_imaging = 0.07

        self.set_imaging_detuning(frequency_detuned = self.p.frequency_detuned_imaging)
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        self.prepare_lf_tweezers()

        self.init_raman_beams(self.p.frequency_raman_transition,self.p.amp_raman)
        self.ttl.line_trigger.wait_for_line_trigger()

        delay(5.7e-3)

        self.raman.pulse(t=self.p.t_raman_pi_pulse)

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)

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