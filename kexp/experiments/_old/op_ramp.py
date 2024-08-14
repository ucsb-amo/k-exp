from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class rf_scan(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler')

        self.p.imaging_state = 1.
        self.p.t_tof = 20.e-6
        self.p.rf_yes = 1.
        self.p.t_rf_state_xfer_sweep = 100.e-3
        self.p.n_rf_state_xfer_sweep_steps = 500

        self.p.t_lightsheet_rampup = 5.e-3

        # self.xvar('image_delay',np.linspace(0.,20.,10)*1.e-3)

        # self.xvar('frequency_rf_state_xfer_sweep_center',np.linspace(440.5,482.,100)*1.e6)
        # self.p.frequency_rf_state_xfer_sweep_fullwidth = 0.415e6

        # self.xvar('frequency_rf_state_xfer_sweep_center',np.linspace(445.,470.,250)*1.e6)
        # self.p.frequency_rf_state_xfer_sweep_fullwidth = 0.1e6

        # self.xvar('t_lightsheet_hold',np.linspace(20.,200.,12)*1.e-3)
        # self.xvar('t_optical_pumping',np.linspace(0.,50.,3)*1.e-6)
        # self.p.frequency_rf_state_xfer_sweep_fullwidth = 0.61e6

        # self.xvar('frequency_rf_state_xfer_sweep_center',(461.7+np.linspace(-1.0,1.0,200))*1.e6)
        # self.p.frequency_rf_state_xfer_sweep_fullwidth = 0.02e6

        self.xvar('frequency_rf_state_xfer_sweep_center',(np.linspace(440.,482.,60))*1.e6)
        self.p.frequency_rf_state_xfer_sweep_fullwidth = .8e6

        self.xvar('frequency_rf_state_xfer_sweep_center',(np.linspace(440.,482.,60))*1.e6)
        self.p.frequency_rf_state_xfer_sweep_fullwidth = .8e6

        self.p.v_zshim_current_op = 9.99

        self.p.t_optical_pumping = 300.e-6

        self.p.op_sweep_steps = 5
        # self.p.op_sweep_freqs = np.linspace(-.5,1.3,self.p.op_sweep_steps)
        self.p.op_sweep_freqs = np.linspace(1.3,-.5,self.p.op_sweep_steps)
        self.p.op_sweep_dt = self.p.t_optical_pumping / self.p.op_sweep_steps

        self.p.t_mot_load = 0.5
        self.p.t_bias_off_wait = 2.e-3
        self.p.t_repump_flash_imaging = 8.e-6

        self.finish_prepare()

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
        # self.flash_cooler()
        # self.flash_repump()
        # delay(self.p.t_optical_pumping - self.p.t_repump_flash_imaging)

        self.dds.power_down_cooling()
    
        # self.optical_pumping(t=self.p.t_optical_pumping)

        delay(-self.p.t_optical_pumping_bias_rampup)
        self.set_zshim_magnet_current(self.p.v_zshim_current_op)
        delay(self.p.t_optical_pumping_bias_rampup)

        self.ttl.pd_scope_trig.on()
        self.dds.optical_pumping.set_dds_gamma(delta=self.p.op_sweep_freqs[0])
        self.dds.op_r.set_dds_gamma(delta=self.p.op_sweep_freqs[0])
        self.dds.optical_pumping.on()
        self.dds.op_r.on()
        for f in self.p.op_sweep_freqs:
            self.dds.optical_pumping.set_dds_gamma(delta=f)
            self.dds.op_r.set_dds_gamma(delta=f)
            delay(self.p.op_sweep_dt)
        self.dds.optical_pumping.off()
        self.dds.op_r.off()
        self.ttl.pd_scope_trig.off()

        # self.flash_cooler()
        
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
        # self.set_shims()
        # delay(self.p.t_lightsheet_hold)

        self.ttl.pd_scope_trig.on()
        self.rf.sweep()
        self.ttl.pd_scope_trig.off()

        # delay(100.e-3)
        self.set_zshim_magnet_current()
        # delay(self.p.t_bias_off_wait)
        delay(7.e-3)
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


