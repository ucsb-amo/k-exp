import numpy as np
from scipy.optimize import curve_fit
import kamo.constants as c
from kexp.analysis.fitting.fit import Fit

class KinematicFit(Fit):
    def __init__(self,xdata,ydata,
                 include_idx = [0,-1],
                 exclude_idx = []):
        super().__init__(xdata,ydata,
                         include_idx=include_idx,exclude_idx=exclude_idx,
                         savgol_window=20)

        try:
            self.popt, pcov = self._fit(self.xdata,self.ydata)
        except Exception as e:
            print(e)
            self.popt = [np.NaN]*3
            self.y_fitdata = np.zeros(self.ydata.shape); self.y_fitdata.fill(np.NaN)

        x0, v0, a = self.popt
        self.x0 = x0
        self.v0 = v0
        self.a = a

        self.pcov = pcov

        self.y_fitdata = self._fit_func(self.xdata,*self.popt)

    def _fit_func(self, t, x0, v0, a):
        return x0 + v0 * t + 1/2 * a * t**2

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
        x0_guess = np.mean(y)
        v0_guess = 0.
        a_guess = -1.
        popt, pcov = curve_fit(self._fit_func, x, y,
                                p0=[x0_guess, v0_guess, a_guess],
                                bounds=((-np.inf,-np.inf,-np.inf),(np.inf,np.inf,np.inf)))
        return popt, pcov
    
class QuadraticFit(Fit):
    def __init__(self,xdata,ydata,
                 include_idx = [0,-1],
                 exclude_idx = []):
        super().__init__(xdata,ydata,
                         include_idx=include_idx,exclude_idx=exclude_idx,
                         savgol_window=20)

        try:
            self.popt, pcov = self._fit(self.xdata,self.ydata)
        except Exception as e:
            print(e)
            self.popt = [np.NaN]*3
            self.y_fitdata = np.zeros(self.ydata.shape); self.y_fitdata.fill(np.NaN)

        a0, a1, a2 = self.popt
        self.a2 = a2
        self.a1 = a1
        self.a0 = a0

        self.pcov = pcov

        self.y_fitdata = self._fit_func(self.xdata,*self.popt)

    def _fit_func(self, x, a0, a1, a2):
        return a0 + a1 * x + a2 * x**2

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
        a0_guess = np.mean( [np.max(y), np.min(y)] )
        a1_guess = 0.
        slopes = np.diff(y)/np.diff(x)
        if slopes[0] > slopes[1]:
            a2_guess = -1.
        else:
            a2_guess = 1.
            
        popt, pcov = curve_fit(self._fit_func, x, y,
                                p0=[a0_guess, a1_guess, a2_guess],
                                bounds=((-np.inf,-np.inf,-np.inf),(np.inf,np.inf,np.inf)))
        return popt, pcov