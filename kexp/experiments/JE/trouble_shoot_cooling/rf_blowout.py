from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning
from kexp import Base, img_types, cameras

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class mag_trap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select=cameras.xy_basler,
                      imaging_type=img_types.ABSORPTION)

        self.p.t_tof = 300.e-6
        # self.xvar('t_tof',np.linspace(10.,500.,6)*1.e-6)

        self.p.t_rf_state_xfer_sweep = 80.e-3
        self.p.n_rf_sweep_steps = 1000

        self.xvar('do_rf',[0,1])
        # self.xvar('do_blowout',[0,1])
        # self.xvar('do_drop',[0,1])
        # self.xvar('repump_pre_imaging',[0,1])
        self.p.do_rf = 1
        self.p.do_drop = 0
        self.p.do_blowout = 0
        self.p.repump_pre_imaging = 0

        # self.xvar('v_zshim',np.linspace(0.0,1.,10))
        self.p.v_zshim = 0.
        # self.xvar('v_yshim',np.linspace(0.,5.,10))
        self.p.v_yshim = 0.
        # self.xvar('v_xshim',np.linspace(0.,3.,10))
        # self.p.v_xshim = 0.
        
        # self.xvar('frequency_rf_sweep_state_prep_center', 140.e6 + np.linspace(0.,20.,60)*1.e6)

        self.p.frequency_rf_state_xfer_sweep_fullwidth = 70.e3
        df = self.p.frequency_rf_state_xfer_sweep_fullwidth

        # f = np.linspace(460.,463.,10)*1.e6
        # f = 460.719e6 - np.linspace(5.,5.,15)
        # f0 = 461.719e6 # 0 -> 0
        f0 = 462.759e6 # 0 -> 1 at v_zshim = 0. (1.46 G)
        # f0 = 464.8e6
        # f_range = 1.2e6
        # f_range = 0.2e6
        # f_min, f_max = f0 + np.array([-1,1])*f_range
        # f_min,f_max = [460.4e6, 463.e6]
        # f_min,f_max = [462.2e6, 46e6]
        # f = np.arange( f_min, f_max + df, df )
        # self.xvar('frequency_rf_state_xfer_sweep_center', f)

        # self.p.frequency_rf_state_xfer_sweep_fullwidth = np.diff(f)[0] * 1.5

        self.p.frequency_rf_state_xfer_sweep_center = f0

        self.p.t_lightsheet_hold = 1.e-3

        self.p.N_repeats = 1
        self.p.t_mot_load = 1.
        self.p.imaging_state = 2.

        self.p.t_lightsheet_drop1 = 5.e-6
        # self.xvar('t_lightsheet_drop1',np.linspace(0.,2.,5)*1.e-6)
        self.p.t_lightsheet_drop2 = 0.e-6

        self.p.t_blow = 20.e-6
        # self.xvar('t_blow',np.linspace(0.,250.,10)*1e-6)

        self.p.frequency_blowout_pulse = 150.e6

        # self.xvar('frequency_blowout_pulse', np.linspace(50.,220.,20)*1.e6)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(self.p.frequency_blowout_pulse,amp=0.54)

        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        # self.magtrap_and_load_lightsheet(do_magtrap_rampup=False)

        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False,do_magtrap_rampdown=False)
        self.inner_coil.snap_off()
        
        # self.lightsheet.ramp(2.e-3,0.,self.p.v_pd_lightsheet_rampup_end,n_steps=100)
        # self.release()
        # self.pump_to_F1()
        # delay(40.e-3)
        
        self.dac.yshim_current_control.linear_ramp(self.p.t_yshim_rampdown,
                                                   self.p.v_yshim_current_magtrap,
                                                   self.p.v_yshim,n=100)
        # self.dac.zshim_current_control.linear_ramp(10.e-3,
        #                                            self.p.v_zshim_current_magtrap,
        #                                            self.p.v_zshim,n=100)
        # self.dac.xshim_current_control.linear_ramp(10.e-3,
        #                                            self.p.v_xshim_current_magtrap,
        #                                            self.p.v_xshim,n=100)
        delay(20.e-3)

        if self.p.do_rf:
            self.rf.sweep(t=self.p.t_rf_state_xfer_sweep,
                        frequency_center=self.p.frequency_rf_state_xfer_sweep_center,
                        frequency_sweep_fullwidth=self.p.frequency_rf_state_xfer_sweep_fullwidth,
                        n_steps=200)
        else:
            delay(self.p.t_rf_state_xfer_sweep)
        
        delay(1.e-3)

        delay(self.p.t_lightsheet_hold)

        # self.ttl.pd_scope_trig.pulse(1.e-6)
        # delay(-1.e-6)
        self.blowout_pulse()

        self.set_imaging_detuning(self.p.frequency_detuned_imaging)

        delay(self.p.t_lightsheet_hold)

        self.lightsheet.off()

        delay(self.p.t_tof)

        if self.p.repump_pre_imaging:
            self.flash_repump()
        else:
            delay(self.p.t_repump_flash_imaging)
        # self.flash_cooler()
        self.abs_image()

    @kernel
    def blowout_pulse(self):
        if self.p.do_drop:
            self.lightsheet.pid_int_zero_ttl.on()
            self.lightsheet.ttl.off()
        delay(self.p.t_lightsheet_drop1)

        if self.p.do_blowout:
            self.dds.imaging.on()
            delay(self.p.t_blow)
            self.dds.imaging.off()
        else:
            delay(self.p.t_blow)

        # delay(self.p.t_lightsheet_drop2 - self.p.t_blow)

        self.lightsheet.on()
        self.lightsheet.pid_int_zero_ttl.off()

    @kernel
    def run(self):
        self.init_kernel(init_shuttler=False)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
