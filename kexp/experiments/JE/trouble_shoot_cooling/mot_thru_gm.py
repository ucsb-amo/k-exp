from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class gm_tof(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        # self.xvar('frequency_detuned_imaging',np.arange(440.,480.,3)*1.e6)

        # self.xvar('detune_push',np.linspace(-5.,2.,20))
        # self.xvar('amp_push',np.linspace(.05,.188,8))
        # self.p.detune_push = 0.

        # self.xvar('detune_d2_c_2dmot',np.linspace(-4.,0.,8))
        # self.xvar('detune_d2_r_2dmot',np.linspace(-6.,-1.,8))
        # self.p.detune_d2_r_2dmot = -4.4
        # self.p.detune_d2_c_2dmot = -1.6

        # self.xvar('amp_d2_c_2dmot',np.linspace(-6.,0.,8))
        # self.xvar('amp_d2_r_2dmot',np.linspace(.1,.188,8))

        # self.xvar('detune_d2_c_mot',np.linspace(-6.,-.5,8))
        # self.xvar('detune_d2_r_mot',np.linspace(-7.,-2.,8))
        # self.p.detune_d2_r_mot = -4.2
        # self.p.detune_d2_c_mot = -2.07

        # self.xvar('v_2d_mot_current',np.linspace(0.,5.,10))
        # self.p.v_2d_mot_current = 3.3

        # self.xvar('i_mot',np.linspace(10.,35.,20))
        # self.xvar('i_mot',[10.,15.,18.,20.,23.,30.,60.,70.]*5)
        # self.p.i_mot = 16.

        # self.xvar('v_zshim_current',np.linspace(0.1,1.3,8))
        # self.xvar('v_xshim_current',np.linspace(0.,2.,8))
        # self.xvar('v_yshim_current',np.linspace(0.,4.,8))
        # self.p.v_zshim_current = .271
        # self.p.v_xshim_current = 1.1
        # self.p.v_yshim_current = .5

        # self.xvar('detune_d1_c_d1cmot',np.linspace(5.,13.,15))
        # self.xvar('detune_d2_r_d1cmot',np.linspace(-5.,0.,8))

        # self.xvar('pfrac_d1_c_d1cmot',np.linspace(0.3,.99,8))
        # self.xvar('amp_d2_r_d1cmot',np.linspace(0.02,.08,8))

        # self.xvar('i_cmot',np.linspace(15.,35.,30))
        # self.p.i_cmot = 29.

        # self.xvar('detune_d1_c_gm',np.linspace(2.,12.,8))
        # self.xvar('detune_d1_r_gm',np.linspace(2.,12.,8))
        # self.xvar('detune_d1_gm',np.linspace(5.,13.5,15))
        # self.p.detune_d1_gm = 11.2

        # self.p.detune_d1_c_gm = 13.
        # self.p.detune_d1_r_gm = 13.

        # self.xvar('pfrac_d1_c_gm',np.linspace(.0,.99,8))
        # self.xvar('pfrac_d1_r_gm',np.linspace(0.0,.99,8))
        # self.p.pfrac_d1_c_gm = .85
        # self.p.pfrac_d1_r_gm = .85

        # self.xvar('v_zshim_current_gm',np.linspace(0.1,1.,8))
        # self.xvar('v_xshim_current_gm',np.linspace(0.,1.,8))
        # self.xvar('v_yshim_current_gm',np.linspace(0.,5.,8))

        # self.p.v_zshim_current_gm = 0.871
        # self.p.v_xshim_current_gm = 0.429
        # self.p.v_yshim_current_gm = 2.143

        # self.xvar('pfrac_c_gmramp_end',np.linspace(.05,.6,8))
        # self.xvar('pfrac_r_gmramp_end',np.linspace(0.05,.6,8))

        # self.p.pfrac_c_gmramp_end = 0.207
        # self.p.pfrac_r_gmramp_end = 0.207

        # self.xvar('dumdum',[0]*5)
        self.xvar('dumy',np.linspace(1.,800.,800))

        # self.xvar('t_pump_to_F1',np.linspace(.1,150.,20)*1.e-6)
        # self.p.t_pump_to_F1 = .01e-6

        # self.xvar('t_tof',np.linspace(50.,500.,10)*1.e-6)

        # self.camera_params.exposure_time = 50.e-6
        # self.params.t_imaging_pulse = self.camera_params.exposure_time
        # self.camera_params.gain = 1.

        # self.xvar('amp_imaging',np.linspace(0.1,.4,15))
        # self.p.amp_imaging = .35
        # self.p.imaging_state = 1.
        self.p.imaging_state = 2.
        self.p.t_tof = 15000.e-6
        self.p.t_mot_load = .5
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)
        # self.set_imaging_detuning(self.p.frequency_detuned_imaging)
        
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot)
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.release()

        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()
       
    @kernel
    def run(self):
        self.init_kernel(setup_awg=False)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)