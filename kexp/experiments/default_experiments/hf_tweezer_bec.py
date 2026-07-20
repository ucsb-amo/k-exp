
import numpy as np
from artiq.experiment import *
from artiq.language.core import delay, kernel
from kexp import Base, img_types, cameras


class hf_bec(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      setup_camera=True,
                      save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION)
        
        self.p.t_tweezer_hold = 10.e-3

        # self.xvar('t_tof',np.linspace(1000.,4000.,4)*1.e-6)
        self.p.t_tof = 1000.e-6

        self.p.phase_slm_mask = 1.6 * np.pi
        
        self.p.N_repeats = 1

        self.p.t_mot_load = 1.0
        self.p.t_imaging_pulse = 20.e-6

        # self.xvar('amp_imaging',np.linspace(0.05,0.15,5))
        # self.p.amp_imaging = 0.1

        self.data.apd = self.data.add_data_container(1)

        self.camera_params.gain = 300

        self.scanning()
        self.finish_prepare(shuffle=True)

    def scanning(self):
        # self.xvar('t_tweezer_paint_rampdown',np.linspace(0.0,10.,5)*1.e-3)
        
        # self.xvar('v_pd_hf_lightsheet_rampdown_end', np.linspace(0.6,2.0,9))
        # self.xvar('t_tweezer_hold', np.linspace(0.,500.,4) * 1.e-3)
        # self.xvar('t_hf_tweezer_1064_ramp',np.linspace(160,220,3)*1.e-3)
        # self.xvar('v_pd_lightsheet_rampup_end',np.linspace(7.12,,5))
        # self.xvar('i_hf_tweezer_load_current',np.linspace(192.,195.,15))
        # self.xvar('v_hf_tweezer_paint_amp_max',np.linspace(-5.,-1.,5))
        # self.xvar('v_pd_hf_tweezer_1064_rampdown3_end',np.linspace(2.,6.,5))
        # self.p.v_pd_lightsheet_rampup_end = 6.7
        # self.p.i_hf_tweezer_load_current = 193.3
        # self.p.t_hf_tweezer_1064_ramp = 0.19
        # self.p.v_pd_hf_lightsheet_rampdown_end = 0.9
        # self.p.v_pd_hf_tweezer_1064_rampdown3_end = 4.30
        # self.p.v_hf_tweezer_paint_amp_max = -2.5

        # self.xvar('t_mot_load',[0.75,1.,1.5,1.75])

        # self.xvar('phase_slm_mask',np.linspace(0.,5.,17))

        # self.adjust('t_tof',100.e-6,3000.e-6)
        # self.adjust('phase_slm_mask',0.,4*np.pi)
        # self.adjust('dimension_slm_mask',10.e-6,200.e-6)

        # self.xvar('t_tweezer_hold',np.linspace(10.,1000.,4)*1.e-6)
        # self.xvar('v_hf_tweezer_paint_amp_max',np.linspace(0,-3,10))
        pass

    @kernel
    def scan_kernel(self):

        # self.slm.write_phase_mask_kernel(dimension=self.p.dimension_slm_mask,
        #                                  phase=self.p.phase_slm_mask)
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        # self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers()

        delay(10.e-3)
         
        delay(self.p.t_tweezer_hold)
        
        self.tweezer.off()

        delay(self.p.t_tof)

        self.ttl.pd_scope_trig3.pulse(1.e-6)
        # self.abs_image()
        self.abs_image_and_apd(self.data.apd)

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

