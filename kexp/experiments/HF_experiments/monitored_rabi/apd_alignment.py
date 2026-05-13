from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu
from kexp.util.artiq.async_print import aprint

class hf_monitored_rabi(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=False,
                      imaging_type=img_types.DISPERSIVE)
        
        self.p.v_pd_hf_tweezer_1064_rampdown2_end = .5

        self.p.frequency_raman_transition = 119.4639e6 + 32.57e3 # 182 A -1 --> 0 + .2 img amp lightshift

        # self.xvar('t_continuous_rabi',np.linspace(0.,400.e-6,10))
        self.p.t_continuous_rabi = 300.e-6

        # self.xvar('t_raman_pulse',np.linspace(0.,8.7e-6,7))
        # self.xvar('t_raman_pulse',[0.0, (8.8699e-6) / 2, 8.8699e-6])
        self.p.t_raman_pulse = 8.8699e-6
        
        # self.xvar('amp_imaging',np.linspace(.2,1.5, 10))
        self.p.amp_imaging = .2

        self.p.hf_imaging_detuning = -568.e6 # 182.

        self.p.hf_imaging_detuning_mid = -514.e6 # -1 --> 0
        
        self.p.dimension_slm_mask = 20.e-6

        self.p.phase_slm_mask = 0.186 * np.pi

        self.p.t_tweezer_hold = 20.e-3
        self.p.t_tof = 20.e-6
        self.p.t_mot_load = 1.0
        
        self.p.N_repeats = 100

        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=False)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        
        self.set_imaging_detuning(frequency_detuned = self.p.hf_imaging_detuning_mid)
        # self.set_imaging_detuning(frequency_detuned = self.p.hf_imaging_detuning)
        self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask,dimension=self.p.dimension_slm_mask)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers(squeeze=False)

        self.raman.init(fraction_power = self.p.fraction_power_raman,
                        frequency_transition = self.p.frequency_raman_transition)

        self.ttl.raman_shutter.on()
        delay(10.e-3)
        self.ttl.line_trigger.wait_for_line_trigger()
        delay(4.7e-3)
        
        self.ttl.pd_scope_trig3.pulse(1.e-6)
        self.imaging.on()
        delay(3.e-6)
        
        self.raman.pulse(t=self.p.t_continuous_rabi)

        self.imaging.off()

        self.ttl.raman_shutter.off()
        
        self.set_imaging_detuning(frequency_detuned = self.p.hf_imaging_detuning)
        self.imaging.set_power(.5,reset_pid=True)

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)

        self.abs_image()

        # self.core.wait_until_mu(now_mu())
        # self.scope.read_sweep(0)
        # self.core.break_realtime()
        # delay(30.e-3)

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        # aprint(self.scope._data)
        self.end(expt_filepath)