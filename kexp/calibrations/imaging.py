import numpy as np
from artiq.experiment import portable, TFloat

# values from k-jam\analysis\measurements\imaging_frequency_vs_iouter.ipynb

# run 22166
# currents set using transducer (not supply set point)
slope_imaging_frequency_per_i_transducer = -2399999.9357619714
yintercept_imaging_frequency_per_i_transducer = -71857154.93524233

@portable
def high_field_imaging_detuning(i_transducer) -> TFloat:
    detuning = slope_imaging_frequency_per_i_transducer * i_transducer \
      + yintercept_imaging_frequency_per_i_transducer
    return detuning