from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class rf_scan(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler')

        # self.xvar('imaging_state',[1,2])
        # self.xvar('v_vco_rf_state_xfer_sweep_fullwidth',np.linspace(0.05,0.15,8))
        # self.xvar('v_vco_rf_state_xfer_sweep_center',np.linspace(6.8,8.,40))
        # self.xvar('v_vco_rf_state_xfer_sweep_center',np.linspace(7.2,7.37,8))

        # self.xvar('n_rf_state_xfer_sweep_steps',np.linspace(10,1500,15,dtype=int))

        # self.xvar('dummy',[0]*2)

        # self.p.v_vco_rf_state_xfer_sweep_center = 7.26
        
        # self.xvar('do_optical_pumping',[0,1])
        # self.xvar('rf_yes',[0,1])
        # self.xvar('t_bias_off_wait',np.linspace(1.,40.,12)*1.e-3)

        

        # self.p.v_vco_rf_state_xfer_sweep_center = 7.257 # 7.257
        # self.p.v_vco_rf_state_xfer_sweep_fullwidth = 0.06

        self.p.imaging_state = 2.
        self.p.rf_yes = 1.
        self.p.t_rf_state_xfer_sweep = 100.e-3
        self.p.n_rf_state_xfer_sweep_steps = 1000

        self.p.t_optical_pumping = 50.e-6

        # self.p.t_lightsheet_hold = .01e-3
        self.p.t_lightsheet_rampup = 5.e-3

        # self.xvar('frequency_detuned_imaging_F1',4.58e08 - 2.86e6 + np.linspace(-15.,15.,15)*1.e6)

        # self.xvar('t_lightsheet_hold',np.linspace(10.,100.,12)*1.e-3)
        # self.xvar('v_vco_rf_state_xfer_sweep_center',[6.8,7.257])

        # self.xvar('frequency_rf_state_xfer_sweep_center',np.linspace(450.,479.697,100)*1.e6)
        # self.xvar('frequency_rf_state_xfer_sweep_center',np.linspace(454.,470.,54)*1.e6)
        self.xvar('frequency_rf_state_xfer_sweep_center',np.linspace(430.,485.,100)*1.e6)
        self.p.frequency_rf_state_xfer_sweep_fullwidth = 0.4e6 #0.3e6

        self.p.v_zshim_current_op = 9.99
        self.p.t_mot_load = 0.25

        # self.p.v_zshim_current_op = 9.99
        self.p.t_bias_off_wait = 2.e-3

        # self.p.amp_optical_pumping_op = 0.
        # self.p.amp_optical_pumping_r_op = 0.

        self.finish_build()

    @kernel
    def scan_kernel(self):
        self.dds.init_cooling()

        self.core.break_realtime()

        if self.p.imaging_state == 1.:
            self.set_imaging_detuning(detuning=self.p.frequency_detuned_imaging_F1)
        else:
            self.set_imaging_detuning()

        # self.load_2D_mot(self.p.t_2D_mot_load_delay)
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

        # delay(-self.p.t_cooler_flash_imaging)
        self.flash_cooler()

        # if self.p.do_optical_pumping:
        self.dds.power_down_cooling()
        # self.optical_pumping(t=self.p.t_optical_pumping)
        # else:
        #     self.flash_repump(t=self.p.t_optical_pumping)
        #     self.dds.power_down_cooling()

        # self.flash_cooler()

        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
        # self.set_shims()
        self.set_zshim_magnet_current(self.p.v_zshim_current_op)
        delay(20*ms)
        # delay(self.p.t_lightsheet_hold)

        self.ttl.pd_scope_trig.on()
        self.rf.sweep()
        self.ttl.pd_scope_trig.off()
        
        # if self.p.rf_yes:
        #     self.dac.vco_rf.set(self.p.v_vco_rf_state_xfer_sweep_list[0])
        #     self.ttl.antenna_rf_sw.on()
        #     for f in self.p.v_vco_rf_state_xfer_sweep_list:
        #         self.dac.vco_rf.set(f)
        #         delay(self.p.dt_rf_state_xfer_sweep)
        #     self.ttl.antenna_rf_sw.off()
        # else:
        #     delay(self.p.t_rf_state_xfer_sweep)
        
        self.set_zshim_magnet_current()
        delay(self.p.t_bias_off_wait)
        self.lightsheet.off()
        
        delay(self.p.t_tof)
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)


