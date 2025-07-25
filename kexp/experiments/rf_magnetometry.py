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

        self.p.t_tof = 200.e-6
        # self.xvar('t_tof',np.linspace(600,1500.,10)*1.e-6)
        # self.xvar('t_tof',np.linspace(5.,20.,10)*1.e-3)
        # self.xvar('dumy0',np.linspace(1.,1200.,3))
        # self.xvar('dumy',[0,1]*1)
        self.p.dumy = 0
        # self.xvar('dumy0',np.linspace(1.,1200.,3))

        self.p.v_pd_lightsheet_rampup_end = 8.3

        # self.xvar('t_magtrap',np.linspace(.1,3.,15))
        self.p.t_magtrap = 1.5
        
        # self.xvar('t_lightsheet_hold',np.linspace(0.,1.5,20))
        self.p.t_lightsheet_hold = .01

        self.p.t_rf_state_xfer_sweep = 50.e-3
        self.p.n_rf_state_xfer_sweep_steps = 1000
        self.p.frequency_rf_state_xfer_sweep_fullwidth = 147.e3
        self.p.do_sweep = 1

        # self.xvar('i_evap1_current',np.linspace(0.,200.,100))
        # self.xvar('frequency_rf_sweep_state_prep_center', 140.e6 + np.linspace(0.,20.,60)*1.e6)
        self.xvar('frequency_rf_state_xfer_sweep_center', np.linspace(458.,465.2,50)*1.e6)

        # self.xvar('hf_imaging_detuning', np.arange(0.,470.,8.)*1.e6)

        # self.xvar('t_imaging_pulse',np.linspace(1.,20.,20)*1.e-6)
        # self.p.t_imaging_pulse = 2.e-5    
       
        # self.camera_params.exposure_time = 50.e-6
        # self.params.t_imaging_pulse = self.camera_params.exposure_time
        # self.camera_params.em_gain = 1.

        # self.xvar('amp_d2_c_imaging',np.linspace(0.,.188,10))
        # self.p.amp_d2_c_imaging = .188

        self.p.N_repeats = 1
        self.p.t_mot_load = 1.
        # self.p.amp_imaging = .1
        self.p.imaging_state = 2.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.set_imaging_detuning(frequency_detuned=self.p.hf_imaging_detuning)

        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        # if self.p.dumy:
            # self.ttl.d2_mot_shutter.off()

        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False)

        self.dac.yshim_current_control.linear_ramp(self.p.t_yshim_rampdown,self.p.v_yshim_current_magtrap,0.,n=500)

        # self.set_shims(v_xshim_current=0.,v_yshim_current=0.,v_zshim_current=.5)
        self.outer_coil.on()
        self.outer_coil.set_voltage()
        self.outer_coil.set_supply(i_supply=.01)
        delay(30.e-3)

        self.rf.sweep(t=self.p.t_rf_state_xfer_sweep,
                      frequency_center=self.p.frequency_rf_state_xfer_sweep_center)
        delay(1.e-3)
        
        self.outer_coil.off()

        delay(self.p.t_lightsheet_hold)

        self.lightsheet.off()
        
        delay(self.p.t_tof)
        # self.flash_repump()
        # self.flash_cooler()
        self.abs_image()

        

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
