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

class feedback(EnvExperiment, Base, Feedback):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.DISPERSIVE)
        
        ### parameters

        self.p.t_raman_pulse = self.p.t_raman_pi_pulse / 2
        self.p.t_raman_pulse_ideal = self.p.t_raman_pulse + 200.e-9

        self.p.back_action_coherence = .86

        self.p.amp_imaging = 0.2
        self.p.t_img_pulse = 5.e-6
        self.p.frequency_lightshift = 3.48e+04  # Hz, for imaging amp 0.2
        # self.xvar('frequency_lightshift', self.p.frequency_lightshift * np.linspace(.7,1.3,5))
        self.p.v_apd_all_up = -0.151840625
        self.p.v_apd_all_down = -0.2231875

        self.p.phase_offset = 0.0#0.55 #- 0.7/Omega
        # self.xvar('phase_offset', np.linspace(-0.9, -0.5, 10)/Omega)

        self.p.delta_t = 0.
        
        self.p.n_photons_per_shot = 800
        self.p.n_std_photons_per_shot = 50

        self.p.feedback_fractional_initial_offset = 5.

        self.p.update_raman_frequency_bool = 1
    
        self.p.include_photon_noise = 1

        self.p.N_repeats = 500
        
        self.m = 21 # feedback grid size
        # self.N_pulses = 15 # number of steps of evolution
        self.N_pulses = 20 # number of steps of evolution

        self.p.t_tweezer_hold = 30.e-3

        self.p.feedback_guess_span_Omega = 5.0

        ###

        # timing docs: https://docs.google.com/document/d/11tzbmMhPQ-lycEPc1OWHo9MnWyrR9bsQly9bz8DF_WQ/edit?tab=t.cvj0bnjp2og4#heading=h.pimm1a640bup
        self.p.t_calculation_slack_compensation_mu = int64(0.61 * self.m * 1.e3) + 15000 if self.m > 10 else int64(10000)
        self.p.t_fifo_mu = int64(18416)
        self.p.t_raman_set_pretrigger_mu = int64(4000) & ~7 # int64(1260)
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
        self.data.omega_raman = self.data.add_data_container(self.N_pulses)
        self.data.Omega = self.data.add_data_container(self.N_pulses)
        self.data.apd = self.data.add_data_container(self.N_pulses)

        self.data.s_z = self.data.add_data_container(self.N_pulses)
        self.data.t = self.data.add_data_container(self.N_pulses)

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
                          m = self.m,
                          fractional_initial_offset = self.p.feedback_fractional_initial_offset,
                          guess_span_Omega = self.p.feedback_guess_span_Omega,
                          )
        
        self.zidx = np.argmin(abs(self.omega_guess_list - self.p.frequency_raman_transition * 2*np.pi))

        ###

        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=True)
        
        self._phase = 0

        self.finish_prepare()

    @kernel
    def feedback_loop(self, t_start_mu,
                       update_raman_frequency=1,
                       update_rabi_frequency=0,
                       include_photon_noise=1):
        
        self.omega_z_lightshift = 2*np.pi * self.p.frequency_lightshift

        k = 0
        f = self.omega_guess_start / (2*np.pi)
        omega_prev = 0.

        t_step = t_start_mu

        at_mu(now_mu() & ~7)

        at_mu(t_start_mu - 10000)
        self.raman.set_frequency_fast(f)
        self.raman.reset_phase()
        # aprint(self.raman.get_phase())
        # self._phase = 0
        phase_tracker = 0.

        at_mu(t_start_mu)
        
        for i in range(self.N_pulses):

            f = self.omega_raman / (2*np.pi)
            self.data.omega_raman.shot_data[i] = self.omega_raman
            # self.data.Omega.shot_data[i+1] = var

            if i > 0:
                at_mu(t_step - self.p.t_raman_set_pretrigger_mu)
                self.raman.set_frequency_fast(f)

            t = (t_step - t_start_mu)*1.e-9
            at_mu(t_step)

            # phi_pow = self.raman.get_phase()
            
            # phi = self.raman.pow_to_phase(phi_pow)
            
            phase_tracker = phase_tracker + (1.e-9*self.p.t_between_pulses_mu - self.p.delta_t) * omega_prev + self.p.delta_t * omega_raman + # self.p.phase_offset
            phi = phase_tracker

            self.raman.pulse(self.p.t_raman_pulse)
            k = self.measurement(i)
            omega_prev = self.omega_raman
            self.omega_raman, self.Omega = self.generate_posterior(k, t,
                                                    phase_raman_pulse_start=phi,
                                                    update_raman_frequency=update_raman_frequency,
                                                    update_rabi_frequency=update_rabi_frequency,
                                                    include_photon_noise=include_photon_noise)

            # aprint( (phi_pow - self._phase ) & int32(0xffff) )
            # self._phase = phi_pow

            t_step += self.p.t_between_pulses_mu

            self.data.t.shot_data[i] = t + self.p.t_raman_pulse + self.p.t_img_pulse
            self.data.s_z.shot_data[i] = self.state_z[self.zidx]

    @kernel
    def scan_kernel(self):
        self.core.break_realtime()

        self.integrator.init()

        self.initialize_feedback()
        delay(10.e-3)
        
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        # self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask, verbose=False)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers(squeeze=True)
        self.prep_raman(frequency_transition=self.omega_guess_start/(2*np.pi),
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
        self.omega_raman = self.omega_guess_start
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