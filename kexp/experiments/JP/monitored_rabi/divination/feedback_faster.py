from artiq.experiment import *
from artiq.language import now_mu, delay, delay_mu, TFloat, TArray, TTuple, at_mu
from kexp import Base, img_types, cameras
from kexp.base import Feedback
import numpy as np

from kexp.util.artiq.async_print import aprint

T_CONV_MU = 30

class feedback(EnvExperiment, Base, Feedback):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.DISPERSIVE)
        
        ### parameters

        self.p.do_feedback = 0

        self.xvar('dummy',[0])
        self.p.N_repeats = 30
        
        self.p.t_calculation_slack_compensation_mu = 34000

        self.N_pulses = 10 # number of steps of evolution
        self.m = 21 # feedback grid size
        self.p.feedback_guess_span_Omega = 5.0
        
        self.p.feedback_fractional_initial_offset = 0.
        
        self.p.n_photons_per_us_per_imgamp = 215.885
        self.p.feedback_photon_count_scale = 0.1
    
        self.p.t_raman_pulse = self.p.t_raman_pi_pulse/2
        self.p.t_tweezer_hold = 30.e-3

        ### calibrations

        # # 5 us img pulse .41 img amp
        self.p.amp_imaging = 0.41
        self.p.t_img_pulse = 5.e-6
        self.p.v_apd_all_up = -0.175546875
        self.p.v_apd_all_down = -0.22287500000000002
        self.p.frequency_lightshift = 19136.37136929461
        self.p.frequency_lightshift += 12.e3 # magic number

        # 10 us img pulse .41 img amp
        # self.p.amp_imaging = 0.41
        # self.p.t_img_pulse = 10.e-6
        # self.p.v_apd_all_up = -0.127984375 
        # self.p.v_apd_all_down = -0.23432187500000004
        # self.p.frequency_lightshift = 19136.37136929461 + 12.e3

        # # 5 us img pulse .82 img amp
        # self.p.amp_imaging = 0.82
        # self.p.t_img_pulse = 5.e-6
        # self.p.v_apd_all_up = -0.10875625
        # self.p.v_apd_all_down = -0.21389687500000001
        # self.p.frequency_lightshift = 37624.39419087137 + 12.e3

        ###

        self.p.t_between_pulses_mu = self.compute_t_between_pulses_mu(
            t_calculation_slack_compensation_mu=self.p.t_calculation_slack_compensation_mu,
            t_raman_pulse=self.p.t_raman_pulse,
            t_img_pulse=self.p.t_img_pulse,
        )
        print(f'time between pulses: {self.p.t_between_pulses_mu / 1.e3:1.2f} (us)')
        print(f'calculation slack compensation: {self.p.t_calculation_slack_compensation_mu / 1.e3:1.2f} (us)')

        ### setup data containers

        self.idx = 0
        self.data.omega_raman = self.data.add_data_container(self.N_pulses+1)
        self.data.Omega = self.data.add_data_container(self.N_pulses+1)
        self.data.apd = self.data.add_data_container(self.N_pulses+1)

        self.data.s_z = self.data.add_data_container(self.N_pulses+1)
        self.data.t = self.data.add_data_container(self.N_pulses+1)

        ### feedback setup

        Feedback.__init__(self,
                          t_raman_pulse = self.p.t_raman_pulse,
                          t_img_pulse = self.p.t_img_pulse,
                          amp_imaging = self.p.amp_imaging,
                          t_raman_pi_pulse = self.p.t_raman_pi_pulse,
                          frequency_resonance = self.p.frequency_raman_transition,
                          frequency_z_lightshift = self.p.frequency_lightshift,
                          v_apd_all_up = self.p.v_apd_all_up,
                          v_apd_all_down = self.p.v_apd_all_down,
                          n_photons_per_us_per_imgamp = self.p.n_photons_per_us_per_imgamp,
                          photon_count_scale = self.p.feedback_photon_count_scale,
                          m = self.m,
                          fractional_initial_offset = self.p.feedback_fractional_initial_offset,
                          guess_span_Omega = self.p.feedback_guess_span_Omega,
                          lut_size = 4096)

        ###
        
        self.finish_prepare()

    @kernel
    def feedback_loop(self, t_start_mu, feedback=1):

        zidx = len(self.omega_guess_list)//2
        k = 0
        f = 0.
        var = self.Omega

        self.data.apd.shot_data[0] = self.v_apd_all_up
        self.data.s_z.shot_data[0] = self.state_z[zidx]
        self.data.omega_raman.shot_data[0] = self.omega_raman
        # self.data.Omega.shot_data[0] = var

        t_step = t_start_mu
        at_mu(t_start_mu)
        for i in range(self.N_pulses):

            self.data.omega_raman.shot_data[i+1] = self.omega_raman
            # self.data.Omega.shot_data[i+1] = var

            at_mu(t_step - (1300))
            self.raman.set_frequency_fast(frequency_transition=f)

            t = (t_step - t_start_mu)*1.e-9
            at_mu(t_step)
            self.raman.pulse(self.p.t_raman_pulse)
            k = self.measurement()
                
            if feedback:
                self.omega_raman, var = self.generate_posterior(k, t)
            else:
                _, var = self.generate_posterior(k, t)

            f = self.omega_raman / (2*np.pi)

            t_step += self.p.t_between_pulses_mu

            self.data.t.shot_data[i+1] = t + self.p.t_raman_pulse + self.p.t_img_pulse
            self.data.s_z.shot_data[i+1] = self.state_z[zidx]

    @kernel
    def scan_kernel(self):
        self.idx = 1
        self.omega_raman = self.omega_guess_start

        self.core.break_realtime()

        self.integrator.init()

        self.initialize_feedback()
        delay(10.e-3)
        
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask, verbose=False)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers(squeeze=True)
        self.prep_raman(frequency_transition=self.omega_raman/(2*np.pi), phase_mode=1)

        t_pulse_start_mu = now_mu() + 10000000

        f = self.omega_raman/(2*np.pi)
        self.raman.set(frequency_transition=f, t_phase_origin_mu=t_pulse_start_mu)

        self.raman.set_up_fast_frequency_update()

        at_mu(t_pulse_start_mu - 20000) # beginning of time
        self.ttl.pd_scope_trig3.pulse(1.e-6)

        self.feedback_loop(t_start_mu=t_pulse_start_mu, feedback=self.p.do_feedback)
            
        delay(self.p.t_tweezer_hold)
        self.raman.clean_up_fast_frequency_update()

        self.tweezer.off()
        delay(self.p.t_tof)
        self.abs_image()

        self.core.wait_until_mu(now_mu())
        print((self.data.omega_raman.shot_data/(2*np.pi) - self.p.frequency_raman_transition)/1.e3)
        # self.scope.read_sweep(0)
        # self.core.break_realtime()
        delay(30.e-3)

    @kernel
    def measurement(self):
        T_CONV_MU = 80
        idx = self.idx
        self.integrator.begin_integrate(reset=False)
        self.imaging.pulse(self.p.t_img_pulse)
        self.integrator.stop_and_settle()
        t = now_mu()
        # start the clear after the integrator voltage is already in the sampler
        at_mu(t + T_CONV_MU)
        self.integrator.clear(t=0)
        at_mu(t)
        self.data.apd.shot_data[idx] = self.integrator.sample()
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