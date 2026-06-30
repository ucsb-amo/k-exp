
import numpy as np
from artiq.experiment import *
from artiq.language.core import delay, kernel
from kexp import Base, img_types, cameras


class hf_bec(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION)
        
        # self.xvar('t_tof',np.linspace(20.,100.,7)*1.e-6)
        self.p.t_tof = 500.e-6

        # self.xvar('wee',[1,0])
        self.p.wee = 1

        # self.xvar('do_405_pulse',[1,0])
        self.p.do_405_pulse = 1
        self.p.do_980_pulse = 1

        self.p.amp_dds_405 = 0.08

        # self.xvar('frequency_eo_980', np.arange(150.,350.,1)*1.e6)
        # self.xvar('frequency_eo_980', np.linspace(290.,310.,10)*1.e6)
        self.p.frequency_eo_980 = self.siglent.siglent_980._frequency_default
        # self.p.frequency_eo_980 = 305.1e6

        # self.xvar('t_tweezer_paint_rampdown',np.linspace(0.0,10.,5)*1.e-3)

        self.xvar('t_tweezer_hold', np.linspace(0.0, 500.0, 7) * 1.e-3)
        self.t_tweezer_hold = 200.e-3

  
        # self.p.v_pd_ry_405 = 9.1 # for 1.95 mW
        # self.p.v_pd_ry_405 = 9.1 / 2 # for 1.95 mW
        self.p.v_pd_ry_405 = 9.1 / 10 # for 1.95 mW

        # self.p.v_pd_ry_405 = 0.8
        # self.p.v_vva_ry_405 = 0.61
        # self.p.v_vva_ry_405 = 0.76

        self.p.N_repeats = 1

        self.data.apd = self.data.add_data_container(3)

        self.finish_prepare(shuffle=True)

        if self.p.do_405_pulse == 1:
            print(f'doing 405 pulse')
        else:
            print(f'not doing 405 pulse')

    @kernel
    def scan_kernel(self):

        self.integrator.init()
        
        self.ry_405.set_power(self.p.v_pd_ry_405)

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        self.prepare_hf_tweezers(squeeze=False)

        delay(100e-3)

        if self.p.do_405_pulse == 1:
            self.ry_405.reboot()
            self.ry_405.dds_sw.set_dds(amplitude=self.p.amp_dds_405)
            self.ry_405.on()

        delay(self.p.t_tweezer_hold)

        self.ry_405.off()
        self.ry_980.off()
        self.ry_405.ttl_shutter.off()

        delay(40e-3)

        self.tweezer.off()

        delay(self.p.t_tof)
        # self.abs_image()

        self.integrated_imaging_pulse(self.data.apd,
                                      self.p.t_imaging_pulse,
                                      idx=0)
        delay(1.e-3)
        self.integrated_imaging_pulse(self.data.apd,
                                      self.p.t_imaging_pulse,
                                      idx=1)
        delay(1.e-3)
        self.integrated_imaging_pulse(self.data.apd,
                                      self.p.t_imaging_pulse,
                                      idx=2,
                                      dark=True)
        delay(1.e-3)
        
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
