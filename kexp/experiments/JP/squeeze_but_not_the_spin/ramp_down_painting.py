from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.util.artiq.async_print import aprint

class squeezeme(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)
        
        self.xvar('ramp_paint_off',[0,1])
        self.p.ramp_paint_off = 1

        self.p.amp_imaging = self.camera_params.amp_imaging

        self.p.t_tof = 100.e-6
        self.p.N_repeats = 5

        # self.p.t_ramp_down_painting_amp = 15.e-3
        # self.xvar('t_ramp_down_painting_amp',np.linspace(1.,100.,4)*1.e-3)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers()

        v0 = self.tweezer.paint_amp_dac.v
        aprint(v0)
        # if self.p.ramp_paint_off:
        #     self.tweezer.paint_amp_dac.linear_ramp(t=self.p.t_ramp_down_painting_amp,v_start=v0,v_end=-7.,n=100)
        # else:
        #     delay(self.p.t_ramp_down_painting_amp)

        if self.p.ramp_paint_off:
            self.tweezer.paint_amp_dac.set(-7.)
        else:
            pass

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