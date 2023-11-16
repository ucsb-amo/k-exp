from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp.base.base import Base
import numpy as np

dv = 100.
dvlist = np.linspace(1.,1.,5)

class tof_scan_gm(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "cmot tof, vary cmot time"

        ## Parameters

        self.p = self.params

        self.p.t_tof = 10.e-6 * s

        self.p.cmot_ramp_steps = 50
        self.p.cmot_ramp_start = self.p.v_mot_current
        self.p.cmot_ramp_end = np.linspace(self.p.cmot_ramp_start,1.2,6)
        self.p.cmot_ramp_time = np.linspace(1,5,6) * 1.e-3
        self.p.dt_cmot_ramp = self.p.cmot_ramp_time / self.p.cmot_ramp_steps
        
        self.p.cmot_ramp_v_values = np.zeros(
            (len(self.p.cmot_ramp_end),
             self.p.cmot_ramp_steps))
        idx = 0
        for v in self.p.cmot_ramp_end:
            self.p.cmot_ramp_v_values[idx,:] = np.linspace(
                self.p.cmot_ramp_start, v, self.p.cmot_ramp_steps)
            idx += 1

        #GM Detunings

        # self.p.xvar_detune_gm = np.linspace(7.5,10.,6)

        # self.p.xvar_v_pd_d1_r_gm = np.linspace(4.0,5.,5)
        # self.p.xvar_t_gm = np.linspace(1.0,10.0,6) * 1.e-3

        # self.p.xvar_n_gmramp_steps = np.linspace(10,200,5) * 1.e-6

        # self.p.xvar_v_d1cmot_current = np.linspace(0.3,1.3,6)

        # self.p.xvar_t_gmramp = np.linspace(4.,10.,6) * 1.e-3

        # self.p.xvar_v_d2cmot_current = np.linspace(0.7,1.5,6)

        # self.xvar_v_d1cmot_current = np.linspace(0.03,.07,5)
        
        # self.p.xvar_v_pd_d1_c_d1cmot = np.linspace(3.,6.0,6)

        # self.p.xvar_t_d2cmot = np.linspace(1.,30.0,6) * 1.e-3

        # self.p.xvar_t_d1cmot = np.linspace(2.,15.0,6) * 1.e-3

        self.xvarnames = ['cmot_ramp_end','cmot_ramp_time']
        self.p.N_repeats = [1,1]

        self.trig_ttl2 = self.get_device("ttl8")

        self.finish_build(shuffle=False)

    @kernel
    def cmot_d1_ramp(self,dt,v_current,
            detune_d1_c = dv,
            v_pd_d1_c = dv,
            detune_d2_r = dv,
            amp_d2_r = dv):
        
        ### Start Defaults ###
        if detune_d1_c == dv:
            detune_d1_c = self.params.detune_d1_c_d1cmot
        if v_pd_d1_c == dv:
            v_pd_d1_c = self.params.v_pd_d1_c_d1cmot
        if detune_d2_r == dv:
            detune_d2_r = self.params.detune_d2_r_d1cmot
        if amp_d2_r == dv:
            amp_d2_r = self.params.amp_d2_r_d1cmot
        ### End Defaults ###

        self.dds.d1_3d_c.set_dds_gamma(delta=detune_d1_c,
                                       v_pd=v_pd_d1_c)
        delay_mu(self.params.t_rtio_mu)
        self.dds.d2_3d_r.set_dds_gamma(delta=detune_d2_r,
                                       amplitude=amp_d2_r)

        # with parallel:
        self.dds.d2_3d_r.on()
        self.dds.d1_3d_c.on()
        delay_mu(self.params.t_rtio_mu)
        self.dds.d2_3d_c.off()
        self.dds.d1_3d_r.off()
        for v in v_current:
            self.set_magnet_current(v)
            delay(dt)

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait * s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for idx in range(len(self.p.cmot_ramp_end)):
            cmot_values = self.p.cmot_ramp_v_values[idx]
            for idx2 in range(len(self.p.cmot_ramp_time)):
                dt = self.p.dt_cmot_ramp[idx2]

                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s)

                self.trig_ttl2.on()
                for v in cmot_values:
                    self.set_magnet_current(v)
                    delay(dt)
                self.trig_ttl2.off()

                self.dds.push.off()
                self.switch_d2_2d(0)

                self.cmot_d1(self.p.t_d1cmot)

                # self.cmot_d2(self.p.t_d2cmot * s)

                # self.trig_ttl2.on()
                # self.cmot_d1_ramp(dt=dt,v_current=cmot_values)
                # self.trig_ttl2.off()

                # self.trig_ttl.on()
                self.gm(self.p.t_gm * s)

                self.gm_ramp(t_gmramp=self.p.t_gmramp)
                # self.trig_ttl.off()
                
                self.release()

                self.dds.lightsheet.on()

                ### GM 2 ###
                self.gm(2.e-3, detune_d1=10., v_pd_d1_c=5., v_pd_d1_r=3.5)
                self.trig_ttl.off()

                self.release()

                # self.pulse_resonant_mot_beams(1.e-6*s)

                delay(self.p.t_lightsheet_hold)
                self.dds.lightsheet.off()
                
                ### abs img
                delay(self.p.t_tof * s)
                self.flash_repump()
                self.abs_image()

                self.core.break_realtime()

        # return to mot load state
        self.mot_observe()

    def analyze(self):

        # self.p.v_pd_d1_r_gm = self.p.xvar_v_pd_d1_r_gm

        # self.p.t_gmramp = self.p.xvar_t_gmramp

        # self.p.t_gm = self.p.xvar_t_gm

        # self.detune_gm = self.p.xvar_detune_gm

        # self.p.v_d2cmot_current = self.p.xvar_v_d2cmot_current 

        # self.p.v_d1cmot_current = self.p.xvar_v_d1cmot_current

        # self.p.v_pd_d1_c_d1cmot = self.p.xvar_v_pd_d1_c_d1cmot

        # self.p.t_d1cmot = self.p.xvar_t_d1cmot

        self.camera.Close()
        
        self.ds.save_data(self)

        print("Done!")
