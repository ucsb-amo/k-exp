import numpy as np
from artiq.experiment import portable, TFloat

# values from k-jam\analysis\measurements\imaging_frequency_vs_iouter.ipynb

# currents set using transducer (not supply set point)

I_LF_HF_THRESHOLD = 150.

# run 22849
# all shims set to zero during feshbach field
slope_imaging_frequency_per_i_transducer_hf = -3272727.2138181804
yintercept_imaging_frequency_per_i_transducer_hf = 11818170.62545603

@portable
def high_field_imaging_detuning(i_transducer) -> TFloat:
    detuning = slope_imaging_frequency_per_i_transducer_hf * i_transducer \
      + yintercept_imaging_frequency_per_i_transducer_hf
    return detuning

# run 23078
# all shims set to zero during feshbach field
# slope_imaging_frequency_per_i_transducer_lf = -8355555.540425534
# yintercept_imaging_frequency_per_i_transducer_lf = 444888888.5787226

# run 23512
# all shims set to zero during feshbach field
slope_imaging_frequency_per_i_transducer_lf = -8509090.922196094
yintercept_imaging_frequency_per_i_transducer_lf = 449781818.3732016

@portable
def low_field_imaging_detuning(i_transducer) -> TFloat:
    detuning = slope_imaging_frequency_per_i_transducer_lf * i_transducer \
      + yintercept_imaging_frequency_per_i_transducer_lf
    return detuning

# run 23397
# all shims set to zero during feshbach field
slope_imaging_frequency_per_i_transducer_lf_pid = -8888888.888888888
yintercept_imaging_frequency_per_i_transducer_lf_pid = 458222222.2222222

@portable
def low_field_pid_imaging_detuning(i_pid) -> TFloat:
  detuning = slope_imaging_frequency_per_i_transducer_lf_pid * i_pid \
      + yintercept_imaging_frequency_per_i_transducer_lf_pid
  return detuning