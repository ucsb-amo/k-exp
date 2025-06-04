import numpy as np


from kexp.control.slm.slm import SLM

slm = SLM()

slm.write_phase_mask(
    dimension = 177,
    phase = 1.72,
    x_center = 250,
    y_center = 400,
    mask_type = "find"
)