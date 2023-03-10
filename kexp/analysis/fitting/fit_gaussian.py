import numpy as np
from scipy.optimize import curve_fit

class GaussianFit():
    def __init__(self,amplitude,sigma,center,offset,xaxis,):
        self.amplitude = amplitude
        self.sigma = sigma
        self.center = center
        self.offset = offset
        self.xaxis = xaxis

    # def _fit_func()

def _gauss(x, amplitude, sigma, x0, offset):
    return offset + amplitude * np.exp( -(x-x0)**2 / (2 * sigma**2) )

def _gauss_fit(x, y):
    '''
    Returns the gaussian fit parameters for y(x).

    Fit equation: offset + amplitude * np.exp( -(x-x0)**2 / (2 * sigma**2) )

    Parameters
    ----------
    x: ArrayLike
    y: ArrayLike

    Returns
    -------
    amplitude: float
    sigma: float
    x0: float
    offset: float
    '''
    mean = sum(x * y) / sum(y)
    sigma = np.sqrt(sum(y * (x - mean) ** 2) / sum(y))
    popt, pcov = curve_fit(_gauss, x, y, p0=[min(y), max(y), mean, sigma])
    return popt

def gauss_fit(x,y):
    '''
    Returns a GaussianFit object containing the gaussian fit parameters for
    y(x).

    Fit equation: offset + amplitude * np.exp( -(x-x0)**2 / (2 * sigma**2) )

    Parameters
    ----------
    x: ArrayLike
    y: ArrayLike

    Returns
    -------
    amplitude: float
    sigma: float
    x0: float
    offset: float
    '''
    amplitude, sigma, x0, offset = _gauss_fit(x,y)
    fit = GaussianFit(amplitude, sigma, x0, offset, xaxis=x)
    return fit
