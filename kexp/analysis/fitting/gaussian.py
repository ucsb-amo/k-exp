import numpy as np
from scipy.optimize import curve_fit
import kamo.constants as c
from kexp.analysis.fitting.fit import Fit

class GaussianFit(Fit):
    def __init__(self,xdata,ydata):
        super().__init__(xdata,ydata,savgol_window=20)

        try:
            popt = self._fit(self.xdata,self.ydata)
        except Exception as e:
            print(e)
            popt = [np.NaN] * 4
            self.y_fitdata = np.zeros(self.ydata.shape); self.y_fitdata.fill(np.NaN)

        amplitude, sigma, x_center, y_offset = popt
        self.amplitude = amplitude
        self.sigma = sigma
        self.x_center = x_center
        self.y_offset = y_offset

        self.y_fitdata = self._fit_func(self.xdata,*popt)

        self.area = self.amplitude * np.sqrt( 2 * np.pi * self.sigma**2 )

    def _fit_func(self, x, amplitude, sigma, x_center, y_offset):
        return y_offset + amplitude * np.exp( -(x-x_center)**2 / (2 * sigma**2) )

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
        '''

        out = self._gaussian_guesses(x,y)
        fit_mask = out[0]
        guesses = out[1:]

        popt, pcov = curve_fit(self._fit_func, x[fit_mask], y[fit_mask],
                        p0=[*guesses],
                        bounds=((0,0,-np.inf,0),(np.inf,np.inf,np.inf,np.inf)))
        return popt
    
    def _gaussian_guesses(self,x,y,
                          fractional_peak_prominence=0.05,
                          fractional_peak_height_at_width=0.4,
                          px_boxcar_smoothing_width=6):
        # smooth the data
        convwidth = px_boxcar_smoothing_width
        ysm = np.convolve(y,[1/convwidth]*convwidth,mode='same')
        # shift and normalize between 0 and 1
        ynorm = ysm-np.min(ysm)
        ynorm = ynorm/(np.max(ynorm) - np.min(ynorm))

        from scipy.signal import find_peaks
        peak_idx, prop = find_peaks(ynorm[convwidth:],prominence=fractional_peak_prominence)
        peak_idx += convwidth
        # get the most prominent peak if > 1
        prom = prop['prominences']
        idx_idx = np.argmax(prom)
        peak_idx = peak_idx[idx_idx]
        prom = prom[idx_idx]

        # identify the x-position closest to the peak which has y-value closest
        # to fraction thr of peak y-value, use distance between this and
        # x-position of peak as width guess.
        ybase_norm = (ynorm[prop['right_bases'][idx_idx]] + ynorm[prop['left_bases'][idx_idx]])/2
        ynorm_base_at_zero = ynorm - ybase_norm

        threshold_ynorm_at_width = fractional_peak_height_at_width*ynorm_base_at_zero[peak_idx]
        # construct a function miny which is minimized for y values near the threshold y value
        miny = np.abs(ynorm_base_at_zero - threshold_ynorm_at_width)
        how_close_is_close = 0.5 * threshold_ynorm_at_width
        mask = miny < how_close_is_close
        # find the x value in the region where the y value is near the threshold value which is closest to the x value at the peak (x[idx])
        idx_nearest = np.argmin(np.abs(x[mask] - x[peak_idx]))
        x_nearest = x[mask][idx_nearest]

        # construct a mask for the fitting based on a multiple of the estimated peak width
        peak_width_idx = np.abs(peak_idx - idx_nearest)
        N_peak_widths_mask = 2.
        mask_window_half_width = int(N_peak_widths_mask * peak_width_idx)
        fit_mask = np.arange((peak_idx-mask_window_half_width),(peak_idx+mask_window_half_width))
        fit_mask = np.intersect1d(range(len(x)),fit_mask)

        amplitude_guess = y[peak_idx] - np.min(y[fit_mask])
        x_center_guess = x[peak_idx]
        sigma_guess = np.abs(x[peak_idx] - x_nearest)
        y_offset_guess = np.min(y[fit_mask])

        return fit_mask, amplitude_guess, sigma_guess, x_center_guess, y_offset_guess

class BECFit(Fit):
    def __init__(self,xdata,ydata):
        super().__init__(xdata,ydata,savgol_window=20)

        try:
            popt = self._fit(self.xdata,self.ydata)
        except Exception as e:
            print(e)
            popt = [np.NaN] * 6
            self.y_fitdata = np.zeros(self.ydata.shape); self.y_fitdata.fill(np.NaN)

        self.popt = popt
        g_amp, g_sigma, g_center, tf_trap_coeff, tf_center, tf_offset = popt
        self.g_amp = g_amp
        self.g_sigma = g_sigma
        self.g_center = g_center
        self.tf_trap_coeff = tf_trap_coeff
        self.tf_center = tf_center
        self.tf_offset = tf_offset

        self.y_fitdata = self._fit_func(self.xdata,*popt)

    def _fit_func(self, x, g_amp, g_sigma, g_center, tf_trap_coeff, tf_center, tf_offset):
        return self._gauss(x, g_amp, g_sigma, g_center) + self._tf(x, tf_trap_coeff, tf_center, tf_offset)
    
    def _gauss(self, x, g_amp, g_sigma, g_center):
        return g_amp * np.exp( -(x-g_center)**2 / (2 * g_sigma**2) )
        
    def _tf(self, x, tf_trap_coeff, tf_center, tf_offset):
        return -tf_trap_coeff * (x - tf_center)**2 + tf_offset

    def _fit(self, x, y):

        delta_x = x[-1]-x[0]

        g_amp_guess = (np.max(y) - np.min(y)) / 2
        g_sigma_guess = delta_x/6
        g_center_guess = x[np.argmax(y)]
        tf_trap_coeff = c.m_K * (2 * np.pi * 500.)**2 / 2
        tf_center_guess = x[np.argmax(y)]
        tf_offset_guess = np.min(y)

        popt, pcov = curve_fit(self._fit_func, x, y,
                               p0 = [g_amp_guess, g_sigma_guess, g_center_guess, tf_trap_coeff, tf_center_guess, tf_offset_guess],
                               bounds = ((0,0,x[0]-delta_x,0,x[0]-delta_x,0),(np.inf,np.inf,x[-1]+delta_x,np.inf,x[-1]+delta_x,np.inf)))
        return popt

class GaussianTemperatureFit(Fit):
    def __init__(self, xdata, ydata):

        super().__init__(xdata,ydata,savgol_window=4,savgol_degree=2)

        # scales up small numbers
        self._mult = 1.e6

        self._xdata_sq = (self.xdata * self._mult)**2
        self._ydata_sq = (self.ydata * self._mult)**2

        fit_params, cov = self._fit(self._xdata_sq,self._ydata_sq)
        T, sigma0_squared = fit_params
        err = np.sqrt(np.diag(cov))
        err_T, _ = err
        self.T = T
        self.err_T = err_T
        self.sigma0 = np.sqrt(sigma0_squared) / self._mult

        self.y_fitdata = np.sqrt( self._fit_func(self._xdata_sq,T,sigma0_squared) ) / self._mult

    def _fit_func(self, t_squared, T, sigma0_squared):
        return c.kB * T / c.m_K * t_squared + sigma0_squared

    def _fit(self, x, y):
        # sigma0_guess = self.ydata[np.argmin(self.xdata)]
        sigma0_guess = 500
        # get rid of nans
        logic = ~np.isnan(y)
        y = y[logic]
        x = x[logic]
        # fit
        popt, pcov = curve_fit(self._fit_func, x, y, p0=[0.001,sigma0_guess**2], bounds=((0,0),(1,np.inf)))
        return popt, pcov