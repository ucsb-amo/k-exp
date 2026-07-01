from artiq.language import now_mu, delay, delay_mu, TFloat, TArray, TTuple, at_mu, parallel
import numpy as np
rng = np.random.default_rng()
from artiq.experiment import *
from artiq.language.core import delay, kernel
from kexp import Base, img_types, cameras


class hf_bec(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=False,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION)

        self.p.t_tweezer_hold = 10.e-3

        self.p.t_raman_pulse = self.p.t_raman_pi_pulse / 3
        self.p.t_weak_measure = 5.e-6
        self.p.t_strong_measure = 15.e-6
        self.p.raman_phase_list = rng.uniform(low=0,high=2*np.pi,size=(self.p.samples, self.p.N_pulses))
        self.p.N_pulses = 10

        self.p.amp_imaging = .2

        self.p.samples = 100
        self.p.sample_index = 0



        self.xvar('do_weak_measurement',[0,1])
        self.xvar('sample_index', np.arange(self.p.samples))

        self.p.N_repeats = 1

        self.data.strong_measurement = self.data.add_data_container(1)

        self.p.t_mot_load = 1.0

        self.finish_prepare(shuffle=True)

    @kernel
    def pulse_and_measure(self,t_weak_measure,
                            t_strong_measure,
                            weak_measure = True):
        
        for i in range(self.p.N_pulses):

            self.raman.pulse(self.p.t_raman_pulse)

            if self.p.do_weak_measure:
                self.imaging.on()
                delay(t_weak_measure)
                self.imaging.off()
            else:
                delay(t_weak_measure)
            
            self.raman.set(relative_phase=self.p.raman_phase_list[self.p.sample_index, i])

        self.strong_measurement(t_measure=t_strong_measure)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        self.imaging.set_power(self.camera_params.amp_imaging)
        self.prepare_hf_tweezers(ramp_down_painting=True,squeeze=False)

        self.prep_raman()

        self.pulse_and_measure(t_weak_measure=self.p.t_weak_measure,
                               t_strong_measure=self.p.t_strong_measure)
        
        delay(self.p.t_tweezer_hold)
        
        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

        self.outer_coil.off()

    @kernel
    def strong_measurement(self, t_measure):
        T_CONV_MU = 80
        self.integrator.begin_integrate(reset=False)
        self.imaging.pulse(t_measure)
        self.integrator.stop_and_settle()

        t0 = now_mu()
        self.raman.stage_ffua()

        # start the clear after the integrator voltage is already in the sampler
        at_mu(t0 + T_CONV_MU)
        self.integrator.clear(t=0)
        at_mu(t0)
        self.data.apd.shot_data[0] = self.integrator.sample()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)

