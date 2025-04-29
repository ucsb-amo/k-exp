import numpy as np

# print("Hi")

from kexp.control.slm.slm import SLM

# Create an instance of the SLM class
slm = SLM()

# Call the method with test parameters
slm.write_phase_spot(
    diameter = 177,
    phase = 1.72,
    x_center = 250,
    y_center = 400
)