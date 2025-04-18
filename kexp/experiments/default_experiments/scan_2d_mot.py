
import numpy as np

from kexp.util.artiq.async_print import aprint

from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, cameras, img_types

class gm_tof(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select=cameras.xy_basler,
                      imaging_type=img_types.ABSORPTION)

        # self.xvar('frequency_detuned_imaging',np.arange(-150.,150.,8)*1.e6)

        # self.xvar('detune_push',np.linspace(-4.,1.,8))
        # self.xvar('amp_push',np.linspace(.05,.188,8))
        # self.p.detune_push = -.8

        self.xvar('detune_d2v_r_2dmot',np.linspace(-7.,-3.,8))
        self.xvar('detune_d2v_c_2dmot',np.linspace(-4.5,0.,8))
        # self.xvar('detune_d2h_r_2dmot',np.linspace(-10.,-5.,8))
        # self.xvar('detune_d2h_c_2dmot',np.linspace(-4.,0.,8))
       
        # self.p.detune_d2v_r_2dmot = -4.1 
        # self.p.detune_d2v_c_2dmot = -2.5 
        # self.p.detune_d2h_r_2dmot = -6.4 
        # self.p.detune_d2h_c_2dmot = -1.7 

        # self.xvar('detune_d2_c_mot',np.linspace(-3.,0,8))
        # self.xvar('detune_d2_r_mot',np.linspace(-5.,0,8))

        # self.xvar('amp_d2v_r_2dmot',np.linspace(.0,.188,8))
        # self.xvar('amp_d2v_c_2dmot',np.linspace(.0,.188,8))
        # self.xvar('amp_d2h_r_2dmot',np.linspace(.0,.188,8))
        # self.xvar('amp_d2h_c_2dmot',np.linspace(.0,.188,8))
        # self.p.amp_d2v_r_2dmot = 0.161
        # self.p.amp_d2v_c_2dmot = 0.161
        # self.p.amp_d2h_r_2dmot = 0.134
        # self.p.amp_d2h_c_2dmot = 0.134

        
        # self.xvar('v_2d_mot_current',np.linspace(.1,5.,20))
        # self.p.v_2d_mot_current = 2.7

        # self.xvar('i_mot',np.linspace(25.,40.,10))
        # self.p.i_mot = 21.5

        # self.xvar('dumdum',[0]*100)

        # self.xvar('t_tof',np.linspace(14.,20.,10)*1.e-3)
        # self.xvar('t_tof',np.linspace(200.,1500.,10)*1.e-6)

        # self.camera_params.exposure_time = 5.e-3
        # self.params.t_imaging_pulse = self.camera_params.exposure_time
        # self.camera_params.gain = 40.
        
        self.p.imaging_state = 2.
        self.p.amp_imaging = .35

        self.p.t_tof = 300.e-6

        self.p.t_mot_load = .3
        self.p.N_repeats = 1

        

        # self.p.detune_d2_2d_c_imaging = 0.
        # self.p.detune_d2_2d_r_imaging = 0.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        # self.cmot_d1(self.p.t_d1cmot)
        
        # self.gm(self.p.t_gm * s)
        # self.ttl.pd_scope_trig.pulse(1.e-6)
        # self.gm_ramp(self.p.t_gmramp)

        self.release()

        self.switch_d2_2d(0)
        # self.dac.supply_current_2dmot.set(v=0.)

        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()
       
    @kernel
    def run(self):
        self.init_kernel(setup_awg=False)
        
        self.scan()

        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)