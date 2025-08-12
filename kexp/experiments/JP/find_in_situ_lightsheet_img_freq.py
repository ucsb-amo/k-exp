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

        self.p.t_tof = 100.e-6

        self.p.v_yshim = 0.
        # self.xvar('v_pd_lightsheet_rampup_end_pref', np.linspace(0.1,1.,4))
        self.p.v_pd_lightsheet_rampup_end_pref = 1.

        self.p.t_lightsheet_hold = 1.e-3

        self.p.N_repeats = 1
        self.p.t_mot_load = 1.
        self.p.imaging_state = 2.

        self.p.t_lightsheet_drop = 15.e-6

        # self.xvar('frequency_in_situ_imaging',
        #           self.p.frequency_detuned_imaging
        #           + 160.6e6 
        #           + np.arange(-260.,100.,12.)*1.e6)
        self.xvar('frequency_in_situ_imaging',
                  np.arange(120.,180.,3.)*1.e6)

        # self.xvar('frequency_in_situ_imaging',
        #           self.p.frequency_detuned_imaging
        #           + np.arange(400.,700.,6.)*1.e6)
        # self.p.frequency_in_situ_imaging = self.p.frequency_detuned_imaging + 700.e6
        # self.p.frequency_in_situ_imaging = 600.e6

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(self.p.frequency_in_situ_imaging)

        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False)

        
        self.dac.yshim_current_control.linear_ramp(self.p.t_yshim_rampdown,
                                                   self.p.v_yshim_current_magtrap,
                                                   self.p.v_yshim,n=100)
        delay(20.e-3)

        self.lightsheet.ramp(t=100.e-3,
                             v_start=self.p.v_pd_lightsheet_rampup_end,
                             v_end=self.p.v_pd_lightsheet_rampup_end*self.p.v_pd_lightsheet_rampup_end_pref,
                             n_steps=1000)

        # self.ttl.pd_scope_trig.pulse(1.e-6)
        # delay(-1.e-6)

        self.drop_and_repump_to_f2()

        delay(self.p.t_lightsheet_hold)

        self.ttl.pd_scope_trig.pulse(1.e-6)
        delay(-1.e-6)

        self.abs_image_in_trap()

        self.lightsheet.off()


        # self.abs_image()

    @kernel
    def drop_and_repump_to_f2(self):

        self.dds.d2_3d_r.set_dds_gamma(delta=self.params.detune_d2_r_imaging,
                                       amplitude=self.params.amp_d2_r_imaging)

        # drop trap
        self.lightsheet.pid_int_zero_ttl.on()
        self.lightsheet.ttl.off()
        
        delay(self.p.t_lightsheet_drop)

        self.dds.d2_3d_r.on()
        delay(self.p.t_repump_flash_imaging)
        self.dds.d2_3d_r.off()
        
        delay(-self.p.t_repump_flash_imaging)

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
