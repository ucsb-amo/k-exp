import numpy as np
from artiq.experiment import TFloat, TArray, portable, rpc

#Calibration coefficients are from
#k-jam\analysis\measurements\PID1_vs_PID2.ipynb
vpd2_per_vpd1_slope =  71.67500001330266
v_pd2_y_intercept =  -2.1376785723712772

@portable(flags={"fast-math"})
def tweezer_vpd1_to_vpd2(vpd_pid1) -> TFloat:
    return vpd_pid1 * vpd2_per_vpd1_slope + v_pd2_y_intercept

@portable(flags={"fast-math"})
def tweezer_vpd2_to_vpd1(vpd_pid2) -> TFloat:
    return (vpd_pid2 - v_pd2_y_intercept) / vpd2_per_vpd1_slope

"""
To recalibrate:
1. Run tweezer_xpf_calibration.py, making sure that frequency, amplitude
lists produce a pair of trapped tweezers for both cateye (ce) and
non-cateye (nce).
2. Run analysis file:
k-jam/analysis/measurements/tweezer_xgrid_calibration.ipynb
3. Replace x_per_f_ce, x_per_f_nce, x_to_f_offset_ce, and
x_to_f_offset_nce (output of last cell).
"""

F_CE_MAX = 74.5e6
F_CE_MIN = 70.e6
F_NCE_MAX = 82.e6
F_NCE_MIN = 76.e6
X_TO_F_OFFSET_CE = 0.000423043
X_TO_F_OFFSET_NCE = -0.000442464
X_PER_F_CE = -5.7971e-12
X_PER_F_NCE = 5.7971e-12

from waxx.control.tweezer.tweezer_xmesh import tweezer_xmesh as mesh
tweezer_xmesh = mesh(F_CE_MAX,F_CE_MIN,F_NCE_MAX,F_NCE_MIN,X_TO_F_OFFSET_CE,X_TO_F_OFFSET_NCE,X_PER_F_CE,X_PER_F_NCE)