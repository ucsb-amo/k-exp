from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from artiq.language.core import now_mu

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class trap_frequency_spectroscopy(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        self.p.imaging_state = 1.
        self.p.t_mot_load = 1.

        self.p.t_tof = 4.e-6

        self.camera_params.amp_imaging = 0.09
        self.camera_params.exposure_time = 12.e-6
        self.params.t_imaging_pulse = self.camera_params.exposure_time

        self.p.v_pd_lightsheet_rampdown_end = 6.

        self.xvar('v_pd_tweezer_1064_ramp_end',np.linspace(2.,5.,4))
        self.p.v_pd_tweezer_1064_ramp_end = 3.

        # self.xvar('v_modulation_depth',np.linspace(0.1,1.5,6))
        self.p.v_modulation_depth = 1.25

        self.xvar('freq_tweezer_modulation',np.linspace(10.,100.,50)*1.e3)
        # self.p.freq_tweezer_modulation = 2.95e3

        # self.xvar('t_fm',np.linspace(1.,20.,5)*1.e-3)
        self.p.t_fm = 12.e-3

        self.fm = True

        self.p.t_tweezer_hold = 30.e-3

        self.sh_dds = self.get_device("shuttler0_dds0")
        self.sh_dds: DDS
        self.sh_trigger = self.get_device("shuttler0_trigger")
        self.sh_trigger: Trigger
        self.sh_relay = self.get_device("shuttler0_relay")
        self.sh_relay: Relay
        
        self.finish_build(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.outer_coil.discharge()

        ###
        frequency = self.p.freq_tweezer_modulation

        n0 = shuttler_volt_to_mu(self.p.v_modulation_depth)
        n1 = 0.
        n2 = 0.
        n3 = 0.
        r0 = 0.
        r1 = frequency
        r2 = 0.

        T = 8.e-9
        g = 1.64676
        q0 = n0/g
        q1 = n1/g
        q2 = n2/g
        q3 = n3/g

        b0 = np.int32(q0)
        b1 = np.int32(q1 * T + q2 * T**2 / 2 + q3 * T**3 / 6)
        b2 = np.int64(q2 * T**2 + q3 * T**3)
        b3 = np.int64(q3 * T**3)

        c0 = np.int32(r0)
        c1 = np.int32((r1 * T + r2 * T**2) * T32)
        c2 = np.int32(r2 * T**2)

        self.sh_dds.set_waveform(b0=b0, b1=b1, b2=b2, b3=b3, c0=c0, c1=c1, c2=c2)
        self.sh_trigger.trigger(0b11)

        self.sh_relay.init()
        self.sh_relay.enable(0b00),''

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

        self.release()
        self.switch_d2_3d(0)
        self.switch_d1_3d(0)

        self.flash_cooler()

        self.dds.power_down_cooling()

        self.set_shims(v_zshim_current=self.p.v_zshim_current_magtrap,
                        v_yshim_current=self.p.v_yshim_current_magtrap,
                          v_xshim_current=self.p.v_xshim_current_magtrap)

        # magtrap start
        # self.ttl.pd_scope_trig.pulse(1*us)
        self.inner_coil.on()

        # ramp up lightsheet over magtrap
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)

        for i in self.p.magtrap_ramp_list:
            self.inner_coil.set_current(i_supply=i)
            delay(self.p.dt_magtrap_ramp)

        delay(self.p.t_magtrap)

        self.inner_coil.off()
        
        self.ttl.pd_scope_trig.pulse(1.e-6)

        self.outer_coil.on()
        self.outer_coil.set_voltage(v_supply=70.)
        for i in self.p.feshbach_field_rampup_list:
            self.outer_coil.set_current(i_supply=i)
            delay(self.p.dt_feshbach_field_rampup)
        delay(20.e-3)

        self.lightsheet.ramp_down(t=self.p.t_lightsheet_rampdown)
        
        for i in self.p.feshbach_field_ramp_list:
            self.outer_coil.set_current(i_supply=i)
            delay(self.p.dt_feshbach_field_ramp)
        delay(20.e-3)

        self.tweezer.vva_dac.set(v=0.)
        self.tweezer.on()
        self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp)

        self.lightsheet.ramp_down2(t=self.p.t_lightsheet_rampdown2)
        self.lightsheet.off()

        # turn on modulation
        if self.fm:
            self.sh_relay.enable(0b11)
            delay(self.p.t_fm)
            self.sh_relay.enable(0b00)
        else:
            delay(self.p.t_fm)
        
        delay(self.p.t_tweezer_hold)
        
        # self.ttl.pd_scope_trig.pulse(1.e-6)
        self.outer_coil.off()
        delay(self.p.t_feshbach_field_decay)

        self.tweezer.off()
    
        delay(self.p.t_tof)
        # self.flash_repump()
        self.abs_image()

        self.outer_coil.discharge()

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