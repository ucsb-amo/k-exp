from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from kexp.calibrations.magnets import compute_pid_overhead

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,save_data=False)

        self.xvar('dummy',[0]*1000)

        self.finish_prepare(shuffle=False)

    @kernel
    def start_pid_fake(self, i_pid):
        i_start = i_pid
        i_end = i_pid + compute_pid_overhead(i_pid)
        t_ramp = 50.e-3
        n_steps = 50
        delta_i = (i_end - i_start)/(n_steps-1)
        dt = t_ramp / n_steps
        for j in range(n_steps):
            self.outer_coil.set_supply( i_start + delta_i * j )
            delay(dt)
        delay(30.e-3)

    @kernel
    def scan_kernel(self):

        i = 16.

        # feshbach field on, ramp up to field 1  
        self.outer_coil.on()
        self.outer_coil.set_voltage()

        self.outer_coil.ramp_supply(t=100.e-3,i_start=0.,i_end=i)
        delay(100.e-3)
        # self.outer_coil.start_pid()
        # self.start_pid_fake(i)
        # delay(80.e-3)

        #self.outer_coil.start_pid(i_pid=0.)

        self.outer_coil.set_pid(i_pid=i)

        self.ttl.pd_scope_trig.pulse(1.e-6)
        
        self.outer_coil.pid_ttl.on()

        self.outer_coil.ramp_supply(t=100.e-3,i_end=i+compute_pid_overhead(i))

        # self.outer_coil.set_supply(i_supply=18.) # pid will eat all of this as it ramps
        # delay(200.e-3)
        # self.ttl.pd_scope_trig.pulse(1.e-6)
        # self.outer_coil.start_pid_no_overhead(i_pid = 18.)
        # self.outer_coil.ramp_supply(t=100.e-3,i_start=18.,i_end=26.)


        # self.outer_coil.pid_ttl.on()

        # 
        # self.outer_coil.ramp_pid(t=self.p.t_feshbach_field_rampup,
        #                      i_start=0.,
        #                      i_end=self.p.i_lf_lightsheet_evap1_current)
        
        # delay(60.e-3)
        # delay(150.e-3)
        delay(800.e-3)
        # delay(2.)
        # self.ttl.pd_scope_trig.pulse(1.e-6)
        self.outer_coil.stop_pid()
        # self.outer_coil.pid_ttl.off()
        # delay(4.)
        self.outer_coil.off()
        self.outer_coil.discharge()

    @kernel
    def run(self):
        self.init_kernel(setup_awg=False,
                         dds_off=False,
                         dds_set=False,
                         init_shuttler=False,
                         init_lightsheet=False)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)