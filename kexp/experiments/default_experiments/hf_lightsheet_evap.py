from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, Adjust
import numpy as np
from kexp.calibrations import high_field_imaging_detuning
from kexp import Base, img_types, cameras, aprint

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class mag_trap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION,
                      warmup_shots=0)

        self.p.t_tof = 1.2e-3
        # self.xvar('beans',np.linspace(1,10.,10))

        self.xvar('t_tof',np.linspace(200,1100.,9)*1.e-6)

        # self.xvar('t_lightsheet_rampup',np.linspace(20.,400.,15)*1.e-3)
        # self.xvar('v_pd_lightsheet_rampup_end',np.linspace(4.,8.6,11))
        # self.p.t_lightsheet_rampup = 0.074
        # self.p.v_pd_lightsheet_rampup_end = 7.1

        # self.xvar('i_hf_lightsheet_evap1_current',np.linspace(192.5,194.,5))
        # self.p.i_hf_lightsheet_evap1_current = 192.7
        # # self.p.i_hf_lightsheet_evap1_current = 18.

        # self.p.t_tof = 1.3992e-3

        # # self.p.v_pd_lightsheet_rampup_end = 7.6
 
        # self.xvar('v_pd_hf_lightsheet_rampdown_end',np.linspace(.4,1.4,11))
        # self.p.v_pd_hf_lightsheet_rampdown_end = 0.82
        
        self.p.t_hf_lightsheet_rampdown=150.e-3
        # self.xvar('t_hf_lightsheet_rampdown',np.linspace(.2,1.5,8))
    
        # self.adjust('amp_imaging',0.3,0.6)

        # self.p.t_decay_exponential = self.p.t_hf_lightsheet_rampdown
        # self.p.n_lightsheet_evap1_decay_exponential = 1.5
        # self.xvar('n_decay_exponential', np.linspace(2.5,5.,7))

        self.p.N_repeats = 5
        self.p.t_mot_load = 1.

        Adjust.__init__(self)

        self.p.use_imaging_calibration = 1
        self.adjust('use_imaging_calibration', min_val=0.,max_val=1.,step=1.,dtype=float)

        self.p.hf_imaging_detuning = -620.e6
        self.adjust('hf_imaging_detuning', min_val=-700.e6, max_val=-550.e6, step=1.e6, dtype=float)

        # self.adjust('n_decay_exponential', min_val=0.3, max_val=8.)

        self.finish_prepare(shuffle=True)
        
    @kernel
    def scan_kernel(self):

        # self.p.t_decay_exponential = self.p.t_hf_lightsheet_rampdown / self.p.n_decay_exponential

        f0 = high_field_imaging_detuning(self.p.i_hf_lightsheet_evap1_current)
        # aprint(f0/1.e6)
        if self.p.use_imaging_calibration == 1.:
            self.set_imaging_detuning(f0)
        else:
            self.set_imaging_detuning(self.p.hf_imaging_detuning)
        # self.imaging.set_power(power_control_parameter=self.p.amp_imaging)

        # self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False,do_magtrap_rampdown=True)
        # self.inner_coil.snap_off()

        # feshbach field on, ramp up to field 1
        self.outer_coil.on()
        self.outer_coil.set_voltage()
        
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_hf_lightsheet_evap1_current)
        
        self.set_shims(0.,0.,0.)

        # lightsheet evap 1
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.lightsheet.exponential_ramp(t=self.p.t_hf_lightsheet_rampdown,
                             v_start=self.p.v_pd_lightsheet_rampup_end,
                             v_end=self.p.v_pd_hf_lightsheet_rampdown_end)

        # self.lightsheet.exponential_rampramp(t=self.p.t_hf_lightsheet_rampdown,
        #                             v_start=self.p.v_pd_lightsheet_rampup_end,
        #                             v_end=self.p.v_pd_hf_lightsheet_rampdown_end
        #                             )
        
        # self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
        #                      i_start=self.p.i_hf_lightsheet_evap1_current,
        #                      i_end=self.p.i_hf_lightsheet_evap2_current)
        
        # # lightsheet evap 2
        # self.lightsheet.ramp(t=self.p.t_hf_lightsheet_rampdown2,
        #                      v_start=self.p.v_pd_hf_lightsheet_rampdown_end,
        #                      v_end=self.p.v_pd_hf_lightsheet_rampdown2_end)

        delay(self.p.t_lightsheet_hold)
        self.lightsheet.off()

        delay(self.p.t_tof)
        self.abs_image()

        # self.lightsheet.off()

        self.outer_coil.off()

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
