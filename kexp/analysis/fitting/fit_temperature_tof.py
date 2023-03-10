import numpy as np
from scipy.optimize import curve_fit
import kamo.k_properties.constants as c
from kexp.config.camera_params import pixel_size_m, magnification

def tof_sigma_classical(t, sigma0, T):
    return pixel_size_m / magnification * np.sqrt( c.kB * T / c.m_K * t**2 + sigma0**2 )

def tof_temperature_fit_classical(x, y, sigma0):
    popt, pcov = curve_fit(tof_sigma_classical, x, y, p0=[min(y), max(y), sigma0])
    return popt