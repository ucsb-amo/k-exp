import numpy as np
from artiq.experiment import portable, TFloat

@portable
def high_field_imaging_detuning(i_outer) -> TFloat:
    # values from k-jam\analysis\measurements\imaging_frequency_vs_iouter.ipynb
    # current values from runID 10735
    slope_imaging_frequency_per_iouter_current = 986259.0013349565
    yintercept_imaging_frequency_per_iouter_current = 235851195.68433574
    detuning = slope_imaging_frequency_per_iouter_current * i_outer \
          + yintercept_imaging_frequency_per_iouter_current
    return detuning