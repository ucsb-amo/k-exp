"""Builds lightshift_via_ramsey_phase_jump.ipynb (write-only; execute it separately).

The fringe fitting and phase-jump extraction live in waxa.analysis.lightshift, shared with
analysis/feedback/figures/atomic_physics_gpu.ipynb.
"""
from pathlib import Path

import nbformat
from nbformat.v4 import new_code_cell, new_notebook

CELLS = [
'''%load_ext autoreload
%autoreload 2
%matplotlib inline
import matplotlib.pyplot as plt
import matplotlib as mpl
import numpy as np

from waxa import atomdata
from waxa.plotting import *

font = 'DejaVu Sans'
plt.rcParams['figure.dpi'] = 200
plt.rcParams['legend.fontsize'] = 'small'
plt.rcParams['font.family'] = font
plt.rcParams['font.sans-serif'] = [font]
plt.rcParams['mathtext.fontset'] = 'custom\'''',

'''ad = atomdata(0)
print(ad.run_info.run_id)''',

'''plt.set_cmap("viridis")
mixOD_grid(ad,
           ad.od,
           max_od=2.,
           xvarformat='1.3f',
           figsize=[20,3],
           aspect='equal')
plt.show()''',

'''# Light shift from the Ramsey phase jump: fringe with the imaging light on against
# the fringe with it off (xvar with_imaging), both fit by waxa.analysis.lightshift.  A scan
# without the off fringe falls back to reference_phase (pi for this sequence).
from waxa.analysis.lightshift import ramsey_light_shift

ls = ramsey_light_shift(ad)
ls.plot_fringes()
plt.show()

print(f"fits ok: {ls.n_ok}/{ls.n_total}, reference "
      f"{'measured (light off)' if ls.reference_measured else f'assumed at {ls.reference_phase:.2f} rad'}")
if ls.scan_names:
    ls.plot()
    plt.show()
else:
    f_lightshift = float(ls.f_lightshift_Hz)
    print(ls.config_line())''',

'''# -- tunables --
# light shift (Hz) measured with the cell above at each imaging amplitude
IMG_AMPS = [0.0, 0.2, 0.3, 0.4]
LIGHT_SHIFTS_HZ = [0., 30.57e3, 47.01e3, 65.8e3]

img_amps_arr = np.asarray(IMG_AMPS, dtype=float)
ls_arr = np.asarray(LIGHT_SHIFTS_HZ, dtype=float)
(slope, intercept), pcov = np.polyfit(img_amps_arr, ls_arr, 1, cov=True)
slope_err, intercept_err = np.sqrt(np.diag(pcov))

x_fit = np.linspace(img_amps_arr.min(), img_amps_arr.max(), 300)

fig, ax = plt.subplots(figsize=(6, 4), layout='constrained')
ax.plot(img_amps_arr, ls_arr / 1e3, ".", ms=9)
ax.plot(x_fit, (slope * x_fit + intercept) / 1e3, "--")
ax.legend(["Data", "Fit"])
ax.set_xlabel("amp_imaging")
ax.set_ylabel("light shift (kHz)")
ax.set_title(f"Run ID: {ad.run_info.run_id}\\nlight shift calibration: "
             f"slope {slope/1e3:.1f}({slope_err/1e3:.1f}) kHz/amp, "
             f"intercept {intercept/1e3:.1f}({intercept_err/1e3:.1f}) kHz")
ax.grid(alpha=0.25)
plt.show()

def ls_from_img_amp(img_amp):
    img_amp = np.asarray(img_amp, dtype=float)
    ls_val = slope * img_amp + intercept
    return ls_val.item() if ls_val.ndim == 0 else ls_val

print(f"slope = {slope:.6g} +/- {slope_err:.2g} Hz/amp, intercept = {intercept:.6g} +/- {intercept_err:.2g} Hz")''',

'''img_amps = np.linspace(.3,1.7,50)
lss = ls_from_img_amp(img_amps)''',

'''119.4639e6 + lss''',

'''ls_from_img_amp(2.5)''',
]

nb = new_notebook(cells=[new_code_cell(c) for c in CELLS])
nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
out = Path(__file__).with_name("lightshift_via_ramsey_phase_jump.ipynb")
nbformat.write(nb, out)
print(f"wrote {out} ({len(CELLS)} cells, not executed)")
