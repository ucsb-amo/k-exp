from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class rf_scan(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler')

        self.p.imaging_state = 1.
        self.p.rf_yes = 1.
        self.p.t_rf_state_xfer_sweep = 20.e-3
        self.p.n_rf_state_xfer_sweep_steps = 1000

        self.p.t_lightsheet_rampup = 10.e-3

        # self.xvar('frequency_rf_state_xfer_sweep_center',np.linspace(450.,479.697,100)*1.e6)
        # self.p.frequency_rf_state_xfer_sweep_fullwidth = 0.3e6

        self.xvar('frequency_rf_state_xfer_sweep_center',np.linspace(440.,482.,70)*1.e6)
        # self.xvar('t_lightsheet_hold',np.linspace(20.,200.,12)*1.e-3)
        # self.xvar('t_optical_pumping',np.linspace(0.,120.,10)*1.e-6)

        self.p.frequency_rf_state_xfer_sweep_fullwidth = 0.61e6

        self.p.v_zshim_current_op = 9.99

        # self.p.t_optical_pumping = 50.e-6
        self.p.t_optical_pumping = 30.e-6

        # self.p.op_sweep_steps = 50
        # self.p.op_sweep_freqs = np.flip(np.linspace(-2.,2.,self.p.op_sweep_steps))
        # self.p.op_sweep_dt = self.p.t_optical_pumping / self.p.op_sweep_steps

        # self.p.v_zshim_current_op = 5.
        self.p.t_mot_load = 0.75

        # self.p.v_zshim_current_op = 9.99
        self.p.t_bias_off_wait = 2.e-3

        # self.p.amp_optical_pumping_op = 0.
        # self.p.amp_optical_pumping_r_op = 0.

        self.p.detune_optical_pumping_op = 2.
        self.p.detune_optical_pumping_r_op = 2.

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
        self.flash_repump()
        delay(22.e-6)

        delay(-self.p.t_optical_pumping_bias_rampup)
        self.set_zshim_magnet_current(self.p.v_zshim_current_op)
        delay(self.p.t_optical_pumping_bias_rampup)

        self.dds.power_down_cooling()

        # delay(.5e-3*s)
    
        # self.optical_pumping(t=self.p.t_optical_pumping)

        # delay(-self.p.t_optical_pumping_bias_rampup)
        # self.set_zshim_magnet_current(self.p.v_zshim_current_op)
        # delay(self.p.t_optical_pumping_bias_rampup)

        # self.ttl.pd_scope_trig.on()
        # for f in self.p.op_sweep_freqs:
        #     self.dds.optical_pumping.set_dds_gamma(delta=f)
        #     self.dds.op_r.set_dds_gamma(delta=f)
        #     self.dds.optical_pumping.on()
        #     self.dds.op_r.on()
        #     delay(self.p.op_sweep_dt)
        # self.dds.optical_pumping.off()
        # self.dds.op_r.off()
        # self.ttl.pd_scope_trig.off()

        # self.flash_cooler()
        
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
        # self.set_shims()
        delay(.1*ms)
        # delay(self.p.t_lightsheet_hold)

        self.ttl.pd_scope_trig.on()
        self.rf.sweep()
        self.ttl.pd_scope_trig.off()

        # delay(20.e-3)
        self.set_zshim_magnet_current()
        # delay(self.p.t_bias_off_wait)
        delay(20.e-3)
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


