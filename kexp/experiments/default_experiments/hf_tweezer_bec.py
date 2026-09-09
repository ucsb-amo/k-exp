
import numpy as np
from artiq.experiment import *
from artiq.language.core import delay, kernel
from kexp import Base, img_types, cameras, Adjust


class hf_bec(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      setup_camera=True,
                      save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION,
                      warmup_shots=3)

        
        self.p.t_mot_load = 1.0
        self.p.t_imaging_pulse = 10.e-6
        
        self.p.t_tweezer_hold = 100.e-3

        # self.xvar('t_tof',np.linspace(1000.,4000.,5)*1.e-6)
        self.p.t_tof = 4.e-3

        self.data.apd = self.data.add_data_container(1)

        self.p.N_repeats = 2

        # Adjust.__init__(self)sss

        self.scanning()
        self.finish_prepare(shuffle=True)

    def scanning(self):

        self.p.v_hf_tweezer_paint_amp_max = 1.35
        self.p.v_pd_hf_tweezer_1064_rampdown2_end = 2.75
        # self.p.v_pd_lightsheet_rampdown3_end = 0.00
        # self.p.v_pd_hf_lightsheet_rampdown_end = 0.45

        self.p.t_hf_tweezer_1064_rampdown = 550.e-3
        self.xvar('t_hf_tweezer_1064_rampdown2', np.linspace(100.,300.,5)*1.e-3)

        self.p.t_feshbach_field_ramp2 = 50.e-3
        # self.xvar('t_feshbach_field_ramp2',np.linspace(10.,50.,3)*1.e-3)

        # self.p.t_lightsheet_compression_ramp = 210.e-3
        # self.xvar('t_lightsheet_compression_ramp',np.linspace(5.e-3,250.e-3,7))
        # self.p.v_pd_lightsheet_rampdown3_end = 0.0
        # self.p.v_pd_lightsheet_axial_compression = 6.6
        # self.xvar('v_pd_lightsheet_axial_compression',np.linspace(4.5, 6.8, 11))

        # self.xvar('t_tweezer_paint_rampdown',np.linspace(0.0,10.,5)*1.e-3)
        
        # self.xvar('v_pd_hf_lightsheet_rampdown_end', np.linspace(0.2,0.5,7))
        # self.xvar('t_tweezer_hold', np.linspace(0.,500.,5) * 1.e-3)
        # self.xvar('t_hf_tweezer_1064_ramp',np.linspace(160,220,3)*1.e-3)
        # self.xvar('v_pd_lightsheet_rampup_end',np.linspace(7.12,,5))
        # self.xvar('i_hf_tweezer_load_current',np.linspace(192.,195.,15))
        # self.xvar('v_hf_tweezer_paint_amp_max',np.linspace(-0.6,1.8,7))
        # self.xvar('v_hf_tweezer_paint_amp_max',np.linspace(0.2,2.5,8))
        # self.xvar('v_pd_hf_tweezer_1064_rampdown3_end',np.linspace(2.,5.,8))
        # self.xvar('v_pd_lightsheet_rampdown3_end',np.linspace(0.,0.3,5))
        # self.p.v_pd_lightsheet_rampup_end = 6.7
        # self.p.i_hf_tweezer_load_current = 193.3
        # self.p.t_hf_tweezer_1064_ramp = 0.19
        # self.p.v_pd_hf_lightsheet_rampdown_end = 0.9
        # self.p.v_pd_hf_tweezer_1064_rampdown3_end = 4.30
        # self.p.v_hf_tweezer_paint_amp_max = -2.5

        # self.xvar('t_mot_load',[0.75,1.,1.5,1.75])
        # self.xvar('v_pd_lightsheet_rampdown3_end',np.linspace(0.,0.4,5))

        # self.xvar('phase_slm_mask',np.linspace(0.,5.,17))

        # self.adjust('t_tof',100.e-6,3000.e-6)
        # self.adjust('phase_slm_mask',0.,4*np.pi)
        # self.adjust('dimension_slm_mask',10.e-6,200.e-6)
        # self.adjust('px_slm_phase_mask_position_x',1000,1100,step=1,dtype=int)
        # self.adjust('px_slm_phase_mask_position_y',800,850,step=1,dtype=int)

        # self.xvar('t_tweezer_hold',np.linspace(10.,1000.,4)*1.e-6)
        # self.xvar('v_hf_tweezer_paint_amp_max',np.linspace(0,-3,10))

        # self.p.phase_slm_mask = 1.6 * np.pi

        # self.xvar('i_hf_lightsheet_evap1_current',np.linspace(193.8,194.4,5))
        # self.p.i_hf_lightsheet_evap1_current = 194.05
        # self.p.i_hf_lightsheet_evap1_current = 18.

        # self.p.v_pd_lightsheet_rampup_end = 7.6
    
        # self.xvar('v_pd_hf_lightsheet_rampdown_end',np.linspace(.5,1.8,15))
        # self.p.v_pd_hf_lightsheet_rampdown_end = 1.0

        # self.xvar('t_hf_lightsheet_rampdown',np.linspace(500.,2000.,8)*1.e-3)
        # self.p.t_hf_lightsheet_rampdown = 1.

        # self.xvar('v_pd_lightsheet_rampdown3_end',
        #           np.linspace(0,self.p.v_pd_hf_lightsheet_rampdown_end,9))

        # self.xvar('v_zshim_current_magtrap', np.linspace(0.,0.15,5))

        # self.p.v_zshim_current_magtrap

        # self.xvar('v_hf_tweezer_paint_amp_max',np.linspace(1.3,2.4,7))
        # self.xvar('v_hf_tweezer_paint_amp_max',np.linspace(1.3,2.4,7))
        # self.p.v_hf_tweezer_paint_amp_max = 1.28

        # self.xvar('v_pd_hf_tweezer_1064_rampdown3_end',np.linspace(2.8,3.3,7))
        # self.p.v_pd_hf_tweezer_1064_rampdown3_end = 2.8

        # self.xvar('frequency_detuned_hf_f1m1',np.arange(-580.e6,-554.e6,3.e6))

        # self.xvar('v_pd_hf_tweezer_1064_rampdown2_end',np.linspace(0.08,0.1,5))
        # self.p.v_pd_hf_tweezer_1064_rampdown2_end = 0.09

        

        # self.p.i_hf_lightsheet_evap1_current = 194.3
        # self.p.t_hf_lightsheet_rampdown = 1.3

        # self.xvar('amp_imaging',np.linspace(0.05,0.15,5))

        # self.xvar('do_compression',[0,1])
        # self.p.do_compression = 0
        pass

    @kernel
    def scan_kernel(self):

        # self.slm.write_phase_mask_kernel(dimension=self.p.dimension_slm_mask,
        #                                  phase=self.p.phase_slm_mask,
        #                                  x_center=self.p.px_slm_phase_mask_position_x,
        #                                  y_center=self.p.px_slm_phase_mask_position_y)
        # self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        # self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers()

        # if self.p.do_compression:
        #     self.lightsheet.ramp(self.p.t_lightsheet_compression_ramp,
        #                                 v_end=self.p.v_pd_lightsheet_axial_compression)
        # else:
        #     delay(self.p.t_lightsheet_compression_ramp)
         
        delay(self.p.t_tweezer_hold)
        
        self.tweezer.off()
        self.lightsheet.off()
        

        delay(self.p.t_tof)

        

        delay(20.e-6)

        

        self.ttl.pd_scope_trig3.pulse(1.e-6)
        self.abs_image()
        # self.abs_image_and_apd(self.data.apd)
        # self.ttl.camera.pulse()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)

