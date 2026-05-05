from artiq.experiment import *
from artiq.language import now_mu, delay, delay_mu, TFloat, TArray, TTuple, at_mu
from kexp import Base, img_types, cameras
from kexp.base import Feedback
from kexp.calibrations.imaging import integrator_calibration
import numpy as np

from kexp.util.artiq.async_print import aprint

from numpy import int64

T_CONV_MU = 30

# self.p.frequency_lightshift = 19136.37136929461

# # 5 us img pulse .41 img amp
# self.p.amp_imaging = 0.41
# self.p.t_img_pulse = 5.e-6
# self.p.v_apd_all_up = -0.175546875
# self.p.v_apd_all_down = -0.22287500000000002
# self.p.frequency_lightshift = 19136.37136929461
# self.p.frequency_lightshift += 12.e3 # magic number

# 10 us img pulse .41 img amp
# self.p.amp_imaging = 0.41
# self.p.t_img_pulse = 10.e-6
# self.p.v_apd_all_up = -0.127984375 
# self.p.v_apd_all_down = -0.23432187500000004
# self.p.frequency_lightshift = 19136.37136929461
# self.p.frequency_lightshift += 12.e3 # magic number

# # 5 us img pulse .82 img amp
# self.p.amp_imaging = 0.82
# self.p.t_img_pulse = 5.e-6
# self.p.v_apd_all_up = -0.10875625
# self.p.v_apd_all_down = -0.21389687500000001
# self.p.frequency_lightshift = 37624.39419087137
# self.p.frequency_lightshift += 12.e3 # magic number

