import numpy as np
from scipy.optimize import curve_fit

def gauss(x, amplitude, sigma, x0, offset):
    return offset + amplitude * np.exp( -(x-x0)**2 / (2 * sigma**2) )

def gauss_fit(x, y):
    mean = sum(x * y) / sum(y)
    sigma = np.sqrt(sum(y * (x - mean) ** 2) / sum(y))
    popt, pcov = curve_fit(gauss, x, y, p0=[min(y), max(y), mean, sigma])
    return popt