from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential

class image():
    def __init__():
        pass

    @kernel
    def pulse_imaging_light(self,t):
        self.dds.get("imaging").on()
        delay(t)
        self.dds.get("imaging").off()

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

