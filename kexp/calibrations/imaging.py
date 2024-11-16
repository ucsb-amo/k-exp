import numpy as np
from artiq.experiment import portable, TFloat

# run 14721
# currents set using supply setpoint (known to be offset from real current)
slope_imaging_frequency_per_iouter_current_supply = -4137692.152565028
yintercept_imaging_frequency_per_iouter_current_supply = 184968716.32441515

# run 13951
# currents set using transducer (not supply set point)
slope_imaging_frequency_per_iouter_current_pid = -4156249.9999999697
yintercept_imaging_frequency_per_iouter_current_pid = 204874999.99999326

@portable
def high_field_imaging_detuning(i_outer) -> TFloat:
    # values from k-jam\analysis\measurements\imaging_frequency_vs_iouter.ipynb
    detuning = slope_imaging_frequency_per_iouter_current_pid * i_outer \
      + yintercept_imaging_frequency_per_iouter_current_pid
    return detuning