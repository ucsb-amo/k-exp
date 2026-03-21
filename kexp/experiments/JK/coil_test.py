from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types
import numpy as np
from kexp.util.artiq.async_print import aprint
# from kexp.control.slm.slm import SLM
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,camera_select='xy_basler',save_data=True)

        # self.xvar('frequency_detuned_imaging',np.arange(250.,450.,8)*1.e6)
        self.p.frequency_detuned_imaging = 290.e6
        self.xvar('beans',[0]*1000)

        # self.xvar('hf_imaging_detuning', [340.e6,420.e6]*1)
        
       

        # self.xvar('beans',[0,1])

        self.p.t_mot_load = 1.
        self.p.N_repeats = 1

        # self.camera_params.amp_imaging = .12
        # self.camera_params.exposure_time = 10.e-6
        # self.p.t_imaging_pulse = self.camera_params.exposure_time

        # self.xvar('amp_imaging',np.linspace(.05,.2,10))
        # self.p.amp_imaging = .15

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.slm.write_phase_mask_kernel()
        self.set_high_field_imaging(i_outer=self.p.i_spin_mixture,
                                    pid_bool=False)
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_imaging)
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)



        # feshbach field on, ramp up to field 1  
        self.outer_coil.on()
        # delay(1.e-3)
        self.outer_coil.set_voltage()
       

        self.dac.supply_current_2dmot.set(v=0.)

        self.outer_coil.ramp_supply(t=120.e-3,
                             i_start=0.,
                             i_end=self.p.i_spin_mixture)
        delay(375.e-3)

        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.ttl.line_trigger.wait_for_line_trigger()

        self.outer_coil.start_pid()
        delay(125.e-3)
        self.ttl.test_trig.pulse(1.e-6)

        delay(175.e-3)

        # self.raman.sweep(t=self.p.t_raman_sweep,
        #                  frequency_center=self.p.f_raman_sweep_center,
        #                  frequency_sweep_fullwidth=self.p.f_raman_sweep_width)

        # self.dds.raman_plus.on()
        # delay(self.p.t_raman_pulse)
        # self.dds.raman_plus.off()


        delay(self.p.t_tof)

        # delay(50.e-3)


        self.outer_coil.stop_pid()
        
        self.outer_coil.off()
        self.outer_coil.discharge()

        self.dac.supply_current_2dmot.set(v=self.p.v_2d_mot_current)

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