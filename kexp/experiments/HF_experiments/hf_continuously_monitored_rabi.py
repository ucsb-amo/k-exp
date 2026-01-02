from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)

        # self.xvar('amp_raman',np.linspace(0.1,.35,15))
        self.params.fraction_power_raman = 1.
        # self.xvar('t_raman_stateprep_pulse',np.linspace(0.,29.e-6,10))
        
        # self.xvar('beans',[0,1]*50)
        self.p.t_raman_stateprep_pulse = 13.e-6

        self.p.frequency_raman_transition = 147.18e6 # 147.18e6

        self.p.t_raman_stateprep_pulse = 0.
        # self.xvar('t_continuous_rabi',np.linspace(0.,400.e-6,10))
        self.p.t_continuous_rabi = 200.e-6
        
        self.xvar('amp_imaging',np.linspace(0.01,.25,15))
        # self.p.amp_imaging = .28
        self.p.amp_imaging = .18

        self.p.hf_imaging_detuning = -565.e6 # 182. -1

        # self.xvar('hf_imaging_detuning_mid',np.arange(-690.,-590.,10)*1.e6)
        self.p.hf_imaging_detuning_mid = -650.e6# -635.e6
        
        # self.xvar('dimension_slm_mask',np.linspace(10.e-6,200.e-6,10))
        # self.p.dimension_slm_mask = 50.e-6
        # self.xvar('phase_slm_mask',znp.linspace(0.,2.7*np.pi,10))
        self.p.phase_slm_mask = .6 * np.pi
        self.p.dimension_slm_mask = 100.e-6

        # self.xvar('t_raman_stateprep_pulse',[0.e-6,29.e-6]*50)

        # self.xvar('t_tweezer_hold',np.linspace(1.e-3,1.1e-3,10))
        self.p.t_tweezer_hold = 50.e-3
        self.p.t_tof = 100.e-6
        self.p.t_mot_load = 1.

        # self.camera_params.exposure_time = 20.e-6
        # self.params.t_imaging_pulse = self.camera_params.exposure_time
        
        self.p.N_repeats = 3

        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=False)

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned = self.p.hf_imaging_detuning_mid)
        # self.set_imaging_detuning(frequency_detuned = self.p.hf_imaging_detuning)
        # self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask)
        self.imaging.set_power(self.p.amp_imaging,reset_pid=True)

        self.prepare_hf_tweezers()

        # self.init_raman_beams()

        # self.ttl.line_trigger.wait_for_line_trigger()
        # delay(5.7e-3)

        # self.raman.pulse(t=self.p.t_raman_stateprep_pulse)

        self.imaging.on()
        # self.raman.on()
        # self.ttl.pd_scope_trig.pulse(1.e-6)
        delay(self.p.t_continuous_rabi)
        # self.raman.off()
        self.imaging.off()
        
        self.set_imaging_detuning(frequency_detuned = self.p.hf_imaging_detuning)
        self.imaging.set_power(.078,reset_pid=True)

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)

        self.abs_image()

        self.outer_coil.stop_pid()

        self.outer_coil.off()

        # self.core.wait_until_mu(now_mu())
        # self.scope.read_sweep(0)
        # self.core.break_realtime()
        delay(20.e-3)

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