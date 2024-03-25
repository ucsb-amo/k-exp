from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class pi_pulse(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler')
        

        self.xvar('t_rf_pulse',np.linspace(0.1,10.,20)*1.e-3)

        self.p.t_mot_load = 1.
        self.p.t_lightsheet_hold = 50.e-3

        self.finish_build()

    @kernel
    def scan_kernel(self):
        self.dds.init_cooling()

        self.core.break_realtime()

        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        self.set_shims(v_zshim_current=self.p.v_zshim_current_gm,
                        v_yshim_current=self.p.v_yshim_current_gm,
                          v_xshim_current=self.p.v_xshim_current_gm)
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.release()
        self.flash_cooler()

        self.dds.power_down_cooling()

        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
        self.set_shims()
        delay(self.p.t_lightsheet_hold)
        
        self.ttl.antenna_rf_sw.on()
        delay(self.p.t_rf_pulse)
        self.ttl.antenna_rf_sw.off()

        self.lightsheet.off()
        
        delay(self.p.t_tof)
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        self.set_imaging_detuning(detuning=self.p.frequency_detuned_imaging_F1)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)


