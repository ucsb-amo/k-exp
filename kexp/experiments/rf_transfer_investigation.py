from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class rf_scan(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler')

        self.p.imaging_state = 2.
        self.p.rf_yes = 1.
        self.p.t_rf_state_xfer_sweep = 50.e-3
        self.p.n_rf_state_xfer_sweep_steps = 250

        self.p.frequency_rf_state_xfer_sweep_center = 461.7e6
        self.p.frequency_rf_state_xfer_sweep_fullwidth = 0.3e6

        self.xvar('number_of_sweeps',[0,1,2])
        self.p.N_repeats = 5
        # self.xvar('t_repump_flash_imaging',np.linspace(1.,7.,8)*1.e-6)

        self.p.t_mot_load = 0.5

        self.p.t_bias_off_wait = 2.e-3

        self.p.t_lightsheet_hold = 30.e-3
        self.p.t_repump_flash_imaging = 6.e-6

        self.finish_build()

    @kernel
    def scan_kernel(self):
        self.dds.init_cooling()

        self.core.break_realtime()

        if self.p.imaging_state == 1.:
            self.set_imaging_detuning(detuning=self.p.frequency_detuned_imaging_F1)
        else:
            self.set_imaging_detuning()

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.set_shims(v_zshim_current=self.p.v_zshim_current_gm,
                        v_yshim_current=self.p.v_yshim_current_gm,
                          v_xshim_current=self.p.v_xshim_current_gm)
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.release()

        # self.flash_cooler()
        self.flash_repump()
        self.dds.power_down_cooling()

        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
        delay(self.p.t_lightsheet_hold)
        self.set_zshim_magnet_current(self.p.v_zshim_current_op)
        
        t = 1.e-3
        N = int(self.p.number_of_sweeps)
        for n in range(N):
            self.rf.sweep()
            delay(t)
        delay((t+self.p.t_rf_state_xfer_sweep)*(2-self.p.number_of_sweeps))
        
        self.set_zshim_magnet_current()
        delay(self.p.t_bias_off_wait)
        self.lightsheet.off()
        
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


