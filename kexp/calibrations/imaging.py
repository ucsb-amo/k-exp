import numpy as np
from artiq.experiment import portable, TFloat

# values from k-jam\analysis\measurements\imaging_frequency_vs_iouter.ipynb

# currents set using transducer (not supply set point)

I_LF_HF_THRESHOLD = 45.

######

# Ramsey phase-jump light-shift calibration.
# Source notebook: k-jam/analysis/artisinal/lightshift_via_ramsey_phase_jump_vs_img_amp.ipynb
# Model: frequency_lightshift(amp_imaging) = m * amp_imaging + b
@portable
def imaging_lightshift(amp_imaging) -> TFloat:
   # source run id: 64264
   lightshift_slope_Hz_per_amp = 60236.37824283179
   lightshift_intercept_Hz = -3369.647852307185
   return lightshift_slope_Hz_per_amp * amp_imaging + lightshift_intercept_Hz

######

# source notebook; k-jam\analysis\measurements\integrated_apd_calibration_vs_state.ipynb
def integrator_calibration(amp_imaging, t_imaging):

   # notes: https://docs.google.com/document/d/11tzbmMhPQ-lycEPc1OWHo9MnWyrR9bsQly9bz8DF_WQ/edit?tab=t.cvj0bnjp2og4#heading=h.9wxppk5x5p7x

   # source atomdata run_ids: ad_time=64263, ad_amp=64262
   # Voltage model (state-index keyed)
   _VOLTAGE_MODEL_BY_STATE = {
      0: {'b': -0.21729765625, 'k_t': -3208.33333333, 'k_a': 0.0221800595238},
      1: {'b': -0.27353125, 'k_t': 6870.03968254, 'k_a': 0.131696428571},
   }
   # Photon-rate model (state-index keyed)
   _PHOTON_RATE_MODEL_BY_STATE = {
      0: {'b': -12.5683566418, 'k_t': 474798.248551, 'k_a': 53.316723475},
      1: {'b': -25.7080218505, 'k_t': 1653122.17917, 'k_a': 244.219474551},
   }
   # Photon-number STD model (state-index keyed)
   _PHOTON_NUMBER_STD_MODEL_BY_STATE = {
      0: {'b': 10.566118639, 'k_t': 2774226.53904, 'k_a': -12.7258033633},
      1: {'b': 3.38301618956, 'k_t': 10441637.8607, 'k_a': -1.52497818869},
   }

   def integrated_imaging_voltage(amp_imaging, t_imaging, state):
      st = int(state)
      p = _VOLTAGE_MODEL_BY_STATE[st]
      return p["b"] + p["k_t"] * t_imaging + p["k_a"] * amp_imaging


   def integrated_imaging_photon_rate_us(amp_imaging, t_imaging, state):
      st = int(state)
      p = _PHOTON_RATE_MODEL_BY_STATE[st]
      return p["b"] + p["k_t"] * t_imaging + p["k_a"] * amp_imaging


   def integrated_imaging_photon_number(amp_imaging, t_imaging, state):
      return integrated_imaging_photon_rate_us(amp_imaging, t_imaging, state) * (t_imaging * 1e6)


   def integrated_imaging_photon_number_std(amp_imaging, t_imaging, state):
      st = int(state)
      p = _PHOTON_NUMBER_STD_MODEL_BY_STATE[st]
      return p["b"] + p["k_t"] * t_imaging + p["k_a"] * amp_imaging

   # Requested convention: up = state 1, down = state 0
   v_all_up = integrated_imaging_voltage(amp_imaging, t_imaging, 1)
   v_all_down = integrated_imaging_voltage(amp_imaging, t_imaging, 0)

   photons_up = integrated_imaging_photon_number(amp_imaging, t_imaging, 1)
   photons_down = integrated_imaging_photon_number(amp_imaging, t_imaging, 0)
   print(photons_up, photons_down, np.sqrt(photons_up), np.sqrt(photons_down ))
   delta_photons = photons_up - photons_down

   std_photons_up = integrated_imaging_photon_number_std(amp_imaging, t_imaging, 1)
   std_photons_down = integrated_imaging_photon_number_std(amp_imaging, t_imaging, 0)

   return delta_photons, v_all_up, v_all_down, std_photons_up, std_photons_down

######

# run 22849
# all shims set to zero during feshbach field
# slope_imaging_frequency_per_i_transducer_hf = -4955357.14
# yintercept_imaging_frequency_per_i_transducer_hf = 339875000.026

# with PID, valid for 175-182 A
slope_imaging_frequency_per_i_transducer_hf = -4.229e6
yintercept_imaging_frequency_per_i_transducer_hf = 2.018e8

@portable
def high_field_imaging_detuning(i_transducer) -> TFloat:
    detuning = slope_imaging_frequency_per_i_transducer_hf * i_transducer \
      + yintercept_imaging_frequency_per_i_transducer_hf
    return detuning

# @portable
# def high_field_pid_imaging_detuning(i_transducer) -> TFloat:
#     detuning = slope_imaging_frequency_per_i_transducer_hf * i_transducer \
#       + yintercept_imaging_frequency_per_i_transducer_hf
#     return detuning

# run 23078
# all shims set to zero during feshbach field
# slope_imaging_frequency_per_i_transducer_lf = -8355555.540425534
# yintercept_imaging_frequency_per_i_transducer_lf = 444888888.5787226

# run 23512
# all shims set to zero during feshbach field
# slope_imaging_frequency_per_i_transducer_lf = -8509090.922196094
# yintercept_imaging_frequency_per_i_transducer_lf = 449781818.3732016

# @portable
# def low_field_imaging_detuning(i_transducer) -> TFloat:
#     detuning = slope_imaging_frequency_per_i_transducer_lf * i_transducer \
#       + yintercept_imaging_frequency_per_i_transducer_lf
#     return detuning

# run 23527
a2_imaging_frequency_per_i_transducer_lf = 53030.29454330852
a1_imaging_frequency_per_i_transducer_lf = -10615151.158501664
a0_imaging_frequency_per_i_transducer_lf = 468981814.71528655

@portable
def low_field_imaging_detuning(i_transducer) -> TFloat:
   a0 = a0_imaging_frequency_per_i_transducer_lf
   a1 = a1_imaging_frequency_per_i_transducer_lf
   a2 = a2_imaging_frequency_per_i_transducer_lf
   i = i_transducer
   detuning = a2 * i**2 + a1 * i + a0
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

# 2026-01-19 imaging power measurement.
# https://docs.google.com/document/d/11tzbmMhPQ-lycEPc1OWHo9MnWyrR9bsQly9bz8DF_WQ/edit?tab=t.2mlzqbhu1zh6#heading=h.xza8o2nc0hj
slope_imaging_x_power_per_vpd = 5.55e-06 # W/V
yintercept_imaging_x_power_vs_vpd = -2.12e-07 # W
@portable
def imaging_x_pid_vpd_to_power(v_pid) -> TFloat:
   return slope_imaging_x_power_per_vpd * v_pid + yintercept_imaging_x_power_vs_vpd

@portable
def imaging_x_pid_power_to_vpd(power) -> TFloat:
   return (power - yintercept_imaging_x_power_vs_vpd)/slope_imaging_x_power_per_vpd

# @portable 
# def apd_abs_image_vpd