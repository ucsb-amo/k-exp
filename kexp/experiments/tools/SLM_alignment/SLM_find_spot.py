from artiq.experiment import *
from artiq.experiment import delay

import numpy as np

from waxx.util.artiq.async_print import aprint

from kexp import Base, cameras, img_types

# SLM.write_phase_spot(100e-6,3.14,960,200)
class gm_tof(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select='andor',
                      imaging_type=img_types.ABSORPTION)

        N = 11
        self.xvar('px_slm_phase_mask_position_x',1036 + np.linspace(-10.,10.,N,dtype=int))
        self.xvar('px_slm_phase_mask_position_y',837 + np.linspace(-10.,10.,N,dtype=int))
        # self.xvar('dimension_slm_mask', np.arange(10.,200.,10,dtype=int)*1e-6)
        # self.xvar('dumdum',[0]*3)
        # self.p.slm_mask = 'spot'
        self.p.phase_slm_mask = np.pi
        self.p.dimension_slm_mask = 10e-6
        # self.p.px_slm_phase_mask_position_x = 1040
        # self.p.px_slm_phase_mask_position_y = 821
        # self.camera_params.exposure_time = 100.e-6
        self.p.amp_imaging = .5
        self.p.N_repeats = 1
        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)
        self.slm.write_phase_mask_kernel()

        self.light_image()

        delay(self.camera_params.t_light_only_image_delay+0.001)
        self.slm.write_phase_mask_kernel(0.,0.)
        self.light_image()

        self.close_imaging_shutters()
        delay(10.e-3)

        delay(self.camera_params.t_dark_image_delay+0.001)
        self.dark_image()
       
    @kernel
    def run(self):
        self.init_kernel(setup_awg=False)
        
        self.scan()

        # self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)