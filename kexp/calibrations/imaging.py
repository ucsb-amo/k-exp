import numpy as np
from artiq.experiment import portable, TFloat

@portable
def high_field_imaging_detuning(i_outer) -> TFloat:
    # values from k-jam\analysis\measurements\imaging_frequency_vs_iouter.ipynb
    # current values from runID 14721
    slope_imaging_frequency_per_iouter_current = -4137692.152565028
    yintercept_imaging_frequency_per_iouter_current = 184968716.32441515
    detuning = slope_imaging_frequency_per_iouter_current * i_outer \
          + yintercept_imaging_frequency_per_iouter_current
    return detuning

@portable
def low_field_imaging_detuning(i_outer) -> TFloat:
    # values from k-jam\analysis\measurements\imaging_frequency_vs_iouter.ipynb
    # current values from runID 14721
    slope_imaging_frequency_per_iouter_current = -4137692.152565028
    yintercept_imaging_frequency_per_iouter_current = 184968716.32441515
    detuning = slope_imaging_frequency_per_iouter_current * i_outer \
          + yintercept_imaging_frequency_per_iouter_current
    return detuning