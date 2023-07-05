from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential
from kexp.config.dds_id import dds_frame
from kexp.config.expt_params import ExptParams
from kexp.config.camera_params import CameraParams

class Image():
    def __init__(self):
        self.dds = dds_frame()
        self.params = ExptParams()
        self.camera_params = CameraParams()

    @kernel
    def pulse_imaging_light(self,t):
        self.dds.imaging.on()
        delay(t)
        self.dds.imaging.off()

    @kernel
    def pulse_resonant_mot_beams(self,t):
        with parallel:
            self.dds.d2_3d_c.set_dds_gamma(0.)
            self.dds.d2_3d_r.set_dds_gamma(0.)
        with parallel:
            self.dds.d2_3d_c.on()
            self.dds.d2_3d_r.on()
        delay(t)
        with parallel:
            self.dds.d2_3d_c.off()
            self.dds.d2_3d_r.off()

    @kernel
    def trigger_camera(self):
        '''
        Written to pretrigger camera such that the camera exposure begins at the
        timeline cursor position where this is called. Returns the timeline
        cursor to this position after pretrigger.
        '''
        delay(-self.params.t_pretrigger * s)
        self.ttl_camera.pulse(self.params.t_camera_trigger * s)
        t_adv = self.params.t_pretrigger - self.params.t_camera_trigger
        delay(t_adv * s)

    @kernel
    def abs_image(self):
        self.trigger_camera()
        self.pulse_imaging_light(self.params.t_imaging_pulse * s)

        delay(self.params.t_light_only_image_delay * s)
        self.trigger_camera()
        self.pulse_imaging_light(self.params.t_imaging_pulse * s)

        self.dds.imaging.off()
        delay(self.params.t_dark_image_delay * s)
        self.trigger_camera()

    @kernel
    def fl_image(self):

        self.trigger_camera()
        # self.pulse_imaging_light(self.camera_params.exposure_time * s)
        self.pulse_resonant_mot_beams(self.camera_params.exposure_time * s)

        delay(self.params.t_light_only_image_delay * s)
        self.trigger_camera()
        # self.pulse_imaging_light(self.camera_params.exposure_time * s)
        self.pulse_resonant_mot_beams(self.camera_params.exposure_time * s)

