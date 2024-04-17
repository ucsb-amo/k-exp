from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class rf_scan(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        self.p.imaging_state = 2.
        # self.xvar('imaging_state',[2,1])
        self.p.t_rf_state_xfer_sweep = 100.e-3
        self.p.n_rf_state_xfer_sweep_steps = 2000
        # self.p.frequency_rf_sweep_state_prep_center = 459.3543e6
        self.p.frequency_rf_sweep_state_prep_fullwidth = 50.e3

        self.p.t_lightsheet_rampup = 10.e-3

        # self.xvar('t_rf_state_xfer_sweep',np.linspace(20.,100.,10)*1.e-3)

        # self.xvar('high_field_current',np.linspace(80.,100.,3))

        # self.p.high_field_current = 90.

        self.xvar('frequency_rf_sweep_state_prep_center',185.2e6 + np.linspace(-1.,1.,40)*1.e6)
        self.p.do_sweep = 1

        self.high_field_ramp_start = 0.
        self.high_field_ramp_end = 90.

        self.t_high_field_ramp = 22.e-3
        self.high_field_ramp_steps = 1000
        self.dt_high_field_ramp = self.t_high_field_ramp / self.high_field_ramp_steps

        self.high_field_ramp_list = np.linspace(self.high_field_ramp_start,
                                                self.high_field_ramp_end,
                                                self.high_field_ramp_steps)
        
        self.high_field_ramp_down_list = np.flip(self.high_field_ramp_list)

        self.p.t_optical_pumping = 100.e-6

        self.p.t_lightsheet_hold = 10.e-3

        self.p.t_mot_load = 0.5
        self.p.t_bias_off_wait = 2.e-3
        self.p.t_repump_flash_imaging = 10.e-6
        self.p.t_tof = 20.e-6

        # self.p.N_repeats = [1,2]

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

        self.outer_coil.on(i_supply=0.)

        self.flash_cooler()
        # self.flash_repump(t=self.p.t_repump_flash_imaging)

        self.dds.power_down_cooling()

        self.set_shims(v_zshim_current=0.,
                       v_yshim_current=self.p.v_zshim_current_gm,
                        v_xshim_current=self.p.v_zshim_current_gm)

        # self.optical_pumping(self.p.t_optical_pumping,v_anti_zshim_current=0.,v_zshim_current=0.)
        
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
        delay(10.e-3)

        delay(-10.e-3)
        for i in self.high_field_ramp_list:
            self.outer_coil.on(i_supply=i)
            delay(self.dt_high_field_ramp)
        delay(100.e-3)
        # delay(22.e-3)

        # delay(10*ms)
        if self.p.do_sweep:
            self.rf.sweep(frequency_sweep_list=self.p.frequency_rf_sweep_state_prep_list)
        # delay(100*ms)

        # self.dac.anti_zshim_current_control.set(0.)
        # self.set_shims(v_zshim_current=self.p.v_zshim_current_gm,
        #                v_yshim_current=self.p.v_zshim_current_gm,
        #                 v_xshim_current=self.p.v_zshim_current_gm)
        
        delay(self.p.t_lightsheet_hold)

        delay(-10.e-3)
        for i in self.high_field_ramp_down_list:
            self.outer_coil.on(i_supply=i)
            delay(self.dt_high_field_ramp)
        delay(10.e-3)

        self.outer_coil.off()
        delay(5.e-3)

        self.lightsheet.off()

        delay(self.p.t_tof)
        # self.flash_repump(t=self.p.t_repump_flash_imaging)
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