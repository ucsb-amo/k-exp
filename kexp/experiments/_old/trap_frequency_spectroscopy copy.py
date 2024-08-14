from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from artiq.language.core import now_mu

class trap_frequency_spectroscopy(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        self.p.imaging_state = 1.
        self.p.t_mot_load = 1.

        self.p.t_tof = 4.e-6

        self.camera_params.amp_imaging = 0.09
        self.camera_params.exposure_time = 12.e-6
        self.params.t_imaging_pulse = self.camera_params.exposure_time

        self.p.v_pd_lightsheet_rampdown_end = 6.

        self.p.frequency_tweezer_list = [self.p.frequency_aod_center,0.,0.]
        self.p.amp_tweezer_list = [0.2,0.,0.]
       
        self.xvar('freq_tweezer_modulation',np.linspace(4.,8.,20)*1.e3)

        self.p.t_tweezer_hold = 50.e-3

        self.p.N_repeats = 1

        import vxi11
        self.awg = vxi11.Instrument("192.168.1.91")
        
        self.finish_prepare(shuffle=True)

    def set_awg_fm_frequency(self,freq_fm,freq_fm_mod_depth=1.e6):
        # self.awg.write(f"C1:MDWV CARR,DEVI,{freq_fm_mod_depth:1.0f}")
        self.awg.write(f"C2:MDWV CARR,FRQ,{freq_fm:1.0f}")

    @kernel
    def scan_kernel(self):

        self.core.wait_until_mu(now_mu())
        self.set_awg_fm_frequency(freq_fm=self.p.freq_tweezer_modulation)
        delay(50*ms)

        # kill modulation
        self.dac.fm_tweezer.set(-9.99)

        # self.core.wait_until_mu(now_mu())
        # self.setup_tweezers()
        # self.core.break_realtime()

        # self.tweezer.awg_trg_ttl.pulse(t=1.e-6)
        # self.tweezer.pid_int_hold_zero.on()

        #####
        # freq_tweezer_mod_list = self.p.frequency_aod_center \
        #     + self.p.freq_tweezer_modulation * np.array([-1., 0., 1.])
        # # amp_tweezer_mod_list = [0.02,0.2,0.02]
        # amp_tweezer_mod_list = [0.2,0.2,0.2]

        # self.core.wait_until_mu(now_mu())
        # self.tweezer.set_static_tweezers(freq_tweezer_mod_list, amp_tweezer_mod_list)
        # self.core.break_realtime()
        ####

        # self.tweezer.awg_trg_ttl.pulse(t=1.e-6)

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
        self.ttl.pd_scope_trig.pulse(1*us)
        self.inner_coil.on()

        # ramp up lightsheet over magtrap
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)

        for i in self.p.magtrap_ramp_list:
            self.inner_coil.set_current(i_supply=i)
            delay(self.p.dt_magtrap_ramp)
        
        self.outer_coil.set_current(i_supply=self.p.i_feshbach_field_rampup_start)
        self.outer_coil.set_voltage(v_supply=70.)

        delay(self.p.t_magtrap)

        self.inner_coil.off()

        # delay(self.p.t_lightsheet_hold)
        
        self.outer_coil.on()

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
        delay(10*ms)

        # turn on modulation
        self.dac.fm_tweezer.set(9.99)
        
        delay(self.p.t_tweezer_hold)
        
        self.ttl.pd_scope_trig.on()
        self.outer_coil.off()
        delay(self.p.t_feshbach_field_decay)
        self.ttl.pd_scope_trig.off()

        self.tweezer.off()
    
        delay(self.p.t_tof)
        # self.flash_repump()
        self.abs_image()

        # self.outer_coil.off()

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