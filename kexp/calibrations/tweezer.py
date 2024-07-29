import numpy as np
from artiq.experiment import TFloat, portable

def trap_frequency_from_tweezer_power(p_tweezer):
    pass

def tweezer_power_from_vpd(v_pd,aod_amplitude,n_tweezers):
    # from k-jam\analysis\measurements\trap_frequency_from_atom_loss.ipynb
    T_CELL = 0.97
    T_OBJECTIVE = 0.74
    slope_mW_per_vpd = 39.43830286087527
    y_intercept_vpd = -3.056741637492236

def aod_diffraction_efficiency_from_awg_amp(amp):
    pass

@portable(flags={"fast-math"})
def vpd2_per_vpd1(vpd_pid1) -> TFloat:
    slope = 9.79299
    y_intercept = -0.136599
    return vpd_pid1*slope + y_intercept
