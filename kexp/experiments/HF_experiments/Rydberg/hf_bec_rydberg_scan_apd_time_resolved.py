
import numpy as np
from artiq.experiment import *
from artiq.language.core import delay, kernel, now_mu
from kexp import Base, img_types, cameras

class hf_bec(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.DISPERSIVE)
        
        # self.xvar('t_tof',np.linspace(20.,3000.,7)*1.e-6)
        self.p.t_tof = 1700.e-6

        # self.xvar('do_405_pulse',[0,1])
        self.p.do_405_pulse = 1
        # self.xvar('do_980_pulse',[0,1])
        self.p.do_980_pulse = 1
        self.p.amp_dds_405 = .06
#   

         # self.xvar('compress',[0,1])
        self.p.compress = 0


        # self.xvar('frequency_eo_980', 366.4e6 + 1.e6 * np.linspace(-5,5,9))
        # self.xvar('frequency_eo_980', np.arange(422.,434.,0.05)*1.e6)
        # self.xvar('frequency_eo_980', np.linspace(430.,460.,40)*1.e6)
        # self.p.frequency_eo_980 = self.siglent.siglent_980._frequency_default
        # self.p.frequency_eo_980 = 352.1e6
        # self.p.frequency_eo_980 = 418.1e6

        self.xvar('frequency_eo_980', np.arange(421.5,431.5,0.075)*1.e6)
        # self.xvar('frequency_eo_980', [422.695e6,421.75e6])
        self.p.frequency_eo_980 = 422.695e6
        # self.xvar('frequency_eo_980', self.p.frequency_eo_980 + np.arange(-1.e6,1.e6,0.05e6))

        # self.xvar('t_tweezer_hold', np.linspace(0.0, 700.0, 4) * 1.e-3)
        self.p.t_tweezer_hold = 800.e-3

        # self.p.v_pd_hf_tweezer_1064_rampdown3_end=3.5

        # self.p.hf_imaging_detuning = -568.e6

        self.p.amp_imaging = 0.25*(26.5/48.7)
        self.p.t_imaging_pulse = 10.e-6

        # self.xvar('v_pd_ry_980',np.linspace(0.,1.,5))
        self.p.v_pd_ry_405 = 0.4
        self.p.v_pd_ry_980 = 2.8

        self.p.N_pulses = 6

        # self.xvar('beans',np.linspace(0,30,10))
        self.p.N_repeats = 1


        self.data.apd = self.data.add_data_container(self.p.N_pulses, float)
        self.data.t_pulse = self.data.add_data_container(self.p.N_pulses, float)
        self.data.apd_no_atoms = self.data.add_data_container(1, float)

        self.finish_prepare(shuffle=True)

        if self.p.do_405_pulse == 1:
            print(f'doing 405 pulse')
        else:
            print(f'not doing 405 pulse')
        if self.p.do_980_pulse == 1:
            print(f'doing 980 pulse')
        else:
            print(f'not doing 980 pulse')

    @kernel
    def scan_kernel(self):
        
        self.ry_405.set_power(self.p.v_pd_ry_405)
        self.ry_980.set_power(self.p.v_pd_ry_980)

        if self.p.compress:
            self.p.t_tof = 450.e-6
        if self.p.do_980_pulse == 1:
            self.ry_980.sweep_to(self.p.frequency_eo_980)

        # self.ry_980.set_power(9.9)

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        self.imaging.set_power(self.p.amp_imaging)

        if self.p.compress:
            self.prepare_hf_tweezers(squeeze=True)
        else:
            self.prepare_hf_tweezers(squeeze=False, do_tweezer_evap_3=True, do_tweezer_evap_2=True)

        # self.tweezer.ramp(t=self.p.t_tweezer_squeezer_ramp_1,
        #                         v_start=self.p.v_pd_hf_tweezer_1064_rampdown3_end,
        #                         v_end=self.p.v_pd_tweezer_squeeze_rampup_handoff_lp,
        #                         low_power=True, paint=False, keep_trap_frequency_constant=False,
        #                         cubic_ramp=self.cubic_ramp)


        if self.p.do_405_pulse == 1:
            self.ry_405.reboot()
            self.ry_405.dds_sw.set_dds(amplitude=self.p.amp_dds_405)
            self.ry_405.on()
        if self.p.do_980_pulse == 1:
            self.ry_980.on()
        
        T = self.p.t_tweezer_hold
        dt = T / self.p.N_pulses

        self.ttl.pd_scope_trig3.pulse(1.e-6)

        t = 0.
        t0 = now_mu()

        for i in range(self.p.N_pulses):
            t = (now_mu() - t0)*1.e-9
            # self.ry_405.off()
            self.integrated_imaging_pulse(self.data.apd, t=self.p.t_imaging_pulse, idx=i)
            delay(4e-6)
            # self.ry_405.on()
            self.data.t_pulse.put_data(t, i=i)
            delay(dt)

        self.ry_405.off()
        self.ry_980.off()
        self.ry_405.ttl_shutter.off()

        self.tweezer.off()
        self.outer_coil.off()

        delay(10.e-3)
        self.integrated_imaging_pulse(self.data.apd_no_atoms, t=self.p.t_imaging_pulse)

        delay(10.e-3)

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
