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

        self.p.v_pd_hf_tweezer_1064_rampdown2_end = 1.

        self.p.i_hf_raman = 182.

        # self.xvar('frequency_raman_transition',147.355e6 + np.linspace(-50.e3,50.e3,9))

        self.p.frequency_raman_transition = 147.2447e6 # 182. A

        # self.xvar('amp_raman',np.linspace(0.1,.35,15))
        self.p.fraction_power_raman = .99

        # self.xvar('t_raman_stateprep_pulse',[0.,9.9979e-06])
        self.p.t_raman_pi_over_2_pulse = (1.0202e-05) / 2

        self.xvar('amp_imaging',np.linspace(.3,.9,20))
        # self.p.amp_imaging = .28
        self.p.amp_imaging = .01

        self.xvar('t_ramsey',np.linspace(0.,100.e-6,25))
        self.p.t_ramsey = 10.e-6

        self.p.hf_imaging_detuning = -565.e6 # 182.
        self.p.hf_imaging_detuning_mid = -655.e6 # -635.e6
        
        self.p.phase_slm_mask = 1.54 * np.pi
        self.p.dimension_slm_mask = 20.e-6

        # self.xvar('t_raman_stateprep_pulse',[0.e-6,29.e-6]*50)

        # self.xvar('t_tweezer_hold',np.linspace(1.e-3,1.1e-3,10))
        self.p.t_tweezer_hold = 20.e-3
        self.p.t_tof = 20.e-6
        self.p.t_mot_load = 1.15

        # self.camera_params.exposure_time = 20.e-6
        # self.params.t_imaging_pulse = self.camera_params.exposure_time
        
        self.p.N_repeats = 3

        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=False)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned = self.p.hf_imaging_detuning_mid)
        # self.set_imaging_detuning(frequency_detuned = self.p.hf_imaging_detuning)
        self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers()

        self.raman.init(fraction_power=self.p.fraction_power_raman,
                        frequency_transition= self.p.frequency_raman_transition)

        self.ttl.raman_shutter.on()
        delay(10.e-3)
        self.ttl.line_trigger.wait_for_line_trigger()
        delay(5.7e-3)

        self.raman.pulse(t=self.p.t_raman_pi_over_2_pulse)

        self.imaging.on()
        self.ttl.pd_scope_trig3.pulse(1.e-6)
        delay(self.p.t_ramsey)
        self.imaging.off()

        self.raman.pulse(t=self.p.t_raman_pi_over_2_pulse)

        self.ttl.raman_shutter.off()
        
        self.set_high_field_imaging(self.p.i_hf_raman)
        self.imaging.set_power(.2,reset_pid=True)

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)

        self.abs_image()

        # self.outer_coil.stop_pid()

        # self.outer_coil.off()

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