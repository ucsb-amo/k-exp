from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class better_pumping_flash(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        # self.xvar('i_magtrap_init',np.linspace(20.,40.,8))
        # self.xvar('t_magtrap_hold',np.linspace(1.,100.,5)*1.e-3)
        self.p.i_magtrap_init = 27.

        # self.xvar('i_magtrap_init',np.linspace(20.,60.,8))
        # self.xvar('t_magtrap_hold',np.linspace(10.,80.,8)*1.e-3)
        self.p.t_magtrap_hold = 150.e-3

        

        self.p.t_tof = 10.e-3
        # self.xvar('t_tof',np.linspace(5.,10.,8)*1.e-3)

        # self.xvar('do_pumping',[0,1])
        self.p.do_pumping = 1.
        self.p.use_op_repump = 0.
        # self.p.detune_optical_pumping_r_op = -9.2
        self.p.amp_optical_pumping_r_op = 0.5
        self.xvar('use_op_repump',[0,1])
        # self.p.t_cooler_flash_imaging = 3.e-6

        self.p.t_op_cooler_flash = 200.e-6
        # self.xvar('t_op_cooler_flash',np.linspace(50.,500.,10)*1.e-6)

        self.p.N_repeats = [20]

        self.finish_prepare(shuffle=True)

    @kernel
    def pump(self):
        delay(2.e-3)
        if self.p.do_pumping:
            self.dds.optical_pumping.set_dds(set_stored=True)
            self.dds.op_r.set_dds(set_stored=True)
            self.dds.optical_pumping.on()
            if self.p.use_op_repump:
                self.dds.op_r.on()
            delay(self.p.t_op_cooler_flash)
            self.dds.op_r.off()
            self.dds.optical_pumping.off()
            self.flash_cooler()
        else:
            delay(self.p.t_op_cooler_flash)
            self.flash_cooler()

    # @kernel
    # def pump(self):
    #     delay(2.e-3)
    #     if self.p.do_pumping:
    #         self.dds.optical_pumping.set_dds(set_stored=True)
    #         self.dds.optical_pumping.on()
    #         delay(self.p.t_op_cooler_flash)
    #         self.dds.optical_pumping.off()
    #         self.flash_cooler()
    #     else:
    #         delay(self.p.t_op_cooler_flash)
    #         self.flash_cooler()

    @kernel
    def scan_kernel(self):

        # self.set_imaging_detuning(amp=self.p.amp_imaging)

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        # self.release()
        self.switch_d2_3d(0)
        self.switch_d1_3d(0)

        # self.flash_cooler()
        self.pump()

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
