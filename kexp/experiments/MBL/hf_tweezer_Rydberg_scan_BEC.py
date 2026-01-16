from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp import Base, img_types, cameras


class mag_trap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION)
        
        self.p.t_tof = 100.e-6
        # self.xvar('t_tof',np.linspace(1000.,4500.,10)*1.e-6)

        # self.xvar('t_pulse',np.linspace(0.,15.,5)*1.e-3)
        self.p.t_pulse = 5.e-3
        # self.p.t_pulse = 

        # self.xvar('woo',[0,1]*1)
        self.p.woo = 0

        # self.xvar('frequency_405_cavity_ao',np.linspace(80.,86.,7)*1.e6)
        self.p.frequency_405_cavity_ao = 80.0*1.e6

        self.xvar('frequency_980_fiber_eo',np.linspace(360.,380.,7)*1e6)
        self.p.frequency_980_fiber_eo = 371.8e6

        # self.xvar('dumy',[0]*3)

        # self.xvar('t_tweezer_hold',np.linspace(1.,30.,5)*1e-3)
        self.p.t_tweezer_hold = 10.e-3

        # self.p.hf_imaging_detuning = -617.e6 # 193.2
        self.p.imaging_state = 2.

        self.p.N_repeats = 1
        self.p.t_mot_load = 1.

        self.p.amp_imaging = .25

        self.p.hf_imaging_detuning = -565.e6 # 182.

        self.p.v_pd_hf_tweezer_1064_rampdown2_end = 1.



        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        # self.ttl.raman_shutter.on()
        # self.dds.raman_80_plus.on()
        # self.dds.raman_150_plus.on()

        self.ry_405.init()
        self.ry_405.set_power(.039)
        self.ry_405.set_siglent(frequency=self.p.frequency_405_cavity_ao)

        self.ry_980.init()
        self.ry_980.set_siglent(frequency=self.p.frequency_980_fiber_eo)

        # self.set_imaging_detuning(frequency_detuned=self.p.hf_imaging_detuning)
        # self.set_high_field_imaging(i_outer=self.p.i_non_inter)
        self.set_imaging_detuning(frequency_detuned=self.p.hf_imaging_detuning)

        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers()

        delay(self.p.t_tweezer_hold)

        self.ry_980.on()

        # self.init_raman_beams_nf(frequency_transition=self.p.frequency_raman_transition_nf_1m1_20 - 10.e6,
        #                          fraction_power=1.0)
        # delay(1.e-3)
        # self.raman_nf.pulse(self.p.t_raman_pulse)
        if self.p.woo == 0:
            self.ttl.pd_scope_trig.pulse(1.e-8)
            self.ry_405.pulse(self.p.t_pulse)
        
        elif self.p.woo == 1:
            delay(self.p.t_pulse)
        # delay(1.e-3)
        
        self.ry_980.off()

        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

        self.outer_coil.off()

    @kernel
    def run(self):
        self.init_kernel(setup_slm=False)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()
        # self.ttl.raman_shutter.on()
        # self.dds.raman_80_plus.on()
        # self.dds.raman_150_plus.on()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
