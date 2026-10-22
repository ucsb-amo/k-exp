from artiq.experiment import *
from artiq.experiment import delay
import numpy as np
from kexp.calibrations import high_field_imaging_detuning
from kexp import Base, img_types, cameras, aprint

class hf_lightsheet_bec_rydberg(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      setup_camera=True,
                      save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION,
                      warmup_shots=0)

        self.p.t_tof = 2000.e-6
        # self.xvar('t_tof',np.linspace(100.,4800.,9)*1.e-6)

        self.p.t_mot_load = 1.

        # lightsheet evap (from JK/hf_lightsheet_evap.py)
        self.p.i_hf_lightsheet_evap1_current = 193.15
        # self.xvar('i_hf_lightsheet_evap1_current',np.linspace(192.3,193.3,8))
        self.p.v_pd_hf_lightsheet_rampdown_end = 1.
        # self.xvar('v_pd_hf_lightsheet_rampdown_end',np.linspace(0.5,2.,8))

        self.p.i_hf_lightsheet_evap2_current = 192.9
                # self.xvar('i_hf_lightsheet_evap2_current',np.linspace(192.7,193.6,8))
        
        self.p.t_hf_lightsheet_rampdown2 = 1.2
                # self.xvar('t_hf_lightsheet_rampdown2',np.geomspace(0.34,3.0,8))
        
        self.p.v_pd_hf_lightsheet_rampdown2_end = 0.185
        # self.xvar('v_pd_hf_lightsheet_rampdown2_end',np.linspace(0.19,0.23,7))

        # rydberg (from HF_experiments/Rydberg/hf_bec_rydberg_scan.py)
        # self.xvar('do_405_pulse',[0,1])
        self.p.do_405_pulse = 1
        # self.xvar('do_980_pulse',[0,1])
        self.p.do_980_pulse = 1
        self.p.amp_dds_405 = 0.07

        self.p.hf_imaging_detuning = -568.e6 

        self.xvar('frequency_eo_980', np.linspace(470.,499.,7)*1.e6)
        self.p.frequency_eo_980 = 422.7e6

        self.p.v_pd_ry_405 = 0.8
        self.p.v_pd_ry_980 = 2.8

        # rydberg beams are on for the whole lightsheet hold
        # self.xvar('t_lightsheet_hold', np.linspace(0.0, 600.0, 7) * 1.e-3)
        self.p.t_lightsheet_hold = 512.e-3

        self.p.N_repeats = 1
        self.finish_prepare(shuffle=True)

        if self.p.do_405_pulse == 1:
            print(f'doing 405 pulse')
        else:
            print(f'not doing 405 pulse')
        if self.p.do_980_pulse == 1:
            print(f'doing 980 pulse')
        else:
            print(f'not doing 980 pulse')

    @kernel
    def scan_kernel(self):

        # self.set_imaging_detuning(frequency_detuned=self.p.hf_imaging_detuning)
        f0 = high_field_imaging_detuning(self.p.i_hf_lightsheet_evap2_current)
        self.set_imaging_detuning(f0)

        self.ry_405.set_power(self.p.v_pd_ry_405)
        self.ry_980.set_power(self.p.v_pd_ry_980)
        self.ttl.ry_intensity_pid_clear.pulse(10.e-6)

        if self.p.do_980_pulse == 1:
            self.ry_980.sweep_to(self.p.frequency_eo_980)

        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)

        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False,do_magtrap_rampdown=True)

        # feshbach field on, ramp up to field 1
        self.outer_coil.on()
        self.outer_coil.set_voltage()

        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_hf_lightsheet_evap1_current)

        self.set_shims(0.,0.,0.)
        self.ttl.pd_scope_trig.pulse(1.e-6)

        # lightsheet evap 1
        self.lightsheet.exponential_ramp(t=self.p.t_hf_lightsheet_rampdown,
                             v_start=self.p.v_pd_lightsheet_rampup_end,
                             v_end=self.p.v_pd_hf_lightsheet_rampdown_end)

        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_hf_lightsheet_evap1_current,
                             i_end=self.p.i_hf_lightsheet_evap2_current)

        # lightsheet evap 2
        self.lightsheet.exponential_ramp(t=self.p.t_hf_lightsheet_rampdown2,
                             v_start=self.p.v_pd_hf_lightsheet_rampdown_end,
                             v_end=self.p.v_pd_hf_lightsheet_rampdown2_end)

        # self.outer_coil.ramp_supply(t=20.e-3,
        #                              i_end=self.p.i_hf_raman)

                
        # self.outer_coil.start_pid()
                
        delay(30.e-3)
                

        # rydberg beams on the lightsheet BEC
        if self.p.do_405_pulse == 1:
            self.ry_405.reboot()
            self.ry_405.dds_sw.set_dds(amplitude=self.p.amp_dds_405)
            self.ry_405.on()
        if self.p.do_980_pulse == 1:
            self.ry_980.on()

        delay(self.p.t_lightsheet_hold)

        self.ry_405.off()
        self.ry_980.off()
        self.ry_405.ttl_shutter.off()

        delay(40e-3)

        self.lightsheet.off()

        delay(self.p.t_tof)

        self.abs_image()

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
