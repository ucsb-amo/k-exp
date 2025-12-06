from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, cameras
import numpy as np
from kexp.calibrations import high_field_imaging_detuning

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class mag_trap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select=cameras.xy_basler,save_data=True)

        self.p.t_tof = 20.e-6
        # self.p.t_tof = 20.e-6
        self.xvar('t_tof',np.linspace(5.,10.,10)*1.e-3)
        # self.xvar('t_tof',np.linspace(5.,20.,10)*1.e-3)
        # self.xvar('dumy',[0]*500)

        self.p.t_magtrap_hold = 0.15 
        # self.p.t_magtrap_hold = 1.

        self.p.N_repeats = 1
        self.p.t_mot_load = .5

        self.p.amp_imaging = .18
        # self.xvar('amp_imaging',np.linspace(0.08,0.12,5))
        # self.camera_params.gain = 0.
        self.p.imaging_state = 2.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.dds.imaging.set_dds()
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.ttl.pd_scope_trig.pulse(1.e-8)
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        # self.ttl.pd_scope_trig.pulse(1.e-6)
        self.magtrap_and_load_lightsheet(do_lightsheet_ramp=False,
                                        do_magtrap_rampup=False,
                                        do_magtrap_hold=False,
                                        do_magtrap_rampdown=False)
        delay(self.p.t_magtrap_hold)
        # self.ttl.pd_scope_trig.pulse(1.e-6)
        self.inner_coil.snap_off()

        
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
