import numpy as np

def trap_frequency_from_tweezer_power(p_tweezer):
    pass

def tweezer_power_from_vpd(v_pd,aod_amplitude,n_tweezers):
    # from k-jam\analysis\measurements\trap_frequency_from_atom_loss.ipynb
    T_CELL = 0.97
    T_OBJECTIVE = 0.74
    slope_mW_per_vpd = 39.43830286087527
    y_intercept_vpd = -3.056741637492236
    
