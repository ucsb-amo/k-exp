from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class high_field_magnetometry(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        self.p.imaging_state = 2.
        # self.xvar('imaging_state',[2,1])
        self.p.t_rf_state_xfer_sweep = 100.e-3
        self.p.n_rf_state_xfer_sweep_steps = 2000
        # self.p.frequency_rf_sweep_state_prep_center = 459.3543e6
        self.p.frequency_rf_sweep_state_prep_fullwidth = 50.e3

        self.p.t_lightsheet_rampup = 10.e-3

        # self.xvar('t_rf_state_xfer_sweep',np.linspace(20.,100.,10)*1.e-3)

        # the high field value to be scanned
        # self.xvar('i_evap1_current',np.linspace(80.,100.,3))
        self.p.i_evap1_current = 90.

        # self.p.high_field_current = 90.

        self.xvar('frequency_rf_sweep_state_prep_center',185.2e6 + np.linspace(-1.,1.,40)*1.e6)
        self.p.do_sweep = 1

        self.p.i_evap2_current = 0.

        self.p.t_optical_pumping = 100.e-6

        self.p.t_lightsheet_hold = 10.e-3

        self.p.t_mot_load = 0.5
        self.p.t_bias_off_wait = 2.e-3
        self.p.t_repump_flash_imaging = 10.e-6
        self.p.t_tof = 20.e-6

        # self.p.N_repeats = [1,2]

        self.finish_prepare()

    @kernel
    def scan_kernel(self):

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)

        self.inner_coil.set_current(i_supply=self.p.i_magtrap_init)
        
        self.set_shims(v_zshim_current=self.p.v_zshim_current_gm,
                        v_yshim_current=self.p.v_yshim_current_gm,
                          v_xshim_current=self.p.v_xshim_current_gm)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        # self.release()
        self.switch_d2_3d(0)
        self.switch_d1_3d(0)

        self.flash_cooler()

        self.dds.power_down_cooling()

        self.set_shims(v_zshim_current=0.,
                       v_yshim_current=self.p.v_zshim_current_gm,
                        v_xshim_current=self.p.v_zshim_current_gm)

        # magtrap start
        self.inner_coil.on()

        # ramp up lightsheet over magtrap
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)

        for i in self.p.magtrap_ramp_list:
            self.inner_coil.set_current(i_supply=i)
            delay(self.p.dt_magtrap_ramp)

        self.outer_coil.set_current(i_supply=self.p.i_feshbach_field_rampup_start)
        self.outer_coil.set_voltage(v_supply=9.)

        delay(self.p.t_magtrap)

        self.inner_coil.off()
        self.outer_coil.on()

        for i in self.p.feshbach_field_rampup_list:
            self.outer_coil.set_current(i_supply=i)
            delay(self.p.dt_feshbach_field_rampup)
        delay(20.e-3)

        if self.p.do_sweep:
            self.rf.sweep(frequency_sweep_list=self.p.frequency_rf_sweep_state_prep_list)
        
        delay(self.p.t_lightsheet_hold)

        delay(-10.e-3)
        for i in self.p.feshbach_field_ramp_list:
            self.outer_coil.set_current(i_supply=i)
            delay(self.p.dt_feshbach_field_ramp)
        delay(20.e-3)

        self.outer_coil.off()
        delay(self.p.t_feshbach_field_decay)

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