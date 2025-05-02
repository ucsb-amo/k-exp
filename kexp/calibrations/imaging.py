import numpy as np
from artiq.experiment import portable, TFloat

# values from k-jam\analysis\measurements\imaging_frequency_vs_iouter.ipynb

# run 13951
# currents set using transducer (not supply set point)
slope_imaging_frequency_per_i_pid = -4135869.5759812593
yintercept_imaging_frequency_per_i_pid = 162119567.262526

@portable
def high_field_imaging_detuning(i_outer) -> TFloat:
    detuning = slope_imaging_frequency_per_i_pid * i_outer \
      + yintercept_imaging_frequency_per_i_pid
    return detuning