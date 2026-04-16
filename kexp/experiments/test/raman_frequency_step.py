from artiq.experiment import *
from artiq.language import now_mu, at_mu, delay, delay_mu
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu

class hf_raman(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)

        # self.xvar('frequency_raman_offset',[0,2*54.33e3])
        self.p.frequency_raman_offset = 1*54.33e3 
        # self.p.frequency_raman_offset = 1.e6

        # self.xvar('relative_phase',np.linspace(0., 2*np.pi, 7))
        self.p.relative_phase = 0.

        self.xvar('t',np.linspace(0.,30.,10)*1.e-6)
        self.p.t = 15.e-6
        
        self.xvar('t_raman_pulse', np.linspace(0., 1.*self.p.t_raman_pi_pulse, 11))
        self.p.t_raman_pulse = self.p.t_raman_pi_pulse # -1 --> 0
        
        self.p.amp_imaging = .5

        self.p.t_tweezer_hold = .01e-3
        self.p.t_tof = 90.e-6
        self.p.t_mot_load = 1.
        self.p.N_repeats = 1
        # self.data.phases = self.data.add_data_container(2)
        self.data.t = self.data.add_data_container(1)

        # self.camera_params.gain = 75.

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        # self.set_high_field_imaging(i_outer=self.p.i_hf_raman)
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        # self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers(squeeze=True)

        self.raman.init(frequency_transition = self.p.frequency_raman_transition, 
                        fraction_power = self.params.fraction_power_raman,
                        phase_mode = 1)
        
        self.ttl.raman_shutter.on()
        delay(10.e-3)
        self.ttl.line_trigger.wait_for_line_trigger()
        delay(4.7e-3)

        T_DELAY_TIL_PULSE_MU = 30000
        t_pulse_start = now_mu() + T_DELAY_TIL_PULSE_MU
        self.raman.set(t_phase_origin_mu = t_pulse_start,
                       relative_phase = 0.)
        
        at_mu(t_pulse_start)

        self.raman.pulse(self.p.t_raman_pi_pulse / 2)
        t=now_mu()
        
        # delay(10.e-6)
        delay(self.p.t)
        
        self.raman.set(frequency_transition = self.p.frequency_raman_transition + (self.p.frequency_raman_offset))
        

        p0 = self.raman.get_phase()
        p1 = self.raman.get_phase(frequency_transition = self.p.frequency_raman_transition + self.p.frequency_raman_offset)  

        t2=now_mu()

        self.raman.pulse(self.p.t_raman_pulse)
        

        # delay(self.p.t)
        # self.raman.set(frequency_transition = self.p.frequency_raman_transition - self.p.frequency_raman_offset)
        # self.raman.pulse(self.p.t_raman_pulse)

        self.ttl.raman_shutter.off()

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)

        self.abs_image()


        self.core.wait_until_mu(now_mu())
        delay(10.e-3)
        # print(p0,p1)
        print(t2-t)
        # self.data.phases.put_data( p0, idx = 0 )
        # self.data.phases.put_data( p1, idx = 1 )
        self.data.t.put_data((t2-t)*1e-9)
        delay(10.e-3)

    @kernel
    def run(self):
        self.init_kernel(setup_slm=True)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        
    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)