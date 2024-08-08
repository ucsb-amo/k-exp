from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class mag_trap(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        # self.xvar('t_magtrap_hold',np.linspace(1.,100.,15)*1.e-3)

        self.p.N_repeats = [5]
        self.p.imaging_state = 2.
        # self.xvar('frequency_detuned_imaging',np.linspace(11.,21.,10)*1.e6)

        self.p.t_magtrap_hold = 100.e-3
        self.xvar('t_tof',np.linspace(4.,12.,15)*1.e-3)
        # self.xvar('i_magtrap_init',np.linspace(20.,34.,8))
        # self.xvar('i_magtrap_ramp_start',np.linspace(28.,95.,8))
        # self.xvar('t_magtrap',np.linspace(0.,20.,8)*1.e-3)
        # self.xvar('v_zshim_current_magtrap',np.linspace(0.,8.,20))

        # self.p.detune_push = -4.17116726
        # self.p.amp_push = 0.16738739
        # self.p.detune_d2_c_2dmot = -1.73040681
        # self.p.detune_d2_r_2dmot = -3.08733172
        # self.p.amp_d2_c_2dmot = 0.2
        # self.p.amp_d2_r_2dmot = 0.17571287
        # self.p.v_2d_mot_current = 2.11158112
        # self.p.detune_d2_c_mot = -2.37056453
        # self.p.detune_d2_r_mot = -3.94081539
        # self.p.amp_d2_c_mot = 0.2
        # self.p.amp_d2_r_mot = 0.15113752
        # self.p.i_mot = 22.75847018

        self.p.t_tof = 8.e-3

        self.finish_build(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        # self.release()
        self.switch_d2_3d(0)
        self.switch_d1_3d(0)

        self.flash_cooler()

        self.dds.power_down_cooling()

        self.set_shims(v_zshim_current=self.p.v_zshim_current_magtrap,
                        v_yshim_current=self.p.v_yshim_current_magtrap,
                          v_xshim_current=self.p.v_xshim_current_magtrap)

        # magtrap start
        self.ttl.pd_scope_trig.pulse(t=1.e-6)
        self.inner_coil.on()

        self.inner_coil.ramp(t=self.p.t_magtrap_ramp,
                             i_start=self.p.i_magtrap_init,
                             i_end=self.p.i_magtrap_ramp_end)

        delay(self.p.t_magtrap_hold)

        self.inner_coil.off()

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
