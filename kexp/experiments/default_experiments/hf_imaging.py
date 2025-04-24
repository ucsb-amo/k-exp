from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2

T32 = 1<<32

class hf_imaging(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        self.p.t_mot_load = .75

        self.p.v_pd_lightsheet_rampdown_end = 3.

        self.p.v_tweezer_paint_amp_max = 4.

        self.xvar('i_evap2_current',np.linspace(179.,194.,15))
        self.xvar('frequency_detuned_imaging',np.arange(-630.,-530.,8)*1.e6)

        self.p.v_pd_tweezer_1064_ramp_end = 9.99
        self.p.t_tweezer_1064_ramp = .09

        self.p.t_tof = 25.e-6
        self.p.N_repeats = [1]
        
        self.p.n_tweezer_ramp_steps = 100

        self.p.t_lightsheet_hold = 100.e-3

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.set_imaging_detuning(amp=self.p.amp_imaging)

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.inner_coil.set_current(i_supply=self.p.i_magtrap_init)

        self.set_shims(v_zshim_current=self.p.v_zshim_current_gm,
                        v_yshim_current=self.p.v_yshim_current_gm,
                          v_xshim_current=self.p.v_xshim_current_gm)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        # self.release()
        self.switch_d2_3d(0)
        self.switch_d1_3d(0)

        self.flash_cooler()

        self.dds.power_down_cooling()

        self.set_shims(v_zshim_current=self.p.v_zshim_current_magtrap,
                        v_yshim_current=self.p.v_yshim_current_magtrap,
                          v_xshim_current=self.p.v_xshim_current_magtrap)

        # magtrap start
        self.inner_coil.on()

        # ramp up lightsheet over magtrap
        self.lightsheet.ramp(self.p.t_lightsheet_rampup,
                             self.p.v_pd_lightsheet_rampup_start,
                             self.p.v_pd_lightsheet_rampup_end)

        # mag trap ramp up
        self.inner_coil.ramp(t=self.p.t_magtrap_ramp,
                             i_start=self.p.i_magtrap_init,
                             i_end=self.p.i_magtrap_ramp_end)
        
        delay(self.p.t_magtrap)

        # mag trap ramp down
        self.ttl.pd_scope_trig.pulse(t=1.e-6)
        self.inner_coil.ramp(t=self.p.t_magtrap_rampdown,
                             i_start=self.p.i_magtrap_ramp_end,
                             i_end=0.)
        self.inner_coil.off()
        
        # feshbach field on, ramp up to field 1
        self.outer_coil.on()
        delay(1.e-3)
        self.outer_coil.set_voltage()
        self.outer_coil.ramp(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_evap1_current)

        # lightsheet evap 1
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown,
                             v_start=self.p.v_pd_lightsheet_rampup_end,
                             v_end=self.p.v_pd_lightsheet_rampdown_end)
        
        # feshbach field ramp to field 2
        self.outer_coil.ramp(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_evap1_current,
                             i_end=self.p.i_evap2_current)

        # tweezer ramp up, constant paint amplitude
        # self.ttl.pd_scope_trig.pulse(t=1.e-6)
        self.tweezer.on(paint=True)
        self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_tweezer_1064_ramp_end,
                          paint=True,keep_trap_frequency_constant=False)

        ## lightsheet ramp down (to off)
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown2,
                             v_start=self.p.v_pd_lightsheet_rampdown_end,
                             v_end=self.p.v_pd_lightsheet_rampdown2_end)
        
        self.lightsheet.off()
        self.tweezer.off()
    
        delay(self.p.t_tof)
        self.abs_image()

        self.outer_coil.off()

        # mitigate spike for next run
        self.outer_coil.discharge()

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

