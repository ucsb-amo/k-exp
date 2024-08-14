from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class test_5_ls_hold(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select="andor",save_data=True)

        self.p.imaging_state = 2.

        # self.xvar('dummy',[1,1])

        self.xvar('t_lightsheet_hold',np.linspace(50.,2000.,10)*1.e-3)

        self.p.v_pd_lightsheet_rampup_start = 0.
        self.p.v_pd_lightsheet_rampup_end = 4.5

        self.p.t_tof = 3.e-6
        self.camera_params.amp_imaging = .07
        self.p.t_imaging_pulse = 5.e-6
        self.camera_params.exposure_time = 5.e-6
        self.camera_params.em_gain = 290.
        self.p.t_mot_load = .5
        
        self.p.t_lightsheet_rampup = 15.e-3
        self.p.t_lightsheet_hold = 40.e-3

        self.camera_params.amp_imaging = .3

        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.dds.init_cooling()

        self.set_imaging_detuning(detuning=self.p.frequency_detuned_imaging)

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot)
        self.set_shims(v_zshim_current=self.p.v_zshim_current_gm,
                        v_yshim_current=self.p.v_yshim_current_gm,
                          v_xshim_current=self.p.v_xshim_current_gm)

        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.release()

        self.flash_cooler()

        self.ttl.pd_scope_trig.on()
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
        delay(self.p.t_lightsheet_hold)
        self.lightsheet.off()
        self.ttl.pd_scope_trig.off()

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