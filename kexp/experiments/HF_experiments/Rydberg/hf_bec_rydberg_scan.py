
import numpy as np
from artiq.experiment import *
from artiq.language.core import delay, kernel
from kexp import Base, img_types, cameras
from kexp.calibrations.imaging import high_field_imaging_detuning


class hf_bec(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION)
        
        # self.xvar('t_tof',np.linspace(20.,3000.,7)*1.e-6)
        self.p.t_tof = 1500.e-6

        # self.xvar('do_405_pulse',[0,1])
        self.p.do_405_pulse = 1
        # self.xvar('do_980_pulse',[0,1])
        self.p.do_980_pulse = 0
        self.p.amp_dds_405 = 0.06
#   

         # self.xvar('compress',[0,1])
        self.p.compress = 0

        # self.xvar('frequency_eo_980', np.arange(422.,424.,0.1)*1.e6)
        self.p.frequency_eo_980 = 422.1e6
        # self.xvar('frequency_eo_980', 418.1e6 + 1e6*np.linspace(-1,1,3))

        # self.xvar('t_tweezer_paint_rampdown',np.linspace(0.0,10.,5)*1.e-3)

        self.xvar('t_tweezer_hold', np.linspace(0.0, 600.0, 7) * 1.e-3)
        self.p.t_tweezer_hold = 512.e-3
        self.p.amp_imaging = .1

        # self.p.v_pd_hf_tweezer_1064_rampdown3_end=3.5
        self.p.hf_imaging_detuning = -568.e6    
        self.p.v_pd_ry_405 = 0.8
        self.p.v_pd_ry_980 = 2.8

        self.p.N_repeats = 1
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
        
        self.set_imaging_detuning(frequency_detuned=self.p.hf_imaging_detuning)
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        self.ry_405.set_power(self.p.v_pd_ry_405)
        self.ry_980.set_power(self.p.v_pd_ry_980)
        self.ttl.ry_intensity_pid_clear.pulse(10.e-6)

        if self.p.compress:
            self.p.t_tof = 450.e-6
        if self.p.do_980_pulse == 1:
            self.ry_980.sweep_to(self.p.frequency_eo_980)

        # self.ry_980.set_power(9.9)

        if self.p.compress:
            self.prepare_hf_tweezers(squeeze=True)
        else:
            self.prepare_hf_tweezers(squeeze=False, do_tweezer_evap_2=True)

        if self.p.do_405_pulse == 1:
            self.ry_405.reboot()
            self.ry_405.dds_sw.set_dds(amplitude=self.p.amp_dds_405)
            self.ry_405.on()
        if self.p.do_980_pulse == 1:
            self.ry_980.on()
        
    

        delay(self.p.t_tweezer_hold)

        self.ry_405.off()
        self.ry_980.off()
        self.ry_405.ttl_shutter.off()

        delay(40e-3)

        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

        self.outer_coil.off()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
