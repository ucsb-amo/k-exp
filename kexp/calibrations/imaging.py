import numpy as np
from artiq.experiment import portable, TFloat

# values from k-jam\analysis\measurements\imaging_frequency_vs_iouter.ipynb

# run 14721
# currents set using supply setpoint (known to be offset from real current)
slope_imaging_frequency_per_iouter_current_supply = -4137692.152565028
yintercept_imaging_frequency_per_iouter_current_supply = 184968716.32441515

# run 13951
# currents set using transducer (not supply set point)
slope_imaging_frequency_per_iouter_current_pid = -4263157.982109993
yintercept_imaging_frequency_per_iouter_current_pid = 201333349.9498738

@portable
def high_field_imaging_detuning(i_outer) -> TFloat:
    detuning = slope_imaging_frequency_per_iouter_current_pid * i_outer \
      + yintercept_imaging_frequency_per_iouter_current_pid
    return detuning