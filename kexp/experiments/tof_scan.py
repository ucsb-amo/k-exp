from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class tof_scan(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        self.p.imaging_state = 2.
        # self.xvar('imaging_state',[2,1])

        self.p.t_mot_load = .5

        # self.p.N_repeats = [3]

        # self.xvar('t_mot_load',np.linspace(.1,2.,10))
        
        # self.xvar('i_2d_mot',np.linspace(0.,5.,20))
        # self.xvar('detune_d2_c_2dmot',np.linspace(-2.,0.,6))
        # self.xvar('detune_d2_r_2dmot',np.linspace(-4.,-1.,6))
        # self.xvar('detune_push',np.linspace(-6.,0.,6))
        # self.xvar('amp_push',np.linspace(.04,.188,6))

        # self.xvar('detune_d2_c_mot',np.linspace(-3.,0.,6))
        # self.xvar('detune_d2_r_mot',np.linspace(-5.,-3.,6))
        # self.xvar('amp_d2_c_mot',np.linspace(.05,.188,6))
        # self.xvar('amp_d2_r_mot',np.linspace(.05,.188,6))
        # self.xvar('i_mot',np.linspace(10.,30.,20))
        # self.xvar('v_zshim_current',np.linspace(.3,.8,6))
        # self.xvar('v_xshim_current',np.linspace(2.0,9.5,8))
        # self.xvar('v_yshim_current',np.linspace(7.0,9.99,8))

        # self.xvar('detune_d1_c_d1cmot',np.linspace(8.,12.,6))
        # self.xvar('detune_d2_r_d1cmot',np.linspace(-3.5,-2.,6))
        # self.xvar('pfrac_d1_c_d1cmot',np.linspace(.7,.999,6))
        # self.xvar('amp_d2_r_d1cmot',np.linspace(.03,.05,6))
        # self.xvar('t_d1cmot',np.linspace(1.,15.,8)*1.e-3)
        # self.xvar('i_cmot',np.linspace(15.,35.,8))

        # self.xvar('detune_gm',np.linspace(7,12.,8))
        # self.xvar('t_gm',np.linspace(.05,5.,8)*1.e-3)
        # self.xvar('pfrac_d1_c_gm',np.linspace(.7,.99,8))
        # self.xvar('pfrac_d1_r_gm',np.linspace(.3,.99,8))

        # self.xvar('pfrac_c_gmramp_end',np.linspace(.05,.4,8))
        # self.xvar('pfrac_r_gmramp_end',np.linspace(.03,.4,8))
        # self.xvar('t_gmramp',np.linspace(3.,8.,20)*1.e-3)

        # self.xvar('i_magtrap_init',np.linspace(20.,40.,8))
        # self.xvar('i_magtrap_ramp_end',np.linspace(28.,95.,8))
        # self.xvar('t_magtrap',np.linspace(20.,1500.,8)*1.e-3)
        # self.xvar('t_magtrap_ramp',np.linspace(10.,800.,8)*1.e-3)

        # self.xvar('t_lightsheet_rampup',np.linspace(20.,1500.,8)*1.e-3)
        # self.xvar('t_lightsheet_hold',np.linspace(50.,2000.,20)*1.e-3)
        # self.xvar('v_pd_lightsheet_rampup_end',np.linspace(2.,8.8,8))

        # self.xvar('i_evap1_current',np.linspace(11.,13.,8))
        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(2.,.8,6))
        self.p.v_pd_lightsheet_rampdown_end = 1.4
        # self.xvar('t_lightsheet_rampdown',np.linspace(1.5,.3,8))

        self.p.v_pd_lightsheet_rampdown2_end = 0.32
        # self.xvar('v_pd_lightsheet_rampdown2_end',np.linspace(0.4,0.3,6))

        # self.xvar('t_lightsheet_rampdown2',np.linspace(0.5,1.5,8))
        self.p.t_lightsheet_rampdown2 = 1.1

        self.xvar('i_evap2_current',np.linspace(11.,15.,6))


        # self.xvar('i_magtrap_shim',np.linspace(0.,2.,20))

        self.xvar('t_tof',np.linspace(10.,800.,6)*1.e-6)

        # self.p.i_magtrap_ramp_end = 47.
        
        # self.p.t_tof = 50.e-6

        # self.p.t_magtrap = 200.e-3

        # self.p.n_lightsheet_rampup_steps = 100

        # self.p.t_lightsheet_rampup = 200.e-3
        self.p.t_lightsheet_hold = 50.e-3
        
        # self.xvar('dummy',[0]*5)
        
        # self.p.v_pd_lightsheet_rampup_end = 0.638

        self.p.N_repeats = 1

        self.finish_build(shuffle=True)

    @kernel
    def scan_kernel(self):
        self.dds.init_cooling()

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.inner_coil.set_current(i_supply=self.p.i_magtrap_init)

        self.set_shims(v_zshim_current=self.p.v_zshim_current_gm,
                        v_yshim_current=self.p.v_yshim_current_gm,
                          v_xshim_current=self.p.v_xshim_current_gm)
        self.gm(self.p.t_gm * s)

        self.ttl.pd_scope_trig.on()
        self.gm_ramp(self.p.t_gmramp)

        # self.release()
        self.switch_d2_3d(0)
        self.switch_d1_3d(0)

        self.flash_cooler()

        self.dds.power_down_cooling()

        self.set_shims(v_zshim_current=0.,
                        v_yshim_current=self.p.v_yshim_current_gm,
                          v_xshim_current=self.p.v_xshim_current_gm)

        # magtrap start
        self.inner_coil.igbt_ttl.on()

        # ramp up lightsheet over magtrap
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)

        for i in self.p.magtrap_ramp_list:
            self.inner_coil.set_current(i_supply=i)
            delay(self.p.dt_magtrap_ramp)
        
        self.outer_coil.set_current(i_supply=self.p.i_evap1_current)
        self.outer_coil.set_voltage(v_supply=9.)
        delay(self.p.t_magtrap)

        self.inner_coil.off()

        # delay(self.p.t_lightsheet_hold)

        self.outer_coil.on(i_supply=self.p.i_evap1_current)
        delay(20.e-3)
        self.lightsheet.ramp_down(t=self.p.t_lightsheet_rampdown)

        self.outer_coil.set_current(i_supply=self.p.i_evap2_current)
        delay(20.e-3)
        self.lightsheet.ramp_down2(t=self.p.t_lightsheet_rampdown2)

        self.outer_coil.off()
        self.ttl.pd_scope_trig.off()
        delay(1.5e-3)

        self.lightsheet.off()
    
        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()

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