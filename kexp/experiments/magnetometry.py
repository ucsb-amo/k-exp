from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class rf_scan(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler')

        self.p.imaging_state = 2.
        self.p.rf_yes = 1.
        self.p.t_rf_state_xfer_sweep = 300.e-3
        self.p.n_rf_state_xfer_sweep_steps = 3000

        self.p.t_lightsheet_rampup = 10.e-3

        # self.xvar('v_zshim_current_op',np.linspace(0.86,0.94,6))

        # self.xvar('frequency_rf_state_xfer_sweep_center',(461.7+np.linspace(-0.15,0.15,75))*1.e6)
        # self.p.frequency_rf_state_xfer_sweep_fullwidth = 7.e3

        # self.xvar('frequency_rf_state_xfer_sweep_center',(475.14+np.linspace(-.1,.1,20))*1.e6)
        # self.p.frequency_rf_state_xfer_sweep_fullwidth = 7.e3

        # self.p.v_zshim_current_measure = 3.0
        # self.p.v_yshim_current_measure = 2.0
        # self.p.v_xshim_current_measure = 0.17

        # self.p.i_outer_coil = 8.93
        self.xvar('i_outer_coil',np.linspace(1.,15.,3))

        # self.xvar('v_yshim_current_measure',0.993 + np.linspace(-0.2,0.7,6))
        # self.xvar('v_xshim_current_measure',np.linspace(0.0,0.15,5))

        # self.xvar('frequency_rf_state_xfer_sweep_center',(462.129591 + np.linspace(-0.5,0.1,50))*1.e6)
        # scan_range = (447.147761+np.linspace(-0.3,0.3,63))*1.e6
        scan_range = np.linspace(440.,461.6,80)*1.e6
        self.xvar('frequency_rf_state_xfer_sweep_center',scan_range)
        self.p.frequency_rf_state_xfer_sweep_fullwidth = np.diff(scan_range)[0]*2

        # self.xvar('frequency_rf_state_xfer_sweep_center',np.linspace(440.,500.,200)*1.e6)
        # self.p.frequency_rf_state_xfer_sweep_fullwidth = 300.0e3

        ### shows both 1,0->2,0 and 1,0->2,1 at low fields
        # self.xvar('frequency_rf_state_xfer_sweep_center',(461.7+np.linspace(-0.05,0.25,42))*1.e6)
        # self.p.frequency_rf_state_xfer_sweep_fullwidth = 10.e3
        ###

        ### ~0.2G background field, see central 3 transitions
        # self.xvar('frequency_rf_state_xfer_sweep_center',(461.7+np.linspace(-0.15,0.15,75))*1.e6)
        # self.p.frequency_rf_state_xfer_sweep_fullwidth = 7.e3
        ###

        ### v = 3.0 z shim, v_x=0.17, v_y = 0.17 (optical pumping field) see all states
        # self.xvar('frequency_rf_state_xfer_sweep_center',np.linspace(456.05,467.45,70)*1.e6)
        # self.p.frequency_rf_state_xfer_sweep_fullwidth = 150.e3
        ###

        # self.xvar('frequency_rf_state_xfer_sweep_center',np.linspace(484,488,100)*1.e6)
        # self.p.frequency_rf_state_xfer_sweep_fullwidth = 38.e3

        self.p.t_optical_pumping = 100.e-6

        self.p.t_mot_load = 0.5
        self.p.t_bias_off_wait = 2.e-3
        self.p.t_repump_flash_imaging = 8.e-6

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
        # self.flash_repump()

        self.dds.power_down_cooling()

        # delay(.5e-3*s)

        # delay(-self.p.t_optical_pumping_bias_rampup)
        # self.set_shims(v_zshim_current=self.p.v_zshim_current_measure,
        #                 v_yshim_current=self.p.v_yshim_current_measure,
        #                   v_xshim_current=self.p.v_xshim_current_measure)
        # delay(self.p.t_optical_pumping_bias_rampup)
        
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
        self.outer_coil.on(i_supply=self.p.i_outer_coil)
        # self.set_shims()
        delay(self.p.t_lightsheet_hold)

        self.ttl.pd_scope_trig.on()
        self.rf.sweep()
        self.ttl.pd_scope_trig.off()

        # delay(20.e-3)
        # self.set_zshim_magnet_current()
        self.outer_coil.off()
        # delay(self.p.t_bias_off_wait)
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