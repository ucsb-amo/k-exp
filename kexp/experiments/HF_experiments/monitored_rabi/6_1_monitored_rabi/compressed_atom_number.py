from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu
from kexp.util.artiq.async_print import aprint

class hf_monitored_rabi(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)


        # self.xvar('v_pd_hf_tweezer_squeeze_power',np.linspace(.2,3.94, 15))
        self.p.v_pd_hf_tweezer_squeeze_power = 2.
        
        # self.xvar('amp_imaging',np.linspace(.2,1.5, 10))
        self.p.amp_imaging = .1

        # self.p.amp_tweezer_list = [.18]

        # self.xvar('frequency_detuned_hf_f1m1',np.linspace(-580.e6,-530.e6,30))
        # self.p.frequency_detuned_hf_f1m1 = -545.e6

        # self.xvar('i_hf_tweezer_load_current',np.linspace(191.,195.,15))
        # self.p.i_hf_tweezer_load_current = 193.

        # self.xvar('v_hf_tweezer_paint_amp_max',np.linspace(-1.,5.0,15))
        # self.p.v_hf_tweezer_paint_amp_max = .7

        # self.xvar('v_pd_hf_tweezer_1064_rampdown3_end',np.linspace(1.5,6.,15))
        # self.p.v_pd_hf_tweezer_1064_rampdown3_end = 3.5

        # self.xvar('i_hf_raman',np.linspace(174.5,182.,10))
        # self.p.i_hf_raman = 176.5

        # self.xvar('t_tweezer_paint_rampdown1',np.linspace(10.e-3,100.e-3,10))
        # self.p.t_tweezer_paint_rampdown1 = 18.e-3

        # self.xvar('v_tweezer_paint_rampdown_end1',[-4.99,-4.5])
        # self.xvar('v_tweezer_paint_rampdown_end1',np.linspace(-4.985,-4.5,11))
        # self.p.v_tweezer_paint_rampdown_end1 = -4.99

        # self.xvar('t_tweezer_squeezer_ramp_1',np.linspace(3.e-3,50.e-3,10))
        # self.p.t_tweezer_squeezer_ramp_1 = 13.e-3

        # self.xvar('t_tweezer_squeezer_ramp_2',np.linspace(3.e-3,50.e-3,10))
        # self.p.t_tweezer_squeezer_ramp_2 = 24.e-3

        self.xvar('t_tof',np.linspace(1000.,4000.,10)*1.e-6)

        # self.xvar('t_tweezer_hold',np.linspace(3.e-3,50.e-3,10))
        self.p.t_tweezer_hold = 10.e-3
        self.p.t_tof = 3000.e-6
        self.p.t_mot_load = 1.0
        
        self.p.N_repeats = 5

        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=False)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        self.set_high_field_imaging(i_outer=self.p.i_hf_raman,pid_bool=True)
        # self.set_imaging_detuning(frequency_detuned = self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers(ramp_down_painting=True,squeeze=False,cubic_ramp_squeeze=False)

        # delay(10.e-3)

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

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
        # aprint(self.scope._data)
        self.end(expt_filepath)