
import numpy as np
from artiq.experiment import *
from artiq.language.core import delay, kernel
from kexp import Base, img_types, cameras

class hf_bec(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION)
        
        # self.xvar('t_tof',np.linspace(20.,3000.,7)*1.e-6)
        self.p.t_tof = 1700.e-6

        # self.xvar('do_405_pulse',[0,1])
        self.p.do_405_pulse = 1
        # self.xvar('do_980_pulse',[0,1])
        self.p.do_980_pulse = 0
        # self.p.amp_dds_405 = 0.06
#   

         # self.xvar('compress',[0,1])
        self.p.compress = 0

        # self.xvar('t_tweezer_paint_rampdown',np.linspace(0.0,10.,5)*1.e-3)

        self.xvar('t_tweezer_hold', np.linspace(0.0, 100.0, 10) * 1.e-3)
        self.p.t_tweezer_hold = 512.e-3

        # self.p.v_pd_hf_tweezer_1064_rampdown3_end=3.5

        self.p.hf_imaging_detuning = -568.e6

        self.p.amp_imaging = 0.125
        # self.xvar('v_pd_ry_980',np.linspace(0.,1.,5))
        self.p.v_pd_ry_405 = 2.5 # maximum value 2.6 V
        self.p.v_pd_ry_980 = 2.8

        self.p.amp_dds_405 = .1

        self.p.i_hf_raman = 182.

        # self.xvar('beans',np.linspace(0,30,10))
        self.p.N_repeats = 10
        self.finish_prepare(shuffle=True)

        if self.p.do_405_pulse == 1:
            print(f'doing 405 pulse')
        else:
            print(f'not doing 405 pulse')
        if self.p.do_980_pulse == 1:
            print(f'doing 980 pulse')
        else:
            print(f'not doing 980 pulse')

    @kernel
    def scan_kernel(self):
        
        self.ry_405.set_power(self.p.v_pd_ry_405)
        self.ry_980.set_power(self.p.v_pd_ry_980)
        self.ttl.ry_intensity_pid_clear.pulse(10.e-6)

        if self.p.compress:
            self.p.t_tof = 450.e-6

        # self.ry_980.set_power(9.9)

        self.set_imaging_detuning(frequency_detuned=self.p.hf_imaging_detuning)

        if self.p.compress:
            self.prepare_hf_tweezers(squeeze=True)
        else:
            self.prepare_hf_tweezers(squeeze=False, do_tweezer_evap_3=True, do_tweezer_evap_2=True)

        # self.tweezer.ramp(t=self.p.t_tweezer_squeezer_ramp_1,
        #                         v_start=self.p.v_pd_hf_tweezer_1064_rampdown3_end,
        #                         v_end=self.p.v_pd_tweezer_squeeze_rampup_handoff_lp,
        #                         low_power=True, paint=False, keep_trap_frequency_constant=False,
        #                         cubic_ramp=self.cubic_ramp)


        if self.p.do_405_pulse == 1:
            self.ry_405.reboot()
            self.ry_405.dds_sw.set_dds(amplitude=self.p.amp_dds_405)
            self.ry_405.on()
        if self.p.do_980_pulse == 1:
            self.ry_980.on()
        
    

        delay(self.p.t_tweezer_hold)

        self.ry_405.off()
        self.ry_980.off()
        self.ry_405.ttl_shutter.off()

        delay(40e-3)

        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

        self.outer_coil.off()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
