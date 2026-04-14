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
                      save_data=True,
                      imaging_type=img_types.DISPERSIVE)

        # self.p.frequency_raman_transition = 147.2778e6 # .1 img amp
        self.p.frequency_raman_transition = 119801200.0 # 182 A -1 --> 0
        # self.xvar('frequency_raman_transition', 119544805.0 + np.linspace(-75.e3,75.e3,10))

        # self.xvar('t_continuous_rabi',np.linspace(0.,400.e-6,10))
        self.p.t_continuous_rabi = 300.e-6

        # self.xvar('t_raman_pulse',[0, 8.7e-06 / 2, 8.7e-06])

        # self.xvar('t_raman_pulse',np.linspace(0.,8.7e-6,7))
        self.p.t_raman_pulse = 8.8699e-6
        
        self.xvar('amp_imaging',np.linspace(2.45,3.5, 10))
        self.p.amp_imaging = 3.5

        self.p.hf_imaging_detuning = -568.e6 # 182.

        # self.xvar('hf_imaging_detuning_mid',np.arange(-680.,-610.,10)*1.e6)
        # self.xvar('hf_imaging_detuning_mid',[-670.e6,-640.e6])
        # self.p.hf_imaging_detuning_mid = -640.e6 # -635.e6
        self.p.hf_imaging_detuning_mid = -514.e6 # -1 --> 0
        
        # self.xvar('dimension_slm_mask',np.linspace(15.e-6,250.e-6,10))
        self.p.dimension_slm_mask = 20.e-6

        # self.p.phase_slm_mask = 0.371 * np.pi
        self.p.phase_slm_mask = 0.186 * np.pi

        # self.xvar('t_tweezer_hold',np.linspace(1.e-3,1.1e-3,10))
        self.p.t_tweezer_hold = 20.e-3
        self.p.t_tof = 20.e-6
        self.p.t_mot_load = 1.0
        
        self.p.N_repeats = 1

        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=False)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        
        self.set_imaging_detuning(frequency_detuned = self.p.hf_imaging_detuning_mid)
        # self.set_imaging_detuning(frequency_detuned = self.p.hf_imaging_detuning)
        self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask,dimension=self.p.dimension_slm_mask)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers(squeeze=True)

        self.raman.init(fraction_power = self.p.fraction_power_raman,
                        frequency_transition = self.p.frequency_raman_transition)

        self.ttl.raman_shutter.on()
        delay(10.e-3)
        self.ttl.line_trigger.wait_for_line_trigger()
        delay(4.7e-3)

        # self.raman.pulse(t=self.p.t_raman_pi_pulse)
        
        self.ttl.pd_scope_trig3.pulse(1.e-6)
        self.imaging.on()
        # delay(3.e-6)
        # self.raman.pulse(t=self.p.t_continuous_rabi)
        delay(self.p.t_continuous_rabi)
        self.imaging.off()

        self.ttl.raman_shutter.off()
        
        self.set_imaging_detuning(frequency_detuned = self.p.hf_imaging_detuning)
        self.imaging.set_power(.2,reset_pid=True)

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)

        self.abs_image()

        self.core.wait_until_mu(now_mu())
        self.scope.read_sweep(0)
        self.core.break_realtime()
        delay(30.e-3)

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