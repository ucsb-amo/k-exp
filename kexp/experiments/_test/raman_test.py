from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class mot_killa(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        self.p.imaging_state = 1
        # self.xvar('beans',[0]*300)

        # self.xvar('evap1_current',np.linspace(19.65,19.80,30))
        # self.p.i_evap1_current = 33.12 # -1 to -1
        self.p.i_evap1_current = 19.73 # -1 to 0

        self.xvar('t_raman_pulse',np.linspace(1.,1000.,60)*1.e-6)
        # self.p.t_raman_pulse = 500.e-6
        self.p.f_raman_transition = 445.997e6

        # self.xvar('f_raman_sweep_center',np.linspace(445.9e6,446.1e6,30))
        self.p.t_raman_sweep = 30.e-3
        # self.p.f_raman_sweep_center = 
        self.p.f_raman_sweep_width = 7.e3

        self.p.t_tof = 10.e-6

        self.p.t_mot_load = 1.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        # self.set_imaging_detuning(frequency_detuned=self.p.detuning_dispersive_imaging)
        # self.set_high_field_imaging(i_outer=self.p.i_evap1_current)
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

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
        
        self.raman.pulse(t=self.p.t_raman_pulse,frequency_transition=self.p.f_raman_transition)
        # self.raman.sweep(t=self.p.t_raman_sweep,frequency_center=self.p.f_raman_sweep_center,frequency_sweep_fullwidth=self.p.f_raman_sweep_width)
        
        
        self.outer_coil.snap_off()
        delay(5.e-3)

        self.lightsheet.off()
    
        delay(self.p.t_tof)
        # self.flash_repump()
        self.abs_image()

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