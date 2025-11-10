from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)

        # self.xvar('frequency_detuned_imaging',np.arange(280.,300.,1)*1.e6)
        self.xvar('beans',[0,1]*50)

        # self.xvar('hf_imaging_detuning', [340.e6,420.e6]*1)

        # self.camera_params.exposure_time = 20.e-6
        # self.params.t_imaging_pulse = self.camera_params.exposure_time

        # self.p.beans = 1

        # self.xvar('v_lf_tweezer_paint_amp_max',np.linspace(-4.,2.,15))
        # self.p.v_lf_tweezer_paint_amp_max = -1.43

        # self.xvar('i_lf_tweezer_load_current',np.linspace(12.5,16.,20))

        # self.xvar('v_pd_lf_tweezer_1064_rampdown2_end',np.linspace(.05,.2,15))
        # self.p.v_pd_lf_tweezer_1064_rampdown2_end = .13

        # self.xvar('v_paint_amp_end',np.linspace(-6.5,-4.,10))

        # self.xvar('v_pd_lf_lightsheet_rampdown_end',np.linspace(.25,1.5,10))

        # self.xvar('t_tof',np.linspace(2.,500.,20)*1.e-6)
        self.p.t_tof = 50.e-6

        # self.p.t_raman_sweep = 1.e-3
        # self.p.frequency_raman_sweep_center = 41.225e6
        # self.p.frequency_raman_sweep_width = 10.e3
        # self.xvar('frequency_raman_sweep_center', 41.225e6 + np.arange(-60.e3,60.e3,self.p.frequency_raman_sweep_width))

        # self.xvar('frequency_raman_transition',41.1*1e6 + np.linspace(-5.e5,5.e5,10))
        self.p.frequency_raman_transition = 41.25e6

        # self.xvar('amp_raman',np.linspace(0.1,.35,15))
        self.p.amp_raman = 0.35

        # self.xvar('t_raman_pulse',np.linspace(0.,50.e-6,20))
        # self.xvar('t_raman_pulse',[12.e-6,24.e-6])
        # self.p.t_raman_pulse = 12.e-6
        self.p.t_raman_pulse = 23.6e-6

        # self.xvar('_t_tweezer_kill',np.linspace(0., 100.e-3,10))
        # self.p._t_tweezer_kill = 10.e-3
        
        # self.xvar('t_tweezer_hold',np.linspace(0.,1.5,10)*1.e-3)
        self.p.t_tweezer_hold = .01e-3

        self.p.amp_imaging = .35
        # self.xvar('amp_imaging',np.linspace(0.15,.5,15))

        # self.xvar('frequency_detuned_imaging',np.arange(590.,630.,4)*1.e6)
        
        # self.xvar('dimension_slm_mask',np.linspace(0.,200.e-6,10))
        # self.p.dimension_slm_mask = 50.e-6
        # self.xvar('phase_slm_mask',np.linspace(0.,np.pi,10))
        # self.xvar('px_slm_phase_mask_position_x',1147 + np.linspace(-10.,10.,5,dtype=int))
        # self.p.px_slm_phase_mask_position_x
        self.p.phase_slm_mask = 0.22 * np.pi
        self.p.t_mot_load = 1.

        # self.sampler.gains = np.array([1,0,0,0,0,0,0,0])
        
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        self.set_imaging_detuning(frequency_detuned = self.p.frequency_detuned_imaging_m1)
        # self.set_imaging_detuning(frequency_detuned = self.p.frequency_detuned_imaging_midpoint)
        # self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask)
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        # self.sampler.init()
        # self.sampler.set_gain_mu(0,2)
        # delay(10.e-3)

        self.prepare_lf_tweezers()

        # self.init_raman_beams(self.p.frequency_raman_transition,self.p.amp_raman)
        # self.ttl.line_trigger.wait_for_line_trigger()

        # delay(5.7e-3)

        
        # self.raman.pulse(t=self.p.t_raman_pulse)
        # delay(self.p.t_raman_pulse)

        # self.raman.sweep(t=self.p.t_raman_sweep,
        #                  frequency_center=self.p.frequency_raman_sweep_center,
        #                  frequency_sweep_fullwidth=self.p.frequency_raman_sweep_width,
        #                  n_steps=50)

        # delay(self.p.t_raman_pulse)

        delay(self.p.t_tweezer_hold)

        
        self.tweezer.off()

        if self.p.beans:
            delay(self.p.t_tof)
        else:
            delay(10.e-3)

        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel(setup_slm=False)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)