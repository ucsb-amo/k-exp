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

        self.p.t_tof = 5.e-3
        # self.p.t_tof = 20.e-6
        # self.xvar('t_tof',np.linspace(3.,15.,10)*1.e-3)
        self.xvar('t_tof',np.linspace(6.,20.,10)*1.e-3)
        # self.xvar('dumy',[0]*500)

        # self.xvar('pfrac_d1_c_d1cmot',np.linspace(0.2,1.0,10))
        # self.xvar('v_zshim_current_gm',np.linspace(0.6, 1., 10))
        # self.xvar('v_xshim_current_gm',np.linspace(0.5, 1., 10))
        # self.xvar('v_yshim_current_gm',np.linspace(0.0, 2.99, 10))
        # self.xvar('t_pump_to_F1',np.linspace(0.,100.,10)*1.e-6)
        # self.p.t_pump_to_F1 = 50.e-6
        # self.xvar('detune_gm',np.linspace(6.,10.,10))
        # self.xvar('detune_d1_c_gm',np.linspace(6.,8.,20))
        # self.p.detune_d1_c_gm = 7.25
        # self.xvar('pfrac_d1_c_gm',np.linspace(0.5,1.0,5))
        # self.xvar('pfrac_d1_r_gm',np.linspace(0.3,0.6,5))
        # self.xvar('pfrac_c_gmramp_end',np.linspace(0.05,self.p.pfrac_d1_c_gm,12))
        # self.xvar('pfrac_r_gmramp_end',np.linspace(0.05,self.p.pfrac_d1_r_gm,8))
        
        # self.xvar('detune_optical_pumping_op',np.linspace(0.,5.,10))

        # self.xvar('v_zshim_current_magtrap',np.linspace(0.,2.,10))
        # self.xvar('v_xshim_current_magtrap',np.linspace(0.,2.,10))
        # self.xvar('v_yshim_current_magtrap',np.linspace(2.,9.9,10))
        self.p.v_zshim_current_magtrap = 0.67
        self.p.v_xshim_current_magtrap = 0.
        self.p.v_yshim_current_magtrap = 5.50
        # self.xvar('t_magtrap_delay',np.linspace(0.05,10.,20)*1.e-3)
        # self.p.t_magtrap_delay = 1.e-3
        # self.p.t_shim_delay = .5e-3
        # self.xvar('t_mot_load',np.linspace(0.5,3.0,5))

        # self.xvar('t_magtrap_hold',np.linspace(5.,15.,12)*1.e-3)
        # self.p.t_magtrap = 0.05
        self.p.t_magtrap_hold = 0.2 
        # self.p.t_magtrap_hold = 1.

        self.p.N_repeats = 1
        self.p.t_mot_load = 1.

        self.p.amp_imaging = .095
        # self.xvar('amp_imaging',np.linspace(0.08,0.12,5))
        # self.camera_params.gain = 0.
        self.p.imaging_state = 2.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

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
