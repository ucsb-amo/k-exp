from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class pumping_flash_calibration(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        # self.xvar('t_tof',np.linspace(2.,10.,5)*1.e-3)
        # self.xvar("imaging_state", [1,2])
        self.p.imaging_state = 2.

        # self.xvar('do_pumping',[0,1])
        self.p.do_pumping = 1.

        # self.xvar('after_tof_bool',[0,1])
        self.p.after_tof_bool = 1.

        self.p.t_tof = 8.e-3
        self.p.t_mot_load = .1

        # self.xvar('detune_optical_pumping_r_op',np.linspace(-2.,2.,10))
        # self.xvar('amp_optical_pumping_r_op',np.linspace(0.1,0.5,10))

        self.p.t_op_cooler_flash = 100.e-6
        # self.xvar('t_op_cooler_flash',np.linspace(0.,200.,50)*1.e-6)
        # self.xvar('t_repump_flash_imaging',np.linspace(0.,2.,20)*1.e-6)
        # self.xvar('t_cooler_flash_imaging',np.linspace(0.,2.,20)*1.e-6)
        self.p.t_cooler_flash_imaging = 2.e-6

        self.p.N_repeats = [20]

        self.finish_build(shuffle=True)

    @kernel
    def pump(self):
        if self.p.do_pumping:
            self.dds.optical_pumping.set_dds(set_stored=True)
            self.dds.optical_pumping.on()
            delay(self.p.t_op_cooler_flash)
            self.dds.optical_pumping.off()
        else:
            delay(self.p.t_op_cooler_flash)
        self.flash_cooler()

    @kernel
    def scan_kernel(self):

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot)
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.release()

        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.set_shims(v_xshim_current=self.p.v_xshim_current_op,
                       v_yshim_current=self.p.v_yshim_current_op,
                       v_zshim_current=self.p.v_zshim_current_op)
        delay(2.e-3)
        # if self.p.after_tof_bool == 0.:
        self.pump()

        self.magtrap()
        delay(10.e-3)
        self.inner_coil.off()

        # delay(self.p.t_tof)

        # if self.p.after_tof_bool == 1.:
        #     self.pump()

        # self.flash_repump()
        # self.flash_cooler()

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