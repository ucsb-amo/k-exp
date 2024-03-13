from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
# from artiq.coredevice.adf5356 import ADF5356
# from artiq.coredevice.mirny import Mirny
import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler')
        
        # self.mirny = ADF5356
        # self.mirny_cpld = Mirny

        # self.mirny = self.get_device("mirny0_ch0")
        # self.mirny_cpld = self.get_device("mirny0_cpld")

        # self.xvar('detune_push',np.linspace(-4.,4.,5))
        # self.xvar('amp_push',np.linspace(.05,.188,5))

        # self.xvar('detune_d2_c_mot',np.linspace(-3.,0.,5))
        # self.xvar('detune_d2_r_mot',np.linspace(-5.,-3.,5))
        # self.xvar('i_mot',np.linspace(22.,25.,5))
        # self.xvar('v_zshim_current',np.linspace(.0,1.,5))
        # self.xvar('v_xshim_current',np.linspace(.0,2.,5))
        # self.xvar('v_yshim_current',np.linspace(.0,2.,5))

        # self.xvar('v_zshim_current_gm',np.linspace(.7,1.,10))
        # self.xvar('v_xshim_current_gm',np.linspace(.0,2.,5))
        # self.xvar('pfrac_c_gmramp_end',np.linspace(.2,.7,5))
        # self.xvar('pfrac_r_gmramp_end',np.linspace(.1,.4,5))
        # self.xvar('pfrac_d1_c_gm',np.linspace(.4,.9,5))
        # self.xvar('pfrac_d1_r_gm',np.linspace(.3,.5,5))
        # self.xvar('t_gm',np.linspace(1.,8.,5)*1.e-3)
        # self.xvar('t_gmramp',np.linspace(3.,9.,5)*1.e-3)
        
        self.xvar('d1_3d_c_delay',np.linspace(1.e3,5.e3,2))
        # self.xvar('t_tweezer_1064_ramp',np.linspace(4.,20.,7)*1.e-3)
        
        # self.xvar('t_tof',np.linspace(100,10000,6)*1.e-6)
        # self.xvar('t_tweezer_hold',np.linspace(1000,15000,5)*1.e-6)
        # self.xvar('t_lightsheet_hold',np.linspace(5000,40000,5)*1.e-6)

        self.p.t_mot_load = 1.
        self.p.t_tof = 20.e-6
        # self.p.N_repeats = 3

        # self.p.amp_imaging_abs = 0.5

        self.finish_build()

    @kernel
    def scan_kernel(self):
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        self.set_shims(v_zshim_current=self.p.v_zshim_current_gm, v_yshim_current=self.p.v_yshim_current_gm, v_xshim_current=self.p.v_xshim_current_gm)
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        #turn off repump or cooler
        self.dds.d1_3d_r.off()
        delay(self.p.d1_3d_c_delay)
        self.dds.d1_3d_c.off()
        
        self.release()

        # self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
        # delay(self.p.t_lightsheet_hold)

        # #Mirny code (since the wrapper class is not written), so we can output and scan rf for antenna using the microwave card
        # self.mirny.set_att(20.)  #max output power=Min(5-att+50,43); min attenuation= 12 dB
        # self.mirny.set_output_power_mu(3)
        # self.mirny.sw.on()
        # self.mirny.set_frequency(460.e6)
        # delay(2*s)
        # self.mirny.sw.off()

        # self.lightsheet.off()



        # self.tweezer.on()
        

        # self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp)
        # delay(self.p.t_tweezer_hold)
        # self.tweezer.off()

        # self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
        # delay(20.e-3)
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp)
        # self.lightsheet.off()
        # delay(self.p.t_tweezer_hold)
        # self.tweezer.off()

        #

        # self.release()

        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()

        # self.tweezer.off()

    @kernel
    def run(self):
        self.init_kernel()
        # self.mirny_cpld.init()
        # delay(1*ms)
        # self.mirny.init()
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)


