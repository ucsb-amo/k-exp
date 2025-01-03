from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        self.xvar('frequency_detuned_imaging',np.arange(-615.,-530.,8)*1.e6)
        
        self.p.t_mot_load = 1.5
        
        self.p.t_rf_state_xfer_sweep = 40.e-3
        self.p.n_rf_sweep_steps = 1000
        self.p.frequency_rf_sweep_state_prep_fullwidth = 10.e3

        # self.xvar('frequency_rf_sweep_state_prep_fullwidth',np.linspace(10.,200.,20)*1.e3)
        # self.xvar('frequency_rf_sweep_state_prep_center', 145.5e6 + np.linspace(-5.,5.,60)*1.e6)
        # self.xvar('frequency_rf_sweep_state_prep_center', np.linspace(145.4,145.6,5)*1.e6)
        self.p.frequency_rf_sweep_state_prep_center = 145.462e6
        # self.p.frequency_rf_sweep_state_prep_center = 146.177e6

        # self.xvar('t_rf_state_xfer_sweep',np.linspace(15.,50.,20)*1.e-3)
        # self.xvar('t_fake_ramsey_delay',np.linspace(0.,100.,20)*1.e-3)
        # self.p.t_fake_ramsey_delay = 1.e-3
        # self.xvar('ifdosweep',[0,1])
        self.p.t_fake_ramsey_delay = 1.e-3

        self.p.ifdosweep = 1

        # self.xvar('i_end',np.linspace(179.,193.,20))
        self.p.i_end = 185.

        # self.xvar('rf_drive_frequency', np.linspace(145.3,145.4,15)*1.e6)
        # self.p.rf_drive_frequency = 145.336e6
        # self.xvar('t_rabi_drive', np.linspace(20.,550.,30)*1.e-6)
        self.p.t_rabi_drive = 1.e-6

        # self.xvar('t_rabi_drive', np.linspace(200.,1500.,40)*1.e-6)

        self.xvar('pid_setpoint',np.linspace(196.,202.90,10))
        self.p.pid_setpoint = 196.3


        # self.xvar('beans',[0.]*100)

        self.pfrac_c_gmramp_end = 0.38
        self.pfrac_r_gmramp_end = 0.27

        # self.xvar('i_evap1_current',np.linspace(190.,195.,20))
        # self.p.i_evap1_current = 192.

        # self.xvar('t_lightsheet_rampdown',np.linspace(.02,1.,8))
        # self.p.t_lightsheet_rampdown = .16

        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(3.,8.,15))
        # self.p.v_pd_lightsheet_rampdown_end = 3.
        self.p.v_pd_lightsheet_rampdown_end = 7.

        # self.xvar('i_evap2_current',np.linspace(192.5,194.5,8))
        self.p.i_evap2_current = 197.72

        # self.xvar('t_tweezer_1064_ramp',np.linspace(.012,.3,20))
        # self.p.t_tweezer_1064_ramp = .17

        # self.xvar('v_tweezer_paint_amp_max',np.linspace(-5.,0.,10))
        self.p.v_tweezer_paint_amp_max = -3.

        # self.xvar('t_tweezer_1064_rampdown',np.linspace(0.012,.1,8))
        # self.p.t_tweezer_1064_rampdown = .12

        # self.xvar('v_pd_tweezer_1064_rampdown_end',np.linspace(0.1,1.5,8))
        self.p.v_pd_tweezer_1064_rampdown_end = .7

        # self.xvar('v_pd_tweezer_1064_rampdown2_end',np.linspace(0.04,.099,5))
        self.p.v_pd_tweezer_1064_rampdown2_end = .06

        # self.xvar('t_tweezer_1064_rampdown2',np.linspace(0.1,.8,8))
        self.p.t_tweezer_1064_rampdown2 = .4

        # self.xvar('v_pd_tweezer_1064_rampdown3_end',np.linspace(.4,2.,8))
        self.p.v_pd_tweezer_1064_rampdown3_end = 1.4

        # self.xvar('t_tweezer_1064_rampdown3',np.linspace(0.02,.5,8))
        self.p.t_tweezer_1064_rampdown3 = .1
        
        # self.xvar('i_evap3_current',np.linspace(192.5,194.3,8))
        self.p.i_evap3_current = 197.53

        # self.xvar('amp_imaging',np.linspace(0.05,0.125,10))
        # self.xvar('frequency_detuned_imaging',\
        #           high_field_imaging_detuning(self.p.i_evap3_current) \
        #             + np.arange(-100.,100.,10.)*1.e6)

        self.p.frequency_tweezer_list = [73.7e6,77.3e6]
        a_list = [.45,.54]

        self.p.amp_tweezer_list = a_list
        self.p.amp_tweezer_auto_compute = False

        self.p.v_tweezer_paint_amp_max = -3.

        self.p.t_tof = 5.e-6
        self.p.N_repeats = [3,1]

        self.p.t_mot_load = .75

        self.camera_params.amp_imaging = .12
        self.camera_params.exposure_time = 10.e-6
        self.p.t_imaging_pulse = self.camera_params.exposure_time

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.set_high_field_imaging(i_outer=192.3)
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)
        self.set_imaging_detuning(self.p.frequency_detuned_imaging)

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
                             i_end=self.p.pid_setpoint)
        
        # self.ttl.pd_scope_trig.pulse(1.e-6)
        # self.tweezer.on(paint=False)
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp,
        #                   v_start=0.,
        #                   v_end=self.p.v_pd_tweezer_1064_ramp_end,
        #                   paint=True,keep_trap_frequency_constant=False)
        
        # # # lightsheet ramp down (to off)
        # self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown2,
        #                      v_start=self.p.v_pd_lightsheet_rampdown_end,
        #                      v_end=self.p.v_pd_lightsheet_rampdown2_end)
        
        # # tweezer evap 1 with constant trap frequency
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown,
        #                   v_start=self.p.v_pd_tweezer_1064_ramp_end,
        #                   v_end=self.p.v_pd_tweezer_1064_rampdown_end,
        #                   paint=True,keep_trap_frequency_constant=True)

        # # feshbach field ramp to field 3
        
        # self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp2,
        #                      i_start=self.p.i_evap2_current,
        #                      i_end=self.p.i_evap3_current)
        
        # # tweezer evap 2 with constant trap frequency
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown2,
        #                   v_start=self.p.v_pd_tweezer_1064_rampdown_end,
        #                   v_end=self.p.v_pd_tweezer_1064_rampdown2_end,
        #                   paint=True,keep_trap_frequency_constant=True)
        
        # # tweezer evap 3 with constant trap frequency
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown3,
        #                   v_start=tweezer_vpd1_to_vpd2(self.p.v_pd_tweezer_1064_rampdown2_end),
        #                   v_end=self.p.v_pd_tweezer_1064_rampdown3_end,
        #                   paint=True,keep_trap_frequency_constant=True,low_power=True)
        
        # self.outer_coil.ramp(t=self.p.t_feshbach_field_ramp2,
        #                      i_start=self.p.i_evap3_current,
        #                      i_end=self.p.i_end)
        delay(30.e-3)
        # self.ttl.pd_scope_trig.pulse(1.e-6)
        # self.dac.outer_coil_pid.set(v=4.8075)
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.outer_coil.start_pid(i_pid=self.p.pid_setpoint)
        # self.ttl.outer_coil_pid_enable.on()
        # self.outer_coil.start_pid()
        delay(.6)

        # if self.p.ifdosweep:
        #     self.rf.set_rf(frequency=self.p.frequency_rf_sweep_state_prep_center)
        #     self.rf.on()
        #     delay(self.p.t_rabi_drive)
            # self.rf.sweep(t=self.p.t_rf_state_xfer_sweep, frequency_center=self.p.frequency_rf_sweep_state_prep_center)
            # delay(self.p.t_fake_ramsey_delay)
            # self.rf.sweep(t=self.p.t_rf_state_xfer_sweep, frequency_center=self.p.frequency_rf_sweep_state_prep_center)
            # self.rf.off()
        # else:
        #     delay(self.p.t_rf_state_xfer_sweep)
            # delay(self.p.t_fake_ramsey_delay)
            # delay(self.p.t_rf_state_xfer_sweep)
        
        self.lightsheet.off()
        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

        self.ttl.outer_coil_pid_enable.off()
        delay(50.e-3)

        # self.outer_coil.stop_pid()

        self.outer_coil.off()
        # self.outer_coil.discharge()

        

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