from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class mag_trap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        self.p.t_tof = 8000.e-6
        # self.xvar('t_tof',np.linspace(5.,10.,10)*1.e-3)
        
        # self.xvar('dumy',[0]*500)
        # self.xvar('dumy',np.linspace(1.,800.,800))

        # self.xvar('t_pump_to_F1',np.linspace(5.,100.,10)*1.e-6)
        # self.p.t_pump_to_F1 = 50.e-6

        # self.xvar('detune_d2v_c_2dmot',np.linspace(-4.,0.,8))
        # self.xvar('detune_d2h_c_2dmot',np.linspace(-4.,0.,8))
        # self.xvar('detune_d2v_r_2dmot',np.linspace(-7.,-2.,8))
        # self.xvar('detune_d2h_r_2dmot',np.linspace(-7.,-2.,8))
        # self.p.detune_d2_r_2dmot = -4.4
        # self.p.detune_d2_c_2dmot = -1.6

        # self.xvar('v_2d_mot_current',np.linspace(.5,4.,15))

        # self.xvar('detune_d2_c_mot',np.linspace(-5.,-2.,8))
        
        # self.xvar('detune_d2_c_mot',np.linspace(-5.5,-1.,8))
        # self.xvar('detune_d2_r_mot',np.linspace(-6.5,-3.,8))
        # self.p.detune_d2_c_mot = -3.
        # self.p.detune_d2_r_mot = -3.5
        
        # self.xvar('i_mot',np.linspace(12.,30.,20))

        # self.xvar('v_zshim_current',np.linspace(0.0,.8,8))
        # self.xvar('v_xshim_current',np.linspace(0.,2.,8))
        # self.xvar('v_yshim_current',np.linspace(0.0,2.3,8))
        # self.p.v_zshim_current = .743
        # self.p.v_xshim_current = .571
        # self.p.v_yshim_current = .11

        # self.xvar('detune_d2_c_mot',np.linspace(-5.,-1.,8))
        # self.xvar('detune_d2_r_mot',np.linspace(-6.,-2.,8))

        # self.xvar('detune_d2_r_d1cmot',np.linspace(-5.,-2.,8))
        # self.xvar('amp_d2_r_d1cmot',np.linspace(.02,.08,8))

        self.p.detune_d1_c_d1cmot = 7.5

        # self.xvar('detune_d1_c_d1cmot',np.linspace(3.,13.,8))
        # self.xvar('pfrac_d1_c_d1cmot',np.linspace(.1,.99,15))

        # self.xvar('i_mot',np.linspace(12.,30.,15))

        # self.xvar('v_zshim_current_gm',np.linspace(0.3,1.,8))
        # self.xvar('v_xshim_current_gm',np.linspace(0.,1.7,8))
        # self.xvar('v_yshim_current_gm',np.linspace(.1,3.,8))
        # self.p.v_zshim_current_gm = .743
        # self.p.v_xshim_current_gm = .571
        # self.p.v_yshim_current_gm = 2.23

        # self.xvar('detune_gm', np.linspace(3.,13.5,8))
        self.p.detune_gm = 7.5

        # self.xvar('pfrac_d1_c_gm',np.linspace(.1,.99,8))
        # self.xvar('pfrac_d1_r_gm',np.linspace(0.1,.99,8))
        # self.p.pfrac_d1_c_gm = .539
        # self.p.pfrac_d1_r_gm = .539

        # self.xvar('t_gmramp',np.linspace(2.,15.,15)*1.e-3)

        # self.xvar('pfrac_c_gmramp_end',np.linspace(0.01,.3,8))
        # self.xvar('pfrac_r_gmramp_end',np.linspace(0.2,.99,8))
        self.p.pfrac_c_gmramp_end = 0.05
        # self.p.pfrac_r_gmramp_end = 0.743
        
        # self.xvar('i_magtrap_init',np.linspace(60.,95.,20))
        # self.i_magtrap_init = 84.

        # self.xvar('v_zshim_current_magtrap',np.linspace(0.,.7,10))
        # self.xvar('v_xshim_current_magtrap',np.linspace(0.,5.,20))
        # self.xvar('v_yshim_current_magtrap',np.linspace(0.,9.9,10))
        # self.p.v_zshim_current_magtrap = .572
        # self.p.v_xshim_current_magtrap = 2.5
        # self.p.v_yshim_current_magtrap = 4.6
        # self.xvar('t_magtrap_delay',np.linspace(.5,10.,15)*1.e-3)
        # self.p.t_magtrap_delay = 5.e-3
        # self.p.t_shim_delay = .5e-3

        # self.xvar('t_magtrap_hold',np.linspace(1.,80.,8)*1.e-3)
        self.p.t_magtrap_hold = .15

        self.p.N_repeats = 1
        self.p.t_mot_load = .5

        # self.xvar('amp_imaging',np.linspace(.25,.4,20))
        # self.p.amp_imaging = .32
        self.p.imaging_state = 2.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)

        self.ttl.pd_scope_trig.pulse(1.e-6)

        self.gm(self.p.t_gm * s,detune_d1=self.p.detune_gm)
        self.gm_ramp(self.p.t_gmramp,detune_d1=self.p.detune_gm)

        # self.release()

        self.magtrap_and_load_lightsheet(do_lightsheet_ramp=False,
                                        do_magtrap_rampup=False,
                                        do_magtrap_hold=False,
                                        do_magtrap_rampdown=False)
        delay(self.p.t_magtrap_hold)
        self.inner_coil.snap_off()

        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel(init_shuttler=False)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
