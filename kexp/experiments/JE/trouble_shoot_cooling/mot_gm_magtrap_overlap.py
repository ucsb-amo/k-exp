from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class mag_trap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=False)

        self.p.t_tof = 9000.e-6
        # self.xvar('t_tof',np.linspace(7.5,15.,10)*1.e-3)
        self.xvar('dumy',[2]*500)

        self.p.t_magtrap_hold = .15
        
        self.p.t_magtrap = .1

        self.p.t_lightsheet_hold = .15

        self.p.N_repeats = 1
        self.p.t_mot_load = .5

        # self.camera_params.exposure_time = 100.e-6
        # self.params.t_imaging_pulse = self.camera_params.exposure_time
        # self.camera_params.gain = 1.

        self.p.amp_imaging = .18
        self.p.imaging_state = 2.

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        if self.p.dumy == 0:
            self.mot(self.p.t_mot_load)
            self.dds.push.off()
            self.release()
            
        elif self.p.dumy == 1:
            self.mot(self.p.t_mot_load)
            self.dds.push.off()
            self.cmot_d1(self.p.t_d1cmot * s,)
            
            self.gm(self.p.t_gm * s)
            self.gm_ramp(self.p.t_gmramp)
            self.release()

        elif self.p.dumy == 2:
            self.mot(self.p.t_mot_load)
            self.dds.push.off()
            self.cmot_d1(self.p.t_d1cmot * s,)
            
            self.gm(self.p.t_gm * s)
            self.gm_ramp(self.p.t_gmramp)

            self.ttl.pd_scope_trig.pulse(1.e-6)
            self.magtrap_and_load_lightsheet(do_lightsheet_ramp=False,do_magtrap_rampup=False, do_magtrap_hold=False,do_magtrap_rampdown=False)
            delay(self.p.t_magtrap_hold)
            self.inner_coil.snap_off()
        
        elif self.p.dumy == 3:
            self.mot(self.p.t_mot_load)
            self.dds.push.off()
            self.cmot_d1(self.p.t_d1cmot * s,)
            
            self.gm(self.p.t_gm * s)
            self.gm_ramp(self.p.t_gmramp)

            self.ttl.pd_scope_trig.pulse(1.e-6)
            self.magtrap_and_load_lightsheet(do_lightsheet_ramp=True,do_magtrap_rampup=False, do_magtrap_rampdown=True)
            # delay(self.p.t_magtrap_hold)
            # self.inner_coil.snap_off()

            delay(self.p.t_lightsheet_hold)

            self.lightsheet.off()

        
        # self.dds.mot_killer.on()

        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()

        # self.dds.mot_killer.off()

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
