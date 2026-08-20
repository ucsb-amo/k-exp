
import numpy as np
from artiq.experiment import *
from artiq.language.core import delay, kernel
from kexp import Base, img_types, cameras


class hf_bec(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION)
        
        # self.xvar('t_tof',np.linspace(20.,2000.,11)*1.e-6)
        self.p.t_tof = 300.e-6

        

        # self.xvar('do_405_pulse',[0,1])
        self.p.do_405_pulse = 1
        # self.xvar('do_980_pulse',[0,1])
        self.p.do_980_pulse = 1

        self.p.amp_dds_405 = 0.06
# 
        # self.xvar('v_pd_hf_tweezer_squeeze_power',[0.09,0.18,0.36])
        # self.xvar('frequency_eo_980', 366.4e6 + 1.e6 * np.linspace(-5,5,9))
        self.xvar('frequency_eo_980', np.arange(355.,367.,1)*1.e6)
        # self.p.frequency_eo_980 = self.siglent.siglent_980._frequency_default
        # self.p.frequency_eo_980 = 352.1e6
        self.p.frequency_eo_980 = 361.84e6
        # self.p.v_pd_hf_tweezer_1064_rampdown3_end = 8.
        # self.xvar('t_tweezer_paint_rampdown',np.linspace(0.0,10.,5)*1.e-3)

        # self.xvar('t_tweezer_hold', np.linspace(0.0, 1050.0, 5) * 1.e-3)
        self.p.t_tweezer_hold = 571.e-3
        # self.p.t_tweezer_hold = 1.e-3

        self.p.amp_imaging = 0.1
        self.p.v_pd_ry_405 = 0.4
        # self.p.v_pd_ry_405 = 0.8
        # self.p.v_vva_ry_405 = 0.61
        # self.p.v_vva_ry_405 = 0.76
        # self.xvar('i_hf_raman',[182.,183.])
        self.p.i_hf_raman = 182.

        # self.xvar('compress',[0,1])
        self.p.compress = 0

        self.p.N_repeats = 7

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
        if self.p.compress:
                self.p.t_tof = 40.e-6
        if self.p.do_980_pulse == 1:
            self.ry_980.sweep_to(self.p.frequency_eo_980)

        # self.ry_980.set_power(9.9)

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers(squeeze=False, do_tweezer_evap_3=False, do_tweezer_evap_2=False)


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
