from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning
from artiq.language.core import now_mu

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2

T32 = 1<<32

class tweezer_paint(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)
        self.camera_params.amp_imaging = 0.5
        
        self.p.t_mot_load = .5

        # self.p.v_lightsheet_paint_amp_max = 4

        self.p.beans = 0
        # self.xvar("beans", [0,1]*200)

        self.xvar('v_lightsheet_paint_amp_max',np.linspace(-7.,6.,10))

        self.p.t_tof = 10.e-6
        self.p.t_lightsheet_hold = .1
        #self.p.N_repeats = [10]

        self.sh_dds = self.get_device("shuttler0_dds0")
        self.sh_dds: DDS
        self.sh_trigger = self.get_device("shuttler0_trigger")
        self.sh_trigger: Trigger
        self.sh_relay = self.get_device("shuttler0_relay")
        self.sh_relay: Relay

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)


        self.magtrap_and_load_lightsheet()
        
        delay(self.p.t_lightsheet_hold)

        self.lightsheet.off()
    
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

