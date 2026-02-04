from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu

class cont_mon_182_ref(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.DISPERSIVE)

        # self.p.v_pd_hf_tweezer_1064_rampdown2_end = 1.
        
        # self.xvar('beans',[0,1]*50)

        self.p.i_hf_raman = 182.

        # self.xvar('frequency_raman_transition',147.35e6 + np.linspace(-30.e3,30.e3,9))

        # self.p.frequency_raman_transition = 145.57e6 # 191. A
        # self.p.frequency_raman_transition = 147.2447e6 # 182. A
        self.p.frequency_raman_transition = 147.245e6 # .3 img amp

        # self.xvar('amp_raman',np.linspace(0.1,.35,15))
        self.p.fraction_power_raman = .99

        # self.xvar('t_raman_stateprep_pulse',[0.,9.9979e-06])
        self.p.t_raman_pi = (1.0058e-05)
        self.p.t_raman_pi_over_two = (1.0058e-05) / 2

        # self.xvar('t_continuous_rabi',np.linspace(0.,400.e-6,10))
        self.p.t_monitor = 20.e-6
        
        self.xvar('amp_imaging',[0.1, 0.14210526, 0.18421053])
        # self.p.amp_imaging = .28
        self.p.amp_imaging = .8

        self.p.hf_imaging_detuning = -565.e6 # 182.

        # self.xvar('hf_imaging_detuning_mid',np.arange(-710.,-570.,10)*1.e6)
        # self.p.hf_imaging_detuning_mid = -690.e6 # -635.e6
        self.p.hf_imaging_detuning_mid = -650.e6 # -635.e6
        
        # self.xvar('dimension_slm_mask',np.linspace(10.e-6,100.e-6,10))
        # self.p.dimension_slm_mask = 60.e-6
        # self.xvar('phase_slm_mask',np.linspace(0.,2.7*np.pi,15))
        self.p.phase_slm_mask = .39 * np.pi
        self.p.dimension_slm_mask = 20.e-6

        # self.xvar('t_raman_stateprep_pulse',[0.e-6,29.e-6]*50)

        # self.xvar('t_tweezer_hold',np.linspace(1.e-3,1.1e-3,10))
        self.p.t_tweezer_hold = 20.e-3
        self.p.t_tof = 20.e-6
        self.p.t_mot_load = 1.15

        # self.camera_params.exposure_time = 20.e-6
        # self.params.t_imaging_pulse = self.camera_params.exposure_time
        
        self.p.N_repeats = 5

        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=False)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned = self.p.hf_imaging_detuning_mid)
        # self.set_imaging_detuning(frequency_detuned = self.p.hf_imaging_detuning)
        self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers()

        self.raman.init(fraction_power = self.p.fraction_power_raman,
                        frequency_transition = self.p.frequency_raman_transition)

        # self.ttl.raman_shutter.on()
        delay(10.e-3)
        self.ttl.line_trigger.wait_for_line_trigger()
        delay(5.7e-3)

        self.ttl.pd_scope_trig3.pulse(1.e-6)
        # self.raman.pulse(t=self.p.t_raman_pi_over_two)
        delay(self.p.t_raman_pi_over_two)

        self.imaging.on()
        delay(self.p.t_monitor)
        self.imaging.off()

        # self.raman.pulse(t=self.p.t_raman_pi)
        delay(self.p.t_raman_pi)

        self.imaging.on()
        delay(self.p.t_monitor)
        self.imaging.off()

        # self.raman.pulse(t=self.p.t_raman_pi_over_two)
        delay(self.p.t_raman_pi_over_two)

        # self.ttl.raman_shutter.off()
        
        self.set_high_field_imaging(self.p.i_hf_raman)
        self.imaging.set_power(.25,reset_pid=True)

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
        self.end(expt_filepath)