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

        self.p.t_tof = 5000.e-6
        # self.xvar('t_tof',np.linspace(2.,20.,10)*1.e-3)
        # self.xvar('t_tof',np.linspace(5.,10.,10)*1.e-3)
        
        self.xvar('dumy',[0]*1000)

        # self.xvar('t_pump_to_F1',np.linspace(5.,100.,10)*1.e-6)
        # self.p.t_pump_to_F1 = 50.e-6
        
        # self.xvar('detune_d2_c_mot',np.linspace(-7.,-2.,10))
        # self.xvar('detune_d2_r_mot',np.linspace(-8.,-2.,10))
        self.detune_d2_r_mot = -6.0
        self.detune_d2_c_mot = -3.11

        # self.xvar('detune_d1_c_d1cmot',np.linspace(5.,13.,10))
        # self.xvar('pfrac_d1_c_d1cmot',np.linspace(0.,.99,8))
        self.pfrac_d1_c_d1cmot = 0.57
        self.detune_d1_c_d1mot = 12.1
        
        # self.xvar('amp_d2_c_mot',np.linspace(.05,.188,8))
        # self.xvar('amp_d2_r_mot',np.linspace(.05,.188,8))

        # self.xvar('pfrac_d1_c_gm',np.linspace(0.6,.99,10)) # optimize GM
        # self.xvar('pfrac_d1_r_gm',np.linspace(0.6,.99,10)) # optimize GM
        # self.p.pfrac_d1_c_gm = 0.687
        # self.p.pfrac_d1_r_gm = 0.64

        # self.xvar('v_zshim_current_magtrap',np.linspace(0.,2.,10))
        # self.xvar('v_xshim_current_magtrap',np.linspace(0.,5.,8))
        # self.xvar('v_yshim_current_magtrap',np.linspace(0.,9.,8))
        # self.xvar('v_xshim_current_gm',np.linspace(0.,2.,10)) # GM
        # self.xvar('v_yshim_current_gm',np.linspace(0.,9.,10)) # GM
        # self.xvar('v_zshim_current',np.linspace(0.,.8,10))
        # self.xvar('v_xshim_current',np.linspace(0.,2.,10))
        # self.p.v_xshim_current_gm = 1.1
        # self.p.v_zshim_current = 0.8
        # self.p.v_xshim_current = 0.
        # self.p.v_xshim_current_magtrap = 0.55
        # self.p.v_yshim_current_magtrap = 9.
        # self.p.v_yshim_current_magtrap = 5.
        # self.xvar('t_magtrap_delay',np.linspace(0.05,10.,20)*1.e-3)
        # self.p.t_magtrap_delay = 1.e-3
        # self.p.t_shim_delay = .5e-3

        # self.xvar('t_magtrap_hold',np.linspace(5.,50.,8)*1.e-3)
        self.p.t_magtrap_hold = .1

        self.p.N_repeats = 3
        self.p.t_mot_load = .5

        # self.p.amp_imaging = .35
        self.p.imaging_state = 2.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.magtrap_and_load_lightsheet(do_lightsheet_ramp=False,
                                        do_magtrap_rampup=False,
                                        do_magtrap_rampdown=False,
                                        do_magtrap_hold=False)
        delay(self.p.t_magtrap_hold)
        self.inner_coil.snap_off()

        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()

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
