from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning
from kexp import Base, img_types, cameras, Adjust

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class mag_trap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                    save_data=True,
                    camera_select=cameras.xy_basler,
                    imaging_type=img_types.ABSORPTION)

        self.p.t_tof = 700.e-6
        self.xvar('t_tof',np.linspace(300,1200.,5)*1.e-6)
        # self.xvar('t_tof',np.linspace(20.,300.,7)*1.e-6)
        # self.xvar('beans',np.linspace(1,10.,10))

       



        # self.xvar('v_xshim_current_magtrap',np.linspace(1.,2.,7))
        # self.xvar('v_yshim_current_magtrap',np.linspace(0.,5.,7))
        # self.xvar('v_zshim_current_magtrap',np.linspace(0.,0.5,5))

        # self.xvar('i_magtrap_init',np.linspace(104.,110.,6))
        self.p.i_magtrap_init = 106.5 # makbe keep maybe don't

        # self.p.i_magtrap_ramp_end = 40.
        # self.xvar('i_magtrap_ramp_end',np.linspace(32.5,55.,7))
        # self.xvar('t_magtrap_ramp', np.linspace(0.05,0.125,5))

        # self.xvar('do_rampup',[0,1])
        self.camera_params.amp_imaging = 0.2

        # self.xvar('t_magtrap',np.linspace(.1,3.,15))
        # self.p.t_magtrap = 1.
        
        # self.xvar('t_lightsheet_hold',np.linspace(0.05,1.,5))
        # self.p.t_lightsheet_hold = .

        # self.xvar('amp_imaging',np.linspace(0.08,0.12,5)) 

        # self.xvar('v_pd_lightsheet_rampup_end', np.linspace(6.7,7.4,9))
        self.p.v_pd_lightsheet_rampup_end=6.9
        # self.xvar('t_lightsheet_rampup', np.linspace(.05,.7,11))

        # self.p.t_lightsheet_rampup=0.15

        self.p.N_repeats = 2
        self.p.t_mot_load = 1.
        # self.p.amp_imaging = .25
        self.p.imaging_state = 2.

        # Adjust.__init__(self)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)
        self.imaging.set_power(self.camera_params.amp_imaging)

        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False)
        
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