class feedback(EnvExperiment, Base, Feedback):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.DISPERSIVE)
        
        ### parameters

        self.p.t_raman_pulse = self.p.t_raman_pi_pulse / 2
        self.p.amp_imaging = 0.41
        self.p.t_img_pulse = 5.e-6

        self.p.update_raman_frequency_bool = 0
        self.p.include_photon_noise = 0

        # self.xvar('dummy',[0])
        self.p.N_repeats = 1
        
        self.p.t_calculation_slack_compensation_mu = 0
        self.N_pulses = 10 # number of steps of evolution
        self.m = 3 # feedback grid size
        self.p.feedback_guess_span_Omega = 5.0
        self.p.feedback_fractional_initial_offset = 0.

        self.p.t_tweezer_hold = 30.e-3

        ### calibrations

        # self.p.n_photons_per_us_per_img_amp = 231 
        # self.p.n_photons_per_shot = self.p.n_photons_per_us_per_img_amp * self.p.amp_imaging * self.p.t_img_pulse * 1.e6
        # self.p.n_photons_per_us_per_imgamp = 215.885
        # self.p.feedback_photon_count_scale = 0.1
        # self.p.std_n_photons_per_shot = 0.1 * self.p.n_photons_per_shot * self.p.feedback_photon_count_scale
        # self.p.frequency_lightshift = 19136.37136929461

        ###

        self.xvar('t_calculation_slack_compensation_mu',np.linspace(27000, 50000, 100))

        self.p.t_fifo_mu = int64(18416)
        self.p.t_raman_set_pretrigger_mu = int64(1260)
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
        self.data.omega_raman = self.data.add_data_container(self.N_pulses+1)
        self.data.Omega = self.data.add_data_container(self.N_pulses+1)
        self.data.apd = self.data.add_data_container(self.N_pulses+1)

        self.data.s_z = self.data.add_data_container(self.N_pulses+1)
        self.data.t = self.data.add_data_container(self.N_pulses+1)

        ### feedback setup
        # uses calibration for v_apd and n_photons from integrator_calibration
        # unless those values are explicitly passed below (commented out)

        Feedback.__init__(self,
                          t_raman_pulse = self.p.t_raman_pulse,
                          t_img_pulse = self.p.t_img_pulse,
                          amp_imaging = self.p.amp_imaging,
                          t_raman_pi_pulse = self.p.t_raman_pi_pulse,
                          frequency_resonance = self.p.frequency_raman_transition,
                        #   frequency_z_lightshift = self.p.frequency_lightshift,
                        #   photon_count_scale = self.p.feedback_photon_count_scale,
                          m = self.m,
                          fractional_initial_offset = self.p.feedback_fractional_initial_offset,
                          guess_span_Omega = self.p.feedback_guess_span_Omega,
                        #   n_photons_per_shot = self.p.n_photons_per_shot,
                        #   std_n_photons_per_shot = self.p.std_n_photons_per_shot
                        #   v_apd_all_up = self.p.v_apd_all_up,
                        #   v_apd_all_down = self.p.v_apd_all_down,
                        #   n_photons_per_shot=self.p.n_photons_per_shot
                          )
        ###
        
        self.finish_prepare(shuffle=False)

    @kernel
    def feedback_loop(self, t_start_mu,
                       update_raman_frequency=1,
                       update_rabi_frequency=0,
                       include_photon_noise=0):

        zidx = len(self.omega_guess_list)//2
        k = 0
        f = self.omega_guess_start / (2*np.pi)

        self.data.apd.shot_data[0] = self.v_apd_all_up
        self.data.s_z.shot_data[0] = self.state_z[zidx]
        self.data.omega_raman.shot_data[0] = self.omega_raman
        # self.data.Omega.shot_data[0] = var

        t_step = t_start_mu
        at_mu(t_start_mu)
        try:
            for i in range(self.N_pulses):

                self.data.omega_raman.shot_data[i+1] = self.omega_raman
                # self.data.Omega.shot_data[i+1] = var

                at_mu(t_step - self.p.t_raman_set_pretrigger_mu)
                self.raman.set_frequency_fast(frequency_transition=f)

                t = (t_step - t_start_mu)*1.e-9
                at_mu(t_step)
                self.raman.pulse(self.p.t_raman_pulse)
                k = self.measurement(i)
                self.omega_raman, self.Omega = self.generate_posterior(k, t,
                                                                       update_raman_frequency=update_raman_frequency,
                                                                       update_rabi_frequency=update_rabi_frequency,
                                                                       include_photon_noise=include_photon_noise)

                f = self.omega_raman / (2*np.pi)

                t_step += self.p.t_between_pulses_mu

                self.data.t.shot_data[i+1] = t + self.p.t_raman_pulse + self.p.t_img_pulse
                self.data.s_z.shot_data[i+1] = self.state_z[zidx]

            aprint("NO underflow in feedback loop at =", self.p.t_calculation_slack_compensation_mu)
        except RTIOUnderflow:
            self.core.break_realtime()
            aprint("underflow in feedback loop at =", self.p.t_calculation_slack_compensation_mu)

    @kernel
    def scan_kernel(self):

        aprint('\n')

        self.p.t_between_pulses_mu = self.compute_t_between_pulses_mu(
            t_calculation_slack_compensation_mu=int64(self.p.t_calculation_slack_compensation_mu),
            t_raman_pulse=self.p.t_raman_pulse,
            t_img_pulse=self.p.t_img_pulse,
            t_fifo_mu=self.p.t_fifo_mu
        )
        aprint(self.p.t_between_pulses_mu)

        self.omega_raman = self.omega_guess_start

        self.core.break_realtime()

        self.integrator.init()

        self.initialize_feedback()
        delay(10.e-3)
        
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask, verbose=False)
        self.imaging.set_power(self.p.amp_imaging)

        # self.prepare_hf_tweezers(squeeze=True)
        # self.prep_raman(frequency_transition=self.omega_raman/(2*np.pi), phase_mode=1)

        delay(10.e-3)

        t_pulse_start_mu = now_mu() + 10000000

        f = self.omega_raman/(2*np.pi)
        self.raman.set(frequency_transition=f, t_phase_origin_mu=t_pulse_start_mu)

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
        # print((self.data.omega_raman.shot_data/(2*np.pi) - self.p.frequency_raman_transition)/1.e3)
        # self.scope.read_sweep(0)
        # self.core.break_realtime()
        delay(30.e-3)

    @kernel
    def measurement(self, idx=0):
        T_CONV_MU = 80
        self.integrator.begin_integrate(reset=False)
        self.imaging.pulse(self.p.t_img_pulse)
        self.integrator.stop_and_settle()
        t = now_mu()
        # start the clear after the integrator voltage is already in the sampler
        at_mu(t + T_CONV_MU)
        self.integrator.clear(t=0)
        at_mu(t)
        self.data.apd.shot_data[idx] = self.integrator.sample()
        v = self.convert_measurement(self.data.apd.shot_data[idx+1])
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