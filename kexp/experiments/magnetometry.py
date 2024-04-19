from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class rf_scan(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler')

        self.p.imaging_state = 2.
        # self.xvar('imaging_state',[2,1])
        self.p.t_rf_state_xfer_sweep = 150.e-3
        self.p.n_rf_state_xfer_sweep_steps = 1500
        # self.p.frequency_rf_sweep_state_prep_center = 459.43e6
        # self.p.frequency_rf_sweep_state_prep_fullwidth = 506.329e3
        self.p.frequency_rf_sweep_state_prep_fullwidth = 1037.974e3
        # self.xvar('frequency_rf_sweep_state_prep_fullwidth', np.linspace(700.,1200.,30)*1.e3)

        self.p.t_lightsheet_rampup = 10.e-3

        # self.p.v_pd_lightsheet_rampup_end = 2.7

        # self.xvar('i_outer_coil',np.linspace(10.,65.,7))
        # self.xvar('i_outer_coil',np.linspace(53, 64, 5))

        # self.xvar('t_rf_state_xfer_sweep',np.linspace(.5,10.,15)*1.e-3)

        # self.xvar('frequency_rf_sweep_state_prep_center', 459.5e6 + np.linspace(-.2,.2,20)*1.e6)
        # self.xvar('frequency_rf_sweep_state_prep_center', 461.e6 + np.linspace(-20.,20.,80)*1.e6)
        # self.xvar('frequency_rf_sweep_state_prep_center', 461.e6 + np.linspace(-5.,5.,80)*1.e6)
        self.xvar('frequency_rf_sweep_state_prep_center', np.linspace(460.,480.,30)*1.e6)
        # self.p.frequency_rf_state_xfer_sweep_center = 476.e6
        self.p.do_sweep = 1
        # self.xvar('do_sweep',[0,1])
        # self.xvar('frequency_rf_sweep_state_prep_fullwidth',np.linspace(20.,500.,15)*1.e3)
        # self.p.frequency_rf_sweep_state_prep_fullwidth = 150.e3

        # self.xvar('v_zshim_current_op',np.linspace(0.86,0.94,6))

        # self.xvar('frequency_rf_state_xfer_sweep_center',(461.7+np.linspace(-0.15,0.15,75))*1.e6)
        # self.p.frequency_rf_state_xfer_sweep_fullwidth = 7.e3

        # self.xvar('frequency_rf_state_xfer_sweep_center',(475.14+np.linspace(-.1,.1,20))*1.e6)
        # self.p.frequency_rf_state_xfer_sweep_fullwidth = 7.e3

        # self.p.i_outer_coil = 8.
        # self.xvar('i_outer_coil',np.linspace(8.,25.,5))
        # self.p.i_outer_coil = 13.924
        # self.xvar('v_yshim_current_measure',0.993 + np.linspace(-0.2,0.7,6))
        # self.xvar('v_xshim_current_measure',np.linspace(0.0,0.15,5))

        # self.xvar('frequency_rf_state_xfer_sweep_center',np.linspace(440.,500.,100)*1.e6)
        # self.p.frequency_rf_state_xfer_sweep_fullwidth = 600.0e3

        ### shows both 1,0->2,0 and 1,0->2,1 at low fields
        # self.xvar('frequency_rf_state_xfer_sweep_center',(461.7+np.linspace(-0.05,0.25,42))*1.e6)
        # self.p.frequency_rf_state_xfer_sweep_fullwidth = 10.e3
        ###

        # self.p.v_zshim_current_op = 0.

        ### ~0.2G background field, see central 3 transitions
        # self.xvar('frequency_rf_state_xfer_sweep_center',(461.7+np.linspace(-0.15,0.15,75))*1.e6)
        # self.p.frequency_rf_state_xfer_sweep_fullwidth = 7.e3
        ###

        ### v = 3.0 z shim, v_x=0.17, v_y = 0.17 (optical pumping field) see all states
        # self.xvar('frequency_rf_state_xfer_sweep_center',np.linspace(456.05,467.45,70)*1.e6)
        # self.p.frequency_rf_state_xfer_sweep_fullwidth = 150.e3
        ###

        ### v = 3.0 z shim, v_x=0.17, v_y = 0.17 (optical pumping field) see all states, wider range
        # self.xvar('frequency_rf_state_xfer_sweep_center',np.linspace(451.05,473.45,85)*1.e6)
        # self.p.frequency_rf_state_xfer_sweep_fullwidth = 150.e3
        ###

        # self.xvar('frequency_rf_state_xfer_sweep_center',np.linspace(484,488,100)*1.e6)
        # self.p.frequency_rf_state_xfer_sweep_fullwidth = 38.e3

        # self.xvar('t_lightsheet_hold', np.linspace(100.,1000.,10)*1.e-3)
        self.p.i_outer_coil = 60.

        self.p.t_optical_pumping = 20.e-6

        self.p.t_lightsheet_hold = 1.e-3

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

        self.flash_cooler()
        # self.flash_repump(t=self.p.t_repump_flash_imaging)

        self.dds.power_down_cooling()

        self.set_shims(v_zshim_current=0.,
                       v_yshim_current=self.p.v_zshim_current_gm,
                        v_xshim_current=self.p.v_zshim_current_gm)

        # self.optical_pumping(self.p.t_optical_pumping,v_anti_zshim_current=9.99,v_zshim_current=0.)

        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)

        self.outer_coil.on(i_supply=self.p.i_outer_coil,wait_for_analog=True)

        delay(50*ms)
        if self.p.do_sweep:
            self.rf.sweep(frequency_sweep_list=self.p.frequency_rf_sweep_state_prep_list)

        # delay(10*ms)

        self.set_shims(v_zshim_current=self.p.v_zshim_current_gm,
                       v_yshim_current=self.p.v_zshim_current_gm,
                        v_xshim_current=self.p.v_zshim_current_gm)
        
        # delay(self.p.t_lightsheet_hold)
        self.outer_coil.igbt_ttl.off()
                       
        delay(10.e-3)
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