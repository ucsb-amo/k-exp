from kexp.analysis.fitting import Fit, GaussianFit

from scipy.signal import find_peaks
from scipy.optimize import curve_fit

import numpy as np

class SineEnvelope(Fit):
    def __init__(self,xdata,ydata,
                include_idx=[0,-1],exclude_idx=[],
                override_center=None):
        super().__init__(xdata,ydata,
                        include_idx=include_idx,exclude_idx=exclude_idx,
                        savgol_window=20)

        # self.xdata, self.ydata = self.remove_infnan(self.xdata,self.ydata)

        self.override_center = override_center

        try:
            gfit = GaussianFit(xdata,ydata)
            self.gfit = gfit
            self.xdata = gfit.xdata
            # self.ydata = gfit.ydata - gfit.y_fitdata

            self.ydata = self.gfit.ydata
            self.popt, self.pcov = self._fit(self.xdata,self.ydata)
        except Exception as e:
            print(e)
            self.popt = [np.NaN, np.NaN, np.NaN, np.NaN, np.NaN, np.NaN, np.NaN]
            self.pcov = np.array([])
            self.y_fitdata = np.zeros(self.ydata.shape); self.y_fitdata.fill(np.NaN)

        amplitude, sigma, x_center, y_offset, contrast, k, phase = self.popt
        self.amplitude = amplitude
        self.sigma = sigma
        self.x_center = x_center
        self.y_offset = y_offset
        self.contrast = contrast
        self.k = k
        self.phase = phase

        self.y_fitdata = self._fit_func(self.xdata,*self.popt)


    def _fit_func(self, x, amplitude, sigma, x_center, y_offset, contrast, k, phase):
        if self.override_center != None:
            x0 = self.override_center 
        else:
            x0 = x_center
        return y_offset + amplitude * np.exp( -(x-x_center)**2 / (2 * sigma**2) ) * ( 1 + contrast * np.cos(k * (x-x0) + phase) )

    def _fit(self, x, y):
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
        guesses = self._guesses(x,y)
        popt, pcov = curve_fit(self._fit_func, x, y,
                                p0=guesses,
                                bounds=((-1.,0,-np.inf,0,0,0,0.),(np.inf,np.inf,np.inf,np.inf,np.inf,np.inf,np.inf)))
        return popt, pcov
        
    def _guesses(self,x,y):
        amplitude_guess = self.gfit.amplitude
        x_center_guess = self.gfit.x_center
        sigma_guess = self.gfit.sigma
        fringes_nogauss = self.ydata - self.gfit.y_fitdata
        self._fringe_data = fringes_nogauss

        fringe_rms = np.sqrt(np.mean(fringes_nogauss**2))
        self.frms = fringe_rms
    
        contrast_guess = fringe_rms 

        prom = fringe_rms
        idx, _ = find_peaks(y, prominence=prom, distance = 4)
        self._x_peaks = x[idx]
        lambda_guess = np.mean(np.diff(x[idx]))
        k_guess = 2*np.pi/lambda_guess 
        phase_guess = k_guess * x[self._find_idx(x_center_guess,x[idx])] + np.pi/4
        y_offset_guess = (np.max(y) - np.min(y))
        return amplitude_guess, sigma_guess, x_center_guess, y_offset_guess, contrast_guess, k_guess, phase_guess
    
    def _find_idx(self,x0,x):
        return np.argmin(np.abs(x-x0))