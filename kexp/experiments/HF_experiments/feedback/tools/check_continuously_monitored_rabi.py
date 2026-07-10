from artiq.experiment import *
from kexp import Base, img_types, cameras
import numpy as np
from artiq.language import now_mu, at_mu, delay_mu, delay

class hf_monitored_rabi(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,
                      camera_select=cameras.andor,
                      save_data=False,
                      imaging_type=img_types.DISPERSIVE)

        # self.p.frequency_raman_transition = 119.4641e6
        # self.p.frequency_raman_transition = 119918210.0

        # self.p.v_pd_hf_tweezer_1064_rampdown2_end = .5

        # self.xvar('t_continuous_rabi',np.linspace(0.,400.e-6,10))
        self.p.t_continuous_rabi = 1.

        # self.p.v_pd_hf_tweezer_squeeze_power = 8.

        # self.xvar('t_raman_pulse',9.2565e-06 + 9.2565e-06*np.linspace(0.,1.,7))
        # self.xvar('t_raman_pulse', 9.2565e-06 + np.array([0.0, (9.2565e-06) / 2, 9.2565e-06]))
        # self.p.t_raman_pulse = (9.2565e-06) / 2
        
        # self.xvar('amp_imaging',np.linspace(.1,.6, 5))
        self.p.amp_imaging = .2 

        # self.p.hf_imaging_detuning = -568.e6 # 182.

        # self.p.hf_imaging_detuning_mid = -514.e6 # -1 --> 0
        
        # self.p.dimension_slm_mask = 20.e-6

        # calibration run 67685
        # img amp 0.2, pulse time 1.0e-05 s
        # self.p.frequency_lightshift = 3.28e+04 # Hz
        # self.p.frequency_lightshift = 3.8e+04  # Hz
        self.p.frequency_lightshift = 3.79e+04  # Hz

        # self.xvar('phase_slm_mask',np.linspace(0.0*np.pi,.5*np.pi,10))
        # self.p.phase_slm_mask = 0.186 * np.pi

        self.p.frequency_raman_transition_lightshifted = self.p.frequency_lightshift + self.p.frequency_raman_transition

        # self.p.fraction_power_raman = 1.

        self.p.t_tweezer_hold = 20.e-3
        self.p.t_tof = 20.e-6
        self.p.t_mot_load = 1.0
        
        self.p.N_repeats = 200

        # self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=False)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        
        self.set_imaging_detuning(frequency_detuned = self.p.frequency_detuned_hf_midpoint)
        self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask,dimension=self.p.dimension_slm_mask)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers(squeeze=True)
        # self.prep_raman(frequency_transition=self.p.frequency_raman_transition_lightshifted,
        #                 phase_mode=0)
        self.prep_raman(frequency_transition=self.p.frequency_raman_transition,
                        phase_mode=0)

        self.raman.set_up_fast_frequency_update(aggressive_mode=1)
        self.raman.set_frequency_fast(self.p.frequency_raman_transition_lightshifted,
                                      do_io_update=False)
        delay(1.e-3)

        self.raman.on()

        # delay( self.p.t_raman_pi_pulse * 10 )

        self.raman.io_update()
        self.imaging.on()
        delay_mu(91)
        
        # self.raman.on()
        self.ttl.pd_scope_trig3.pulse(1.e-6)
        
        delay(self.p.t_continuous_rabi)
        self.imaging.off()
        self.raman.off()

        self.ttl.raman_shutter.off()
        self.tweezer.off()

        # self.core.wait_until_mu(now_mu())
        # self.scope.read_sweep(0)
        # self.core.break_realtime()
        # delay(30.e-3)

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        # self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        # aprint(self.scope._data)
        self.end(expt_filepath)