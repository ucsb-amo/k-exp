from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning
from kexp import Base, img_types, cameras

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class mag_trap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select=cameras.xy_basler,
                      imaging_type=img_types.ABSORPTION)

        self.p.t_tof = 800.e-6
        # self.xvar('t_tof',np.linspace(300,1000.,10)*1.e-6)
        # self.xvar('t_tof',np.linspace(5.,20.,10)*1.e-3)
        # self.xvar('dumy0',np.linspace(1.,50.,50))
        # self.xvar('dumy',[0,1]*5)
        # self.p.dumy = 0
        # self.xvar('dumy0',np.linspace(0.,50.,50))

        # self.xvar('pfrac_c_gmramp_end',np.linspace(0.01,.15,8))
        # self.xvar('pfrac_r_gmramp_end',np.linspace(0.1,.7,8))
        # self.p.pfrac_c_gmramp_end = 0.03
        # self.p.pfrac_r_gmramp_end = 0.55

        # self.xvar('v_xshim_current_magtrap',np.linspace(0.,4.,8))
        # self.xvar('v_yshim_current_magtrap',np.linspace(0.,3.,10))

        # self.xvar('i_magtrap_init',np.linspace(75.,95.,15))
        # self.p.i_magtrap_init = 94.

        # self.xvar('t_magtrap_ramp',np.linspace(.02,.4,10))
        # self.p.t_magtrap_ramp = .4

        # self.xvar('t_lightsheet_rampup',np.linspace(20.,1000.,15)*1.e-3)
        # self.p.t_lightsheet_rampup = .3

        self.xvar('v_pd_lightsheet_rampup_end',np.linspace(5.,9.5,15))
        # self.p.v_pd_lightsheet_rampup_end = 7.3

        # self.xvar('t_magtrap',np.linspace(.5,2.,10))
        # self.p.t_magtrap = .5

        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(3.,8.,10))
        
        # self.xvar('t_lightsheet_hold',np.linspace(0.,1.5,20))
        self.p.t_lightsheet_hold = .1

        # self.xvar('hf_imaging_detuning', np.arange(-10.,40.,3.)*1.e6)

        # self.xvar('t_imaging_pulse',np.linspace(1.,20.,20)*1.e-6)
        # self.p.t_imaging_pulse = 2.e-5    
       
        # self.camera_params.exposure_time = 50.e-6
        # self.params.t_imaging_pulse = self.camera_params.exposure_time
        # self.camera_params.em_gain = 1.

        # self.xvar('amp_imaging',np.linspace(0.09,.2,10))
        # self.p.amp_imaging = .11

        self.p.N_repeats = 1
        self.p.t_mot_load = 1.
        # self.p.amp_imaging = .1
        self.p.imaging_state = 2.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.set_imaging_detuning(frequency_detuned=self.p.hf_imaging_detuning)
        # self.dds.mot_killer.set_dds_gamma(0.,amplitude=self.p.amp_imaging)
        # self.dds.imaging.set_dds_gamma(amplitude=self.p.amp_imaging)

        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False)
        self.dac.yshim_current_control.linear_ramp(self.p.t_yshim_rampdown,
                                                   self.p.v_yshim_current_magtrap,
                                                   0.,n=100)
        # self.dds.mot_killer.on()
        delay(self.p.t_lightsheet_hold)
        
        self.lightsheet.off()
        
        delay(self.p.t_tof)
        self.flash_repump()
        # self.flash_cooler()
        self.abs_image()

        # self.dds.mot_killer.off()
        

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
