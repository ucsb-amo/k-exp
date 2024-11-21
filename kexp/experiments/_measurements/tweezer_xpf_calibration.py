from artiq.experiment import *
from artiq.experiment import delay
from artiq.coredevice.core import now_mu
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class tweezer_xpf_calibration(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        
        self.p.frequency_tweezer_list_ce = np.array([74.e6, 72.1e6])
        self.p.amp_tweezer_list_ce = np.array([.295, .165])

        self.p.frequency_tweezer_list_nce = np.array([76.45, 78.3e6])
        self.p.amp_tweezer_list_nce = np.array([.185, .345])

        # self.xvar('cateye',[0,1])
        self.xvar('tweezer_index',[0,1])
        self.p.cateye = 1

        self.p.t_tof = 10.e-6
        # self.p.N_repeats = [1,1]

        self.camera_params.amp_imaging = .1

        self.tweezer.add_tweezer(frequency=74.e6,
                                 amplitude=0.)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.core.wait_until_mu(now_mu())
        idx = self.p.tweezer_index
        f = 0.
        a = 0.
        if self.p.cateye == 1:
            f = self.p.frequency_tweezer_list_nce[idx]
            a = self.p.amp_tweezer_list_nce[idx]
        elif self.p.cateye == 0:
            f = self.p.frequency_tweezer_list_ce[idx]
            a = self.p.amp_tweezer_list_ce[idx]

        self.tweezer.traps[0].frequency = f
        self.tweezer.traps[0].amplitude = a
        self.core.wait_until_mu(now_mu())
        self.tweezer.set_static_tweezers()
        self.tweezer.awg_trg_ttl.pulse(1.e-6)
        delay(100.*ms)
        self.tweezer.awg_trg_ttl.pulse(1.e-6)

        self.set_high_field_imaging(i_outer=self.p.i_evap3_current)

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet()

        # feshbach field on, ramp up to field 1  
        self.outer_coil.on()
        delay(1.e-3)
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_evap1_current)
        
        # lightsheet evap 1
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown,
                             v_start=self.p.v_pd_lightsheet_rampup_end,
                             v_end=self.p.v_pd_lightsheet_rampdown_end)
        
        # feshbach field ramp to field 2
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_evap1_current,
                             i_end=self.p.i_evap2_current)
        
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.tweezer.on(paint=False)
        self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_tweezer_1064_ramp_end,
                          paint=True,keep_trap_frequency_constant=False)
        
        # # lightsheet ramp down (to off)
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown2,
                             v_start=self.p.v_pd_lightsheet_rampdown_end,
                             v_end=self.p.v_pd_lightsheet_rampdown2_end)
        
        # # # tweezer evap 1 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown,
                          v_start=self.p.v_pd_tweezer_1064_ramp_end,
                          v_end=self.p.v_pd_tweezer_1064_rampdown_end,
                          paint=True,keep_trap_frequency_constant=True)
        
        # # # feshbach field ramp to field 3
        
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp2,
                             i_start=self.p.i_evap2_current,
                             i_end=self.p.i_evap3_current)
        
        # # # tweezer evap 2 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown2,
                          v_start=self.p.v_pd_tweezer_1064_rampdown_end,
                          v_end=self.p.v_pd_tweezer_1064_rampdown2_end,
                          paint=True,keep_trap_frequency_constant=True)
        
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown3,
                          v_start=tweezer_vpd1_to_vpd2(self.p.v_pd_tweezer_1064_rampdown2_end),
                          v_end=self.p.v_pd_tweezer_1064_rampdown3_end,
                          paint=True,keep_trap_frequency_constant=True,low_power=True)
        
        self.lightsheet.off()
        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

        self.outer_coil.off()
        self.outer_coil.discharge()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        if self.setup_camera:
            if self.run_info.save_data:
                self.cleanup_scanned()
                self.write_data(expt_filepath)
            else:
                self.remove_incomplete_data()