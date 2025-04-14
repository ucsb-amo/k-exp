from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, cameras, img_types
import numpy as np

from kexp.util.artiq.async_print import aprint

class gm_tof(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select=cameras.basler_2dmot,
                      imaging_type=img_types.FLUORESCENCE)

        # self.xvar('frequency_detuned_imaging',np.arange(-150.,150.,8)*1.e6)

        # self.xvar('detune_push',np.linspace(-3.,2.,8))
        # self.xvar('amp_push',np.linspace(.05,.188,8))
        # self.p.detune_push = -.8

        # self.xvar('detune_d2_c_2dmot',np.linspace(-4.,1.5,8))
        # self.xvar('detune_d2_r_2dmot',np.linspace(-6.,-2.5,10))
        # self.p.detune_d2_r_2dmot = -4.4
        # self.p.detune_d2_c_2dmot = -1.6

        # self.xvar('detune_d2_c_mot',np.linspace(-3.,0,8))
        # self.xvar('detune_d2_r_mot',np.linspace(-5.,0,8))

        # self.xvar('amp_d2_c_2dmot',np.linspace(-6.,0.,8))
        # self.xvar('amp_d2_r_2dmot',np.linspace(.1,.188,8))

        # self.xvar('v_2d_mot_current',np.linspace(0.,5.,10))
        # self.p.v_2d_mot_current = 3.3

        # self.xvar('i_mot',np.linspace(25.,40.,10))
        # self.p.i_mot = 28.

        # self.xvar('dumdum',[0]*100)

        # self.xvar('t_tof',np.linspace(14.,20.,10)*1.e-3)
        # self.xvar('t_tof',np.linspace(200.,1500.,10)*1.e-6)

        self.camera_params.exposure_time = 250.e-3
        self.params.t_imaging_pulse = self.camera_params.exposure_time
        
        self.p.imaging_state = 2.

        self.p.t_tof = 10.e-6

        self.p.t_mot_load = .5
        self.p.N_repeats = 1

        self.camera_params.gain = 30.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        
        self.mot(self.p.t_mot_load)
        # self.dds.push.off()
        # self.cmot_d1(self.p.t_d1cmot)
        
        # self.gm(self.p.t_gm * s)
        # self.ttl.pd_scope_trig.pulse(1.e-6)
        # self.gm_ramp(self.p.t_gmramp)

        self.release()

        delay(self.p.t_tof)

        self.abs_image()

        # self.trigger_camera()
        # # delay(self.camera_params.exposure_time)
        # self.pulse_2d_mot_beams(t=self.camera_params.exposure_time)

        # delay(self.camera_params.t_light_only_image_delay)
        # self.trigger_camera()
        # delay(self.camera_params.exposure_time)

        # delay(self.camera_params.t_dark_image_delay)
        # self.trigger_camera()
        # delay(self.camera_params.exposure_time)
       
    @kernel
    def run(self):
        self.init_kernel()
        
        self.scan()

        # self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)