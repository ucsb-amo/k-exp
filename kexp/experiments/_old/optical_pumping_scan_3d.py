from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

from kexp.util.artiq.async_print import aprint

import numpy as np

class scan_optical_pumping(EnvExperiment, Base):

    def prepare(self):
        # Base.__init__(self,setup_camera=True,andor_imaging=False,absorption_image=False)
        Base.__init__(self)

        self.run_info._run_description = "scan optical pumping detuning, amplitude"

        ## Parameters

        self.p = self.params

        self.p.N_repeats = [1,1,1]

        self.p.t_tof = 10 * 1.e-6 # gm

        self.p.t_mot_load = 1.5

        self.p.imaging_state = [1,2]
        # self.p.xvar_t_op = np.linspace(0.,30.,3) * 1.e-6
        # self.p.xvar_amp_optical_pumping_op = np.linspace(0.0,0.3,3)
        self.p.amp_optical_pumping_op = 0.3
        # self.p.xvar_amp_optical_pumping_r_op = np.linspace(0.0,0.3,5)
        self.p.amp_optical_pumping_r_op = 0.3

        # self.p.t_optical_pumping = 200.e-6
        self.p.t_optical_pumping = np.linspace(0.,2.,10) * 1.e-6
        self.p.t_total = np.max(self.p.t_optical_pumping)

        self.p.put_on_bias_field = [0,1]

        # self.p.t_total = np.max(self.p.t_optical_pumping)
        # self.xvarnames = ['xvar_amp_optical_pumping_op','t_optical_pumping','imaging_state']
        # self.xvarnames = ['xvar_amp_optical_pumping_op','xvar_amp_optical_pumping_r_op','imaging_state']
        self.xvarnames = ['put_on_bias_field','t_optical_pumping','imaging_state']

        self.finish_prepare()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.camera_params.connection_delay*s)
        
        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

        # for do_optical_pumping in self.p.quantization_field_bool:
        for put_on_bias_field in self.p.put_on_bias_field:
            for t_op in self.p.t_optical_pumping:
                for img_state in self.p.imaging_state:

                    if put_on_bias_field:
                        v_zshim = self.p.v_zshim_current_op
                    else:
                        v_zshim = self.p.v_zshim_current

                    if img_state == 1:
                         self.set_imaging_detuning(detuning=self.p.frequency_detuned_imaging_F1) 
                    elif img_state == 2:
                         self.set_imaging_detuning()

                    self.mot(self.p.t_mot_load * s)
                    self.dds.push.off()
                    self.cmot_d1(self.p.t_d1cmot * s)
                    self.gm(self.p.t_gm * s)
                    self.gm_ramp(self.p.t_gmramp * s)
                    self.release()

                    self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
                    # delay(10.e-3)

                    self.set_zshim_magnet_current(v=v_zshim)

                    delay(50*ms) 

                    self.lightsheet.off()

                    self.optical_pumping(t=t_op,t_bias_rampup=0.,
                                         v_zshim_current=v_zshim)
                    # self.optical_pumping(t=self.p.t_optical_pumping,t_bias_rampup=0.,
                    #                      amp_optical_pumping=xvar1,
                    #                      amp_optical_pumping_r=xvar2,
                    #                      v_zshim_current=self.p.v_zshim_current_op)
                    # if do_optical_pumping:
                    #     self.optical_pumping(t=t_op,t_bias_rampup=0.,v_zshim_current=self.p.v_zshim_current_op)
                    # else:
                    #     self.optical_pumping(t=t_op,t_bias_rampup=0.,v_zshim_current=self.p.v_zshim_current)

                    delay(self.p.t_total - t_op)
                    
                    ### abs img
                    delay(self.p.t_tof * s)
                    self.abs_image()

                    self.core.break_realtime()
                    delay(1.e-3)
                    self.set_zshim_magnet_current()

                    delay(self.p.t_recover)

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        import os
        expt_filepath = os.path.abspath(__file__)
        self.ds.save_data(self, expt_filepath)

        print("Done!")