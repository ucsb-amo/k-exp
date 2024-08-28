import numpy as np
from scipy.optimize import curve_fit
import kamo.constants as c
from kexp.analysis.fitting.fit import Fit

class KinematicFit(Fit):
    def __init__(self,xdata,ydata):
        super().__init__(xdata,ydata,savgol_window=20)

        try:
            (x0, v0, a), pcov = self._fit(self.xdata,self.ydata)
        except Exception as e:
            print(e)
            x0, v0, a = np.NaN, np.NaN, np.NaN
            self.y_fitdata = np.zeros(self.ydata.shape); self.y_fitdata.fill(np.NaN)

        self.x0 = x0
        self.v0 = v0
        self.a = a

        self.pcov = pcov

        self.y_fitdata = self._fit_func(self.xdata,x0,v0,a)

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