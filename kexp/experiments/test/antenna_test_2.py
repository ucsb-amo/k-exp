from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
from artiq.coredevice.adf5356 import ADF5356
from artiq.coredevice.mirny import Mirny
import numpy as np

class tof(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler')
        
        self.mirny = ADF5356
        self.mirny_cpld = Mirny

        self.mirny = self.get_device("mirny0_ch0")
        self.mirny_cpld = self.get_device("mirny0_cpld")
        
        # self.xvar('d1_3d_c_delay',np.linspace(1.e3,5.e3,2))
        self.p.freq_mirny_ramp_start = 440.e6
        self.xvar('freq_mirny_ramp_end',np.linspace(450,470,2)*1.e6)
        self.p.t_mirny_ramp = 5
        self.p.N_mirny_ramp = 5
        self.p.dt_mirny_ramp = self.p.t_mirny_ramp / self.p.N_mirny_ramp

        self.finish_prepare(compute_new_derived=self.recompute)

    def recompute(self):
        self.p.freq_mirny_list = np.linspace(self.p.freq_mirny_ramp_start,
                                             self.p.freq_mirny_ramp_end,
                                             self.p.N_mirny_ramp)

    @kernel
    def scan_kernel(self):
        # self.load_2D_mot(self.p.t_2D_mot_load_delay)
        # self.mot(self.p.t_mot_load)
        # self.dds.push.off()
        # self.cmot_d1(self.p.t_d1cmot * s)
        # self.set_shims(v_zshim_current=self.p.v_zshim_current_gm, v_yshim_current=self.p.v_yshim_current_gm, v_xshim_current=self.p.v_xshim_current_gm)
        # self.gm(self.p.t_gm * s)
        # self.gm_ramp(self.p.t_gmramp)

        #turn off repump or cooler
        # self.dds.d1_3d_r.off()
        # delay(self.p.d1_3d_c_delay)
        # self.dds.d1_3d_c.off()
        
        self.release()

        # #Mirny code (since the wrapper class is not written), so we can output and scan rf for antenna using the microwave card
        self.mirny.set_att(20.)  #max output power=Min(5-att+50,43); min attenuation= 12 dB
        self.mirny.set_output_power_mu(3)
        self.mirny.sw.on()
        for f in self.p.freq_mirny_list:
            self.mirny.set_frequency(f)
            delay(self.p.dt_mirny_ramp)
        self.mirny.sw.off()

        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        self.mirny_cpld.init()
        delay(1*ms)
        self.mirny.init()
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)


