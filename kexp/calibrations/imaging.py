import numpy as np
from artiq.experiment import portable, TFloat

# values from k-jam\analysis\measurements\imaging_frequency_vs_iouter.ipynb

# currents set using transducer (not supply set point)

# run 22166
# slope_imaging_frequency_per_i_transducer = -2399999.9357619714
# yintercept_imaging_frequency_per_i_transducer = -71857154.93524233

# run 22849
slope_imaging_frequency_per_i_transducer = -3272727.2138181804
yintercept_imaging_frequency_per_i_transducer = 11818170.62545603

@portable
def high_field_imaging_detuning(i_transducer) -> TFloat:
    detuning = slope_imaging_frequency_per_i_transducer * i_transducer \
      + yintercept_imaging_frequency_per_i_transducer
    return detuning