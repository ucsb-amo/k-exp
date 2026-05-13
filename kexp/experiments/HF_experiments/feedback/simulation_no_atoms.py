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

        self.p.t_raman_pulse = self.p.t_raman_pi_pulse / 3
        # self.p.t_raman_pulse_ideal = self.p.t_raman_pulse + 200.e-9
        self.p.t_raman_pulse_ideal = self.p.t_raman_pulse + 300.e-9

        self.p.back_action_coherence = 1.0
        #self.xvar('back_action_coherence', np.linspace(.5,1.,7))

        self.p.amp_imaging = 0.2
        self.p.t_img_pulse = 5.e-6
        self.p.frequency_lightshift = 3.48e+04  # Hz, for imaging amp 0.2
        # self.p.frequency_lightshift = 0.  # Hz, for imaging amp 0.2
    
        # self.xvar('frequency_lightshift', self.p.frequency_lightshift + self.p.frequency_lightshift*np.linspace(-3.,3,7))

        # self.xvar('frequency_lightshift', self.p.frequency_lightshift * np.linspace(.7,1.3,5))
        self.p.v_apd_all_up = -0.151840625
        self.p.v_apd_all_down = -0.2231875

        # self.p.amp_imaging = 0.2
        # self.p.t_img_pulse = 10.e-6
        # self.p.frequency_lightshift = 1.2*33.34e3
        # # self.xvar('frequency_lightshift', self.p.frequency_lightshift * np.linspace(.7,1.3,5))
        # self.p.v_apd_all_up = -0.076790625
        # self.p.v_apd_all_down = -0.22614375
        
        self.p.n_photons_per_shot = 800
        self.p.n_std_photons_per_shot = 50

        Omega = np.pi / self.p.t_raman_pi_pulse

        self.p.phase_offset = 0.0#0.55 #- 0.7/Omega
        # self.xvar('phase_offset', np.linspace(-0.9, -0.5, 10)/Omega)

        self.p.delta_t_mu = int64(104)
        #self.xvar('delta_t_mu', np.linspace(0,10000,7).astype(int64))

        

        self.p.intermediate_detuning = 2*np.pi*self.p.frequency_raman_transition + 2*Omega*0
        self.xvar('intermediate_detuning',  2*np.pi*self.p.frequency_raman_transition + Omega*(np.linspace(10, 11, 20)))

        detuning_list = np.array([10., 0., 0., 0, 0,
        0.,  0.,  0.,  0.,  0.,
        0., -0., -0. ,  0. , -0.])
        # detuning_list = 3*(np.random.random(15) -0.5)

        # rand_list = np.array([-0.654877,   0.30609096,  0.38354877,  0.18202263,  0.29501175,
        #     -0.31005943,  0.38354877,  0.30609096,  0.11595314,  0.18202263,
        #         0.35998194, -0.26850061, -0.0969936 ,  0.3203508 , -0.00077061]) * 2
        # detuning_list = rand_list

        self.p.omega_pulse_list = 2*np.pi*self.p.frequency_raman_transition + (Omega * detuning_list)
        #self.xvar('omega_pulse_list', 5+np.linspace(0, 2, 10))

        self.p.feedback_fractional_initial_offset = 0.

        self.p.update_raman_frequency_bool = 0
    
        self.p.include_photon_noise = 1

        self.p.N_repeats = 1
        
        self.p.feedback_grid_size = 3 # feedback grid size
        # self.p.N_pulses = 15 # number of steps of evolution
        self.p.N_pulses = 11 # number of steps of evolution

        self.p.feedback_fractional_grid_center_offset = 2.0

        self.p.t_tweezer_hold = 30.e-3

        self.p.feedback_guess_span_Omega = 5.0

        ###

        # timing docs: https://docs.google.com/document/d/11tzbmMhPQ-lycEPc1OWHo9MnWyrR9bsQly9bz8DF_WQ/edit?tab=t.cvj0bnjp2og4#heading=h.pimm1a640bup
        self.p.t_calculation_slack_compensation_mu = int64(0.61 * self.p.feedback_grid_size * 1.e3) + 30000 if self.p.feedback_grid_size > 10 else int64(10000)
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
        self.data.omega_raman = self.data.add_data_container(self.p.N_pulses)
        self.data.Omega = self.data.add_data_container(self.p.N_pulses)
        self.data.apd = self.data.add_data_container(self.p.N_pulses)

        self.data.s_z = self.data.add_data_container(self.p.N_pulses)
        self.data.t = self.data.add_data_container(self.p.N_pulses)

        Feedback.__init__(self)
        
        self.zidx = np.argmin(abs(self.omega_guess_list - self.p.frequency_raman_transition * 2*np.pi))

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

            # self.omega_raman = self.p.omega_pulse_list[i] 

            if i == 2:
                self.omega_raman = self.p.intermediate_detuning
                omega_prev = self.p.omega_pulse_list[1]
            elif i == 3:
                self.omega_raman = self.p.omega_pulse_list[3] 
                omega_prev = self.p.intermediate_detuning
            else:
                self.omega_raman = self.p.omega_pulse_list[i] 
                omega_prev = self.p.omega_pulse_list[i-1] if i > 0 else 0.
            #     #pass
            
            f = self.omega_raman / (2*np.pi)
            self.data.omega_raman.shot_data[i] = self.omega_raman
            # self.data.Omega.shot_data[i+1] = var

            #if i > 0:
            at_mu(t_step - self.p.t_raman_set_pretrigger_mu)
            self.raman.set_frequency_fast(f)

            t = (t_step - t_start_mu)*1.e-9
            at_mu(t_step)                                                                                                                           

            # phi_pow = self.raman.get_phase()

            phase_tracker += ((tP - tR + dt) * omega_prev + (tR - dt) * self.omega_raman) * 1.e-9

            # phase_tracker += ((tP * 1e-9) * omega_prev) 

            # phase_tracker += ( (self.p.t_between_pulses_mu - self.p.delta_t_mu) * omega_prev \
            #                     + self.p.delta_t_mu * self.omega_raman ) * 1.e-9 # + self.p.phase_offset
            phi = phase_tracker

            self.raman.pulse(self.p.t_raman_pulse)

            k = self.measurement(i)

            # self.phi[i] = phi
            # self.phi_pow[i] = self.raman.pow_to_phase(phi_pow)

            # omega_prev = self.omega_raman

            self.omega_raman, self.Omega = self.generate_posterior(k, t,
                                                    phase_raman_pulse_start=phi,
                                                    update_raman_frequency=update_raman_frequency,
                                                    update_rabi_frequency=update_rabi_frequency,
                                                    include_photon_noise=include_photon_noise)

            # aprint( (phi_pow - self._phase ) & int32(0xffff))
            # self._phase = phi_pow

            t_step += self.p.t_between_pulses_mu
            # phase_tracker = phase_tracker + t_step * self.omega_raman

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

        self.prep_raman(frequency_transition=self.omega_raman/(2*np.pi),
                        phase_mode=0)

        t_pulse_start_mu = now_mu() + 100000

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
        
        # print((self.phi  - self.phi[0]) % (2*np.pi))
        # print((self.phi_pow - self.phi_pow[0]) % (2*np.pi))