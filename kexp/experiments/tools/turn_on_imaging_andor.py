from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
from kexp.base.cameras import img_config

class turn_on_imaging(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      imaging_type=img_types.ABSORPTION,
                      setup_camera=False)
        
        self.configure_imaging_system(img_config.PID)

        # in case you want to use this to do triggering
        self.ttl.camera = self.ttl.andor 

        self.camera_params = cameras.andor

        self.finish_prepare(shuffle=False)
       
    @kernel
    def run(self):
        self.init_kernel(setup_awg=False,
                         setup_slm=False,
                         init_lightsheet=False,
                         init_shuttler=False)
        
        self.set_imaging_shutters()
        
        frequency_detuned = 380.e6
        v_pd = 6.
        # v_pd = self.camera_params.amp_imaging

        # after running experiment, control power with DAC 'imaging_pid'
        # shutter beam with dds.imaging_x_switch

        self.imaging.set_imaging_detuning(frequency_detuned)
        delay(1.e-3)
        self.imaging.set_power(v_pd)
        self.imaging.on()

        self.imaging.ttl_pid_manual_override.off()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)