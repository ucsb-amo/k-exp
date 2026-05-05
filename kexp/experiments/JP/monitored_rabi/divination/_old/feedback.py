from artiq.experiment import *
from artiq.language import now_mu, delay, delay_mu, TFloat, TArray, TTuple, at_mu
from kexp import Base, img_types, cameras
from kexp.base import Feedback
import numpy as np

from kexp.util.artiq.async_print import aprint

class feedback(EnvExperiment, Base, Feedback):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.DISPERSIVE)
        
        ### parameters

        self.xvar('dummy',[0])

        self.p.amp_imaging = 0.23
        
        self.p.t_raman_pulse = self.p.t_raman_pi_pulse / 3

        self.N_pulses = 8 # number of steps of evolution
        self.m = 21 # feedback grid size
        
        self.p.N_repeats = 1

        self.p.t_calculation_slack_compensation_mu = 32000
        self.p.feedback_guess_span_Omega = 5.0
        self.p.feedback_fractional_initial_offset = 10.0
        self.p.n_photons_per_us_per_imgamp = 431.77
        self.p.feedback_photon_count_scale = 0.1

        ### calibrations

        # 5 us img pulse
        # self.p.t_img_pulse = 5.e-6
        # self.v_apd_all_up = -0.192
        # self.v_apd_all_down = -0.219

        # 10 us img pulse
        self.p.t_img_pulse = 10.e-6
        self.p.v_apd_all_up = -0.15
        self.p.v_apd_all_down = -0.22

        # arb pulse length
        # self.p.t_img_pulse = 15.e-6
        # self.v_apd_all_up = 10200. * self.p.t_img_pulse - 0.242
        # self.v_apd_all_down = -0.23

        # for vpd = 0.3, lightshift 18.74kHz (#63034)
        self.p.frequency_lightshift = 21.03e3

        self.Omega = np.pi / (self.p.t_raman_pi_pulse)

        self.p.t_between_pulses_mu = self.compute_t_between_pulses_mu(
            t_calculation_slack_compensation_mu=self.p.t_calculation_slack_compensation_mu,
            t_raman_pulse=self.p.t_raman_pulse,
            t_img_pulse=self.p.t_img_pulse,
        )

        ### setup data containers

        self.idx = 0
        self.data.omega_raman = self.data.add_data_container(self.N_pulses)
        self.data.Omega = self.data.add_data_container(self.N_pulses)
        self.data.apd = self.data.add_data_container(self.N_pulses)
        self.data.counts = self.data.add_data_container(self.N_pulses)
        self.data.ts = self.data.add_data_container(self.N_pulses)

        self.data.s_z = self.data.add_data_container(self.N_pulses)
        self.data.t = self.data.add_data_container(self.N_pulses)

        ### feedback setup

        Feedback.__init__(
            self,
            m=self.m,
            frequency_resonance=self.p.frequency_raman_transition,
            Omega=self.Omega,
            fractional_initial_offset=self.p.feedback_fractional_initial_offset,
            guess_span_Omega=self.p.feedback_guess_span_Omega,
            t_raman_pulse=self.p.t_raman_pulse,
            t_img_pulse=self.p.t_img_pulse,
            frequency_z_lightshift=self.p.frequency_lightshift,
            amp_imaging=self.p.amp_imaging,
            n_photons_per_us_per_imgamp=self.p.n_photons_per_us_per_imgamp,
            photon_count_scale=self.p.feedback_photon_count_scale,
            v_apd_all_up=self.p.v_apd_all_up,
            v_apd_all_down=self.p.v_apd_all_down,
        )

        self.p.omega_guess_list = self.omega_guess_list
        self.p.N_photons_per_shot = self.N_photons_per_shot

        self.omega_raman = self.omega_guess_start # omega_ctrl

        ###
        
        # self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=True)
        
        self.tR = np.zeros(self.N_pulses,dtype=np.int64)
        self.finish_prepare()

    @kernel
    def scan_kernel(self):
        self.idx = 0
        self.omega_raman = self.omega_guess_start

        self.core.break_realtime()

        zidx = self.m//2

        self.integrator.init()

        self.initialize_feedback()
        delay(10.e-3)
        
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        # self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers(squeeze=True)
        self.prep_raman(frequency_transition=self.omega_raman, phase_mode=1)

        t_pulse_start_mu = now_mu() + 10000000

        f = self.omega_raman/(2*np.pi)
        self.raman.set(frequency_transition=f, t_phase_origin_mu=t_pulse_start_mu)

        at_mu(t_pulse_start_mu - 20000) # beginning of time
        self.ttl.pd_scope_trig3.pulse(1.e-6)

        var = self.Omega
        t_step = t_pulse_start_mu
        

        at_mu(t_step)
        for i in range(self.N_pulses):

            self.data.s_z.shot_data[i] = self.state_z[zidx]
            self.data.omega_raman.shot_data[i] = self.omega_raman
            self.data.Omega.shot_data[i] = var

            at_mu(t_step - (5327))
            ti = now_mu()
            self.raman.set(frequency_transition=f)
            self.tR[i] = now_mu() - ti

            at_mu(t_step)
            t_mu = now_mu()
            t = (t_mu - t_pulse_start_mu)*1.e-9
            self.data.t.shot_data[i] = t

            self.raman.pulse(self.p.t_raman_pulse)
            k = self.measurement()
            self.omega_raman, var = self.generate_posterior(k, t)

            f = self.omega_raman / (2*np.pi)

            t_step += self.p.t_between_pulses_mu

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()
        delay(self.p.t_tof)
        self.abs_image()

        self.core.wait_until_mu(now_mu())
        print((self.data.omega_raman.shot_data/(2*np.pi) - self.p.frequency_raman_transition)/1.e3)
        # self.scope.read_sweep(0)
        # self.core.break_realtime()
        delay(30.e-3)

        print(self.tR)

    @kernel
    def measurement(self):
        idx = self.idx
        self.integrated_imaging_pulse(self.data.apd, t=self.p.t_img_pulse, idx=self.idx)
        v = self.convert_measurement(self.data.apd.shot_data[idx])
        self.idx = self.idx + 1
        return v

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)