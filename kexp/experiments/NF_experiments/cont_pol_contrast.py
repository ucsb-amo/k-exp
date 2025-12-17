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

        # self.xvar('v_lf_tweezer_paint_amp_max',np.linspace(-3.5,.5,8))
        self.p.v_lf_tweezer_paint_amp_max = -1.21
        
        self.xvar('v_pd_lf_tweezer_1064_rampdown2_end',np.linspace(.17,.5,5))
        self.p.v_pd_lf_tweezer_1064_rampdown2_end = .164

        # self.xvar('beans',[0,1]*1)
        self.p.beans = 1

        # self.xvar('frequency_detuned_imaging_pol_contrast',np.linspace(250.e6,420.e6,10))
        self.p.frequency_detuned_imaging_pol_contrast = 347.e6
        # self.p.frequency_detuned_imaging_pol_contrast = 222.e6

        # self.xvar('t_tof',np.linspace(100.,1000.,10)*1.e-6)
        self.p.t_tof = 1.e-6

        self.p.v_xcancel = 0.
        self.p.v_ycancel = 2.
        self.p.v_zcancel = .86

        # self.xvar('v_x_shim_pol_contrast',np.linspace(.5,9.,20))
        self.p.v_x_shim_pol_contrast = 9.

        # self.xvar('fraction_power_raman_nf',np.linspace(.1,.8,self.p.f_rf_sweep_width))
        self.p.fraction_power_raman_nf = .15

        # self.p.frequency_raman_transition_nf = 461.33e6 # 2 V X shim (v_x_shim_pol_contrast)
        self.p.frequency_raman_transition_nf = 459.87e6 # 9 V X shim (v_x_shim_pol_contrast)

        # self.xvar('t_raman_pulse',np.linspace(0.e-6,30.e-6,30))
        self.p.t_raman_pulse = 75.e-6

        # self.xvar('t_tweezer_hold',np.linspace(0.e-3,20.e-3,10))
        self.p.t_tweezer_hold = 10.e-3

        # self.xvar('v_power_imaging',np.linspace(.1,1.,10))
        self.p.v_power_imaging = .6

        self.p.hf_imaging_detuning  = 22.25e6

        self.p.t_mot_load = 1.

        self.p.imaging_state = 2
        
        self.p.N_repeats = 10

        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=False)

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        self.set_imaging_detuning(frequency_detuned = self.p.frequency_detuned_imaging_pol_contrast)
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)
        self.imaging.set_power(power_control_parameter=self.p.v_power_imaging)
        # self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask)

        self.prepare_lf_tweezers()

        # self.ttl.pd_scope_trig.pulse(1.e-6)

        self.set_shims(v_xshim_current = self.p.v_xcancel,
                       v_yshim_current= self.p.v_ycancel,
                       v_zshim_current= self.p.v_zcancel)
        
        delay(1.e-3)

        self.dac.xshim_current_control.linear_ramp(t=10.e-3,v_start=0.,v_end=9.99,n=500)
        
        self.outer_coil.snap_off()

        self.dac.xshim_current_control.linear_ramp(t=10.e-3,
                                                   v_start=9.99,
                                                   v_end=self.p.v_x_shim_pol_contrast,
                                                   n=500)
        
        delay(5.e-3)

        # self.dac.tweezer_paint_amp.linear_ramp(t=self.p.t_ramp_down_painting_amp,
        #                                        v_start=self.dac.tweezer_paint_amp.v,
        #                                        v_end=self.p.v_paint_amp_end,
        #                                        n=1000)

        self.init_raman_beams_nf(frequency_transition=self.p.frequency_raman_transition_nf,
                                 fraction_power=self.p.fraction_power_raman_nf)

        self.imaging.on()
        # self.ttl.pd_scope_trig.pulse(1.e-6)
        self.ttl.pd_scope_trig3.pulse(1.e-6)
        
        self.raman_nf.pulse(t=self.p.t_raman_pulse)
        # delay(200.e-6)

        self.imaging.off()

        self.set_imaging_detuning(frequency_detuned = self.p.hf_imaging_detuning)
        self.imaging.set_power(.321)

        delay(self.p.t_tweezer_hold)

        self.tweezer.off()

        delay(self.p.t_tof)
        # self.flash_repump()
        self.abs_image()

        self.core.wait_until_mu(now_mu())
        self.scope.read_sweep(0)
        self.core.break_realtime()
        delay(20.e-3)

    @kernel
    def run(self):
        self.init_kernel(setup_slm=True)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)