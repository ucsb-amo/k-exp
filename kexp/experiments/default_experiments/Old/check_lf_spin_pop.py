from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning
from kexp import Base, img_types, cameras
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class mag_trap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION)
        
        # self.p.t_tof = 50.e-6
        self.p.t_tof = 50.e-6
        # self.xvar('t_tof',np.linspace(1000.,3500.,15)*1.e-6) 
        # self.xvar('dumy',[0]*3)
    
        self.xvar('hf_imaging_detuning', [298.e6,328.e6]*1) # 18 A

        # self.xvar('t_magtrap_rampdown',np.linspace(5.,60.,10)*1.e-3)
        self.p.t_magtrap_rampdown = 15.e-3

        self.xvar('t_feshbach_field_ramp',np.linspace(.015,.2,5))
        # self.p.t_feshbach_field_ramp = 100.e-3

        # self.n_field_ramp_steps = 400

        # self.xvar('i_lf_lightsheet_evap1_current',np.linspace(181.,194.,15))
        self.p.i_lf_lightsheet_evap1_current = 18.

        # self.xvar('v_pd_hf_lightsheet_rampdown_end',np.linspace(.5,3.,15))
        # self.p.v_pd_hf_lightsheet_rampdown_end = 1.

        # self.xvar('t_hf_lightsheet_rampdown',np.linspace(100.,2000.,8)*1.e-3)
        # self.p.t_hf_lightsheet_rampdown = .64
        # self.xvar('t_tof',np.linspace(1000.,3000.,10)*1.e-6)

        # self.xvar('t_lightsheet_hold',np.linspace(1.,500.,10)*1.e-3)
        self.p.t_lightsheet_hold = 50.e-3

        # self.xvar('hf_imaging_detuning', np.arange(280.,410.,3.)*1.e6)
        # self.p.hf_imaging_detuning = -601.e6
        self.p.hf_imaging_detuning = -618.5e6

        # self.xvar('amp_imaging', np.linspace(.1,.3,15))
        # self.p.amp_imaging = .35
        self.p.amp_imaging = .1
        self.p.imaging_state = 2.

        self.p.N_repeats = 1
        self.p.t_mot_load = 1.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.hf_imaging_detuning)
        # self.set_high_field_imaging(i_outer=self.p.i_lf_lightsheet_evap1_current)
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        # self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False)
        # self.inner_coil.snap_off()
        self.ttl.pd_scope_trig.pulse(1.e-6)

        self.dac.yshim_current_control.linear_ramp(self.p.t_yshim_rampdown,self.p.v_yshim_current_magtrap,0.,n=500)

        self.outer_coil.on()
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_lf_lightsheet_evap1_current)

        delay(self.p.t_lightsheet_hold)
        self.lightsheet.off()

        delay(self.p.t_tof)
        # self.flash_repump()
        self.abs_image()

        self.outer_coil.off()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        # self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
