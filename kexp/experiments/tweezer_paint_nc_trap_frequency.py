from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class tof_scan(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        # self.p.imaging_state = 1.
        # self.xvar('frequency_detuned_imaging',np.arange(400.,450.,3)*1.e6)
        self.p.frequency_detuned_imaging = 429.e6 # 150a0
        # self.p.frequency_detuned_imaging = 412.e6 # NI

        self.p.t_mot_load = .75

        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(3.,8.,20))
        self.p.v_pd_lightsheet_rampdown_end = 5.368

        # self.xvar('freq_tweezer_modulation',np.linspace(100.e3,536.e3,20))
        # self.xvar('freq_tweezer_modulation',[])
        # self.xvar('v_tweezer_paint_amp_max',np.linspace(1.,6.,10))
        # self.p.freq_tweezer_modulation = 2.15e3
        self.p.v_tweezer_paint_amp_max = 4.

        # self.xvar('i_evap2_current',np.linspace(192.,195.,20))
        self.p.i_evap2_current = 193.7

        # self.xvar('v_pd_tweezer_1064_ramp_end', np.linspace(5.,9.9,20))
        self.p.v_pd_tweezer_1064_ramp_end = 9.5

        # self.xvar('t_tweezer_1064_ramp',np.linspace(10.,200.,20)*1.e-3)
        self.p.t_tweezer_1064_ramp = .075

        # self.xvar('v_pd_tweezer_1064_rampdown_end',np.linspace(.4,2.,20)) 
        self.p.v_pd_tweezer_1064_rampdown_end = 1.

        # self.xvar('t_tweezer_1064_rampdown',np.linspace(0.01,.1,10))
        self.p.t_tweezer_1064_rampdown = .06

        # self.xvar('v_pd_tweezer_1064_rampdown2_end',np.linspace(.03,.06,8)) 
        self.p.v_pd_tweezer_1064_rampdown2_end = .03

        # self.xvar('t_tweezer_1064_rampdown2',np.linspace(0.05,.15,8))
        self.p.t_tweezer_1064_rampdown2 = .12
        
        # self.xvar('i_tweezer_evap_current',self.p.i_evap2_current + np.linspace(-50.,1.,5))
        # self.p.i_tweezer_evap_current = 193.7
        # self.p.t_feshbach_field_ramp2 = .5

        # self.xvar('t_tweezer_hold',np.linspace(.001,.1,10))
        self.p.t_tweezer_hold = 100.e-3

        # self.xvar('t_tof',np.linspace(50.,350.,10)*1.e-6)
        self.p.t_tof = 100.e-6
        self.p.N_repeats = [3]
        
        self.xvar('dummy_z',[0]*5)

        self.p.n_tweezers = 1
        # self.xvar('frequency_tweezer_array_width',np.linspace(.2e6,1.e6,6))
        # self.p.frequency_tweezer_array_width = .7e6
        # self.p.amp_tweezer_auto_compute = False
        # self.xvar('amp_tweezer_list')
        self.p.amp_tweezer_list = [.17]

        # self.xvar('amp_imaging',np.linspace(.03,.08,15))
        # self.xvar('amp_imaging',np.linspace(.04,.09,20))
        self.camera_params.amp_imaging = 0.05
        self.camera_params.exposure_time = 10.e-6
        self.params.t_imaging_pulse = self.camera_params.exposure_time

        self.sh_dds = self.get_device("shuttler0_dds0")
        self.sh_dds: DDS
        self.sh_trigger = self.get_device("shuttler0_trigger")
        self.sh_trigger: Trigger
        self.sh_relay = self.get_device("shuttler0_relay")
        self.sh_relay: Relay

        self.finish_build(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.set_imaging_detuning(amp=self.p.amp_imaging)
        # self.set_high_field_imaging(i_outer = self.p.i_evap2_current)

        ### Shuttler stuff
        # frequency = self.p.freq_tweezer_modulation

        # n0 = shuttler_volt_to_mu(self.p.v_modulation_depth)
        # n1 = 0.
        # n2 = 0.
        # n3 = 0.
        # r0 = 0.
        # r1 = frequency
        # r2 = 0.

        # T = 8.e-9
        # g = 1.64676
        # q0 = n0/g
        # q1 = n1/g
        # q2 = n2/g
        # q3 = n3/g

        # b0 = np.int32(q0)
        # b1 = np.int32(q1 * T + q2 * T**2 / 2 + q3 * T**3 / 6)
        # b2 = np.int64(q2 * T**2 + q3 * T**3)
        # b3 = np.int64(q3 * T**3)

        # c0 = np.int32(r0)
        # c1 = np.int32((r1 * T + r2 * T**2) * T32)
        # c2 = np.int32(r2 * T**2)

        # self.sh_dds.set_waveform(b0=b0, b1=b1, b2=b2, b3=b3, c0=c0, c1=c1, c2=c2)
        # self.sh_trigger.trigger(0b11)

        # self.sh_relay.init()
        # self.sh_relay.enable(0b00)

        # self.sh_relay.enable(0b11)
        ###

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
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.inner_coil.on()

        # ramp up lightsheet over magtrap
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)

        for i in self.p.magtrap_ramp_list:
            self.inner_coil.set_current(i_supply=i)
            delay(self.p.dt_magtrap_ramp)

        delay(self.p.t_magtrap)

        for i in self.p.magtrap_rampdown_list:
            self.inner_coil.set_current(i_supply=i)
            delay(self.p.dt_magtrap_rampdown)

        self.inner_coil.off()
        
        self.outer_coil.on()
        delay(1.e-3)
        self.outer_coil.set_voltage()

        for i in self.p.feshbach_field_rampup_list:
            self.outer_coil.set_current(i_supply=i)
            delay(self.p.dt_feshbach_field_rampup)
        delay(20.e-3)

        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown,
                             v_ramp_list=self.p.v_pd_lightsheet_ramp_down_list)
        
        for i in self.p.feshbach_field_ramp_list:
            self.outer_coil.set_current(i_supply=i)
            delay(self.p.dt_feshbach_field_ramp)
        delay(20.e-3)

        self.tweezer.vva_dac.set(v=0.)
        self.tweezer.on(paint=True)
        self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp,
                          paint=True,keep_trap_frequency_constant=False)

        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown2,
                             v_ramp_list=self.p.v_pd_lightsheet_ramp_down2_list)

        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown,
                          v_ramp_list=self.p.v_pd_tweezer_1064_rampdown_list,
                          paint=True,keep_trap_frequency_constant=True)

        # for i in self.p.feshbach_field_ramp2_list:
        #     self.outer_coil.set_current(i_supply=i)
        #     delay(self.p.dt_feshbach_field_ramp2)
        # delay(30.e-3)

        # delay(self.p.t_tweezer_hold)

        # vpaint = self.tweezer.v_pd_to_painting_amp_voltage(v_pd=self.p.v_pd_tweezer_1064_rampdown_list[-1:])
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown2,
                          v_ramp_list=self.p.v_pd_tweezer_1064_rampdown2_list,
                          paint=True,keep_trap_frequency_constant=True)
        
        # self.outer_coil.set_current(i_supply=self.p.i_tweezer_evap_current)
        # delay(30.e-3)

        # self.ttl.pd_scope_trig.on()
        # self.outer_coil.off()
        # delay(self.p.t_feshbach_field_decay)
        # self.ttl.pd_scope_trig.off()

        self.lightsheet.off()
        self.tweezer.off()

        # self.sh_relay.enable(0b00)
    
        delay(self.p.t_tof)
        # self.flash_repump()
        self.abs_image()

        self.outer_coil.off()

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