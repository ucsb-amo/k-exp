
import numpy as np
from artiq.experiment import *
from artiq.language.core import delay, kernel
from kexp import Base, img_types, cameras


class hf_bec(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION)
        
        
        # self.xvar('t_tweezer_paint_rampdown',np.linspace(0.0,10.,5)*1.e-3)
        
        # self.xvar('v_pd_hf_lightsheet_rampdown_end', np.linspace(0.6,1.2,5))
        # self.xvar('t_tweezer_hold', np.linspace(0.,500.,4) * 1.e-3)
        # self.xvar('t_hf_tweezer_1064_ramp',np.linspace(160,220,3)*1.e-3)
        # self.xvar('v_pd_lightsheet_rampup_end',np.linspace(7.12,,5))
        # self.xvar('i_hf_tweezer_load_current',[193.6, 193.7, 193.8])
        # self.xvar('v_hf_tweezer_paint_amp_max',np.linspace(-3.,-1,7))
        # self.xvar('v_pd_hf_tweezer_1064_rampdown3_end', np.linspace(4.3,5.2,11))
        # self.p.v_pd_lightsheet_rampup_end = 6.7
        # self.p.i_hf_tweezer_load_current = 193.7
        # self.p.t_hf_tweezer_1064_ramp = 0.19
        # self.p.v_pd_hf_lightsheet_rampdown_end = 0.8
        # self.p.v_pd_hf_tweezer_1064_rampdown3_end = 4.75
        # self.p.v_hf_tweezer_paint_amp_max = -2.33

        # self.xvar('skip_evap_ramp',[0,1])

        self.p.t_tweezer_hold = 10.e-3

        # self.p.v_pd_hf_tweezer_squeeze_power
        # self.xvar('v_pd_hf_tweezer_squeeze_power', np.linspace(0.3,6.7,21))

        self.xvar('t_tof',np.linspace(1000.,2800.,8)*1.e-6)
        self.p.t_tof = 200.e-6
        # self.p.t_tof = 20.e-6

        # self.xvar('v_pd_lightsheet_rampup_end',np.linspace(5.,7.2,3))

        # self.xvar('v',np.linspace(0.,1.,5))
        # self.p.v = 3.

        self.p.N_repeats = 3

        self.p.t_mot_load = 1.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.ry_405.set_power(self.p.v)

        # self.ry_980.on()

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        # self.set_high_field_imaging(i_outer=self.p.i_hf_tweezer_evap2_current)
        self.imaging.set_power(self.camera_params.amp_imaging)
        self.prepare_hf_tweezers(squeeze=False)
        # self.prep_raman()
        
        # self.raman.on()
        # self.ry_405.reboot()
        # self.ry_405.on()
        
        delay(self.p.t_tweezer_hold)
        
        # self.ry_405.ttl_shutter.off()
        # self.raman.off()
        # self.ry_405.ttl_shutter.off()

        # delay(10.e-3)
        
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

