from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class rf_scan(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        self.p.imaging_state = 2.
        # self.xvar('imaging_state',[2,1])
        self.p.t_rf_state_xfer_sweep = 10.e-3
        self.p.n_rf_state_xfer_sweep_steps = 100
        self.p.frequency_rf_sweep_state_prep_center = 459.38e6
        self.p.frequency_rf_sweep_state_prep_fullwidth = 122.448e3
        self.p.do_sweep = 1

        # self.xvar('frequency_rf_sweep_state_prep_center', 461.7e6 + np.linspace(-3.,3.,50)*1.e6)
        # self.xvar('spin_polarization_time', np.linspace(50.,700.,50)*1.e-3)
        # self.xvar('i_magtrap_ramp_start', np.linspace(0.,40.,20))
        # self.xvar('t_magtrap_ramp', np.linspace(10.,500.,20)*1.e-3)
        # self.xvar('i_magtrap_ramp_end',np.linspace(20.,70.,6))
        self.xvar('t_magtrap', np.linspace(10,150,10)*1.e-3)


        self.p.t_magtrap_ramp_start = 5.e-3
        self.p.t_magtrap_ramp_end = 75.e-3

        # self.xvar('t_magtrap_ramp',np.linspace(self.p.t_magtrap_ramp_start,self.p.t_magtrap_ramp_end,6))

        self.p.i_magtrap_ramp_start = 82.
        # self.xvar('i_magtrap_ramp_start', np.linspace(20.,100.,10))

        self.p.t_magtrap = 24.e-3
        # self.xvar('beans',[0,1]*1000)

        # self.p.t_magtrap = 24.e-3

        self.p.i_magtrap = 45.

        self.p.t_spin_polarization_time = 30.e-3

        self.p.t_mot_load = 0.5
        self.p.t_bias_off_wait = 2.e-3

        self.finish_build(shuffle=True)

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
        
        self.inner_coil.set_current(i_supply=self.p.i_magtrap_ramp_start)
        self.set_shims(v_zshim_current=self.p.v_zshim_current_gm,
                        v_yshim_current=self.p.v_yshim_current_gm,
                          v_xshim_current=self.p.v_xshim_current_gm)
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.flash_cooler()
        
        self.inner_coil.igbt_ttl.on()

        # self.release()
        self.switch_d2_3d(0)
        self.switch_d1_3d(0)

        # for i in self.p.magtrap_ramp_list:
        #     self.inner_coil.set_current(i_supply=i)
        #     delay(self.p.dt_magtrap_ramp)

        # self.inner_coil.igbt_ttl.on()
        # delay(self.p.t_magtrap)
        # self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
        # delay(5.e-3)
        # self.lightsheet.off()
        # delay(self.p.t_magtrap_ramp_end - self.p.t_magtrap_ramp)
        delay(self.p.t_magtrap)
        self.inner_coil.off()
    
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