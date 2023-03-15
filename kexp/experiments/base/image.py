from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential

@kernel
def pulse_imaging_light(expt,t):
    expt.dds["imaging"].on()
    delay(t)
    expt.dds["imaging"].off()

@kernel
def trigger_camera(expt, params):
    '''
    Written to pretrigger camera such that the camera exposure begins at the
    timeline cursor position where this is called. Returns the timeline
    cursor to this position after pretrigger.
    '''
    delay(-params.t_pretrigger * s)
    expt.ttl_camera.pulse(params.t_camera_trigger * s)
    t_adv = params.t_pretrigger - params.t_camera_trigger
    delay(t_adv * s)

