from artiq.experiment import *
from artiq.language import now_mu, delay, delay_mu, TFloat, TArray, TTuple, at_mu, parallel
from kexp import Base, img_types, cameras
from kexp.base import Feedback
from kexp.calibrations.imaging import integrator_calibration
import numpy as np
from numpy import int64

from kexp.util.artiq.async_print import aprint

T_CONV_MU = 30

from waxx.control.artiq.DDS import T_AD9910_REGISTER_UPDATE_FROM_PHASE_ORIGIN_MU

from kexp.experiments.HF_experiments.feedback.expt_params_feedback import ExptParams as ExptParamsFeedback

class feedback(EnvExperiment, Base, Feedback):

    def prepare(self):
    
        self.p = ExptParamsFeedback()
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.DISPERSIVE,
                      expt_params=self.p)
        
        self.p.update_raman_frequency_bool = 0
        self.p.include_photon_noise = 1

        self.p.N_repeats = 21
        self.p.N_pulses = 20 # number of steps of evolution
        
        ### parameters
        
        Omega = np.pi / self.p.t_raman_pi_pulse

        # self.p.intermediate_detuning = 2*np.pi*self.p.frequency_raman_transition + 2*Omega*0
        # self.xvar('intermediate_detuning',  2*np.pi*self.p.frequency_raman_transition + Omega*(np.linspace(10, 11, 20)))

        detuning_list = np.array([0., 1., 0., 1., 2.,
           0.,  5.,  0.,  0.,  0.,
            0., -0., -0. ,  0. , -0., 0., 0., 0., 0., 0., 0., 0.])
            # detuning_list = 3*(np.random.random(15) -0.5)

        # detuning_list = np.array([0.,   0.30609096,  0.38354877,  0.18202263,  0.29501175,
        #     -0.31005943,  0.38354877,  0.30609096,  0.11595314,  0.18202263,
        #         0.35998194, -0.26850061, -0.0969936 ,  0.3203508 , -0.00077061]) / 2

        self.p.omega_pulse_list = 2*np.pi*self.p.frequency_raman_transition + (Omega * detuning_list)
        
        ###

        # timing docs: https://docs.google.com/document/d/11tzbmMhPQ-lycEPc1OWHo9MnWyrR9bsQly9bz8DF_WQ/edit?tab=t.cvj0bnjp2og4#heading=h.pimm1a640bup
        self.p.t_between_pulses_mu = self.compute_t_between_pulses_mu(
            t_calculation_slack_compensation_mu=self.p.t_calculation_slack_compensation_mu,
            t_raman_pulse=self.p.t_raman_pulse,
            t_img_pulse=self.p.t_img_pulse,
            t_fifo_mu=self.p.t_fifo_mu
        )

        print(f'time between pulses: {self.p.t_between_pulses_mu / 1.e3:1.2f} (us)')
        print(f'calculation slack compensation: {self.p.t_calculation_slack_compensation_mu / 1.e3:1.2f} (us)')

        ### setup data containers

        self.idx = 0
        self.data.omega_raman = self.data.add_data_container(self.p.N_pulses)
        self.data.Omega = self.data.add_data_container(self.p.N_pulses)
        self.data.apd = self.data.add_data_container(self.p.N_pulses)

        self.data.s_z = self.data.add_data_container(self.p.N_pulses)
        self.data.t = self.data.add_data_container(self.p.N_pulses)

        ### feedback setup
        # uses calibration for v_apd and n_photons from integrator_calibration
        # unless those values are explicitly passed below (commented out)

        Feedback.__init__(self,
                          t_raman_pulse = self.p.t_raman_pulse,
                          t_raman_pulse_ideal = self.p.t_raman_pulse_ideal,
                          t_img_pulse = self.p.t_img_pulse,
                          amp_imaging = self.p.amp_imaging,
                          t_raman_pi_pulse = self.p.t_raman_pi_pulse,
                          frequency_z_lightshift = self.p.frequency_lightshift,
                          v_apd_all_up= self.p.v_apd_all_up,
                          v_apd_all_down = self.p.v_apd_all_down,
                          n_photons_per_shot=self.p.n_photons_per_shot,
                          std_n_photons_per_shot=self.p.n_std_photons_per_shot,
                          frequency_resonance = self.p.frequency_raman_transition,
                          feedback_grid_size = self.p.feedback_grid_size,
                          fractional_grid_center_offset = self.p.feedback_fractional_grid_center_offset,
                          fractional_initial_offset = self.p.feedback_fractional_initial_offset,
                          guess_span_Omega = self.p.feedback_guess_span_Omega,
                          feedback_apd_map_enabled=self.p.feedback_apd_map_enabled,
                          feedback_apd_map_a=self.p.feedback_apd_map_a,
                          feedback_apd_map_b=self.p.feedback_apd_map_b,
                          back_action_coherence = self.p.back_action_coherence
                          )
        
        self.zidx = self.p.feedback_resonance_grid_index

        ###

        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=True)
        
        self._phase = 0

        self.data.phi = self.data.add_data_container(self.p.N_pulses)
        self.data.ts = self.data.add_data_container(self.p.N_pulses)

        self.finish_prepare()

    @kernel
    def feedback_loop(self, t_start_mu,
                       update_raman_frequency=0,
                       update_rabi_frequency=0,
                       include_photon_noise=1):

        self.omega_z_lightshift = 2*np.pi * self.p.frequency_lightshift

        k = 0
        f = self.omega_raman / (2*np.pi)
        omega_prev = 0.

        t_start_mu = t_start_mu & ~7
        t_step = t_start_mu

        at_mu(t_start_mu - (10000 & ~7))

        self.raman.set_frequency_fast(self.p.omega_pulse_list[0] / (2*np.pi))
        self.raman.reset_phase()
        # aprint(self.raman.get_phase())
        # self._phase = 0
        phase_tracker = 0.

        at_mu(t_start_mu)

        tP = self.p.t_between_pulses_mu
        dt = self.p.delta_t_mu
        tR = self.p.t_raman_set_pretrigger_mu
        
        for i in range(self.p.N_pulses):
            # self.omega_raman = self.p.intermediate_detuning

            self.omega_raman = self.p.omega_pulse_list[i] 

            # if i == 2:
            #     self.omega_raman = self.p.intermediate_detuning
            #     omega_prev = self.p.omega_pulse_list[1]
            # elif i == 3:
            #     self.omega_raman = self.p.omega_pulse_list[3] 
            #     omega_prev = self.p.intermediate_detuning
            # else:
            #     self.omega_raman = self.p.omega_pulse_list[i] 
            #     omega_prev = self.p.omega_pulse_list[i-1] if i > 0 else 0.
            #     #pass
            
            f = self.omega_raman / (2*np.pi)
            self.data.omega_raman.shot_data[i] = self.omega_raman
            # self.data.Omega.shot_data[i+1] = var

            #if i > 0:
            at_mu(t_step - self.p.t_raman_set_pretrigger_mu)
            self.raman.set_frequency_fast(f)

            t = (t_step - t_start_mu)*1.e-9
            at_mu(t_step)                                                                                                                           

            phase_tracker += ((tP - tR + dt) * omega_prev + (tR - dt) * self.omega_raman) * 1.e-9

            phi = phase_tracker

            self.raman.pulse(self.p.t_raman_pulse)

            k = self.measurement(i)

            omega_prev = self.omega_raman

            self.omega_raman, self.Omega = self.generate_posterior(k, t,
                                                    phase_raman_pulse_start=phi,
                                                    update_raman_frequency=update_raman_frequency,
                                                    update_rabi_frequency=update_rabi_frequency,
                                                    include_photon_noise=include_photon_noise)

            t_step += self.p.t_between_pulses_mu

            self.data.t.shot_data[i] = t + self.p.t_raman_pulse + self.p.t_img_pulse
            self.data.s_z.shot_data[i] = self.state_z[self.zidx]

            self.data.phi.put_data(phi,i)
            self.data.ts.put_data(t,i)

    @kernel
    def scan_kernel(self):
        self.core.break_realtime()

        self.integrator.init()

        self.initialize_feedback()
        self.reset_initial_omega_from_params()
        delay(10.e-3)
        
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        # self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask, verbose=False)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers(squeeze=True)
        self.prep_raman(frequency_transition=self.omega_raman/(2*np.pi),
                        phase_mode=0)

        t_pulse_start_mu = now_mu() + 5000000

        self.raman.set_up_fast_frequency_update()

        at_mu(t_pulse_start_mu - 20000) # beginning of time
        self.ttl.pd_scope_trig3.pulse(1.e-6)

        self.feedback_loop(t_start_mu=t_pulse_start_mu,
                           update_raman_frequency=self.p.update_raman_frequency_bool,
                           include_photon_noise=self.p.include_photon_noise)

        delay(self.p.t_tweezer_hold)
        self.raman.clean_up_fast_frequency_update()

        self.tweezer.off()
        delay(self.p.t_tof)
        self.abs_image()

        self.core.wait_until_mu(now_mu())
        self.reset_initial_omega_from_params()
        # print((self.data.omega_raman.shot_data/(2*np.pi) - self.p.frequency_raman_transition)/1.e3)
        # self.scope.read_sweep(0)
        # self.core.break_realtime()
        delay(30.e-3)

    @kernel
    def measurement(self, i):
        T_CONV_MU = 80
        self.integrator.begin_integrate(reset=False)
        self.imaging.pulse(self.p.t_img_pulse)
        self.integrator.stop_and_settle()
        t = now_mu()
        # start the clear after the integrator voltage is already in the sampler
        at_mu(t + T_CONV_MU)
        self.integrator.clear(t=0)
        at_mu(t)
        self.data.apd.shot_data[i] = self.integrator.sample()
        v = self.convert_measurement(self.data.apd.shot_data[i])
        i = i + 1
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