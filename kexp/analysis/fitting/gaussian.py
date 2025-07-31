import numpy as np
from scipy.optimize import curve_fit
from scipy.signal import find_peaks
import matplotlib.pyplot as plt
import kamo.constants as c
from kexp.analysis.fitting.fit import Fit

class GaussianFit(Fit):
    def __init__(self,xdata,ydata,debug_plotting=False,
                 which_peak=0,
                 px_boxcar_smoothing=3,
                 fractional_peak_height_at_width=0.3,
                 fractional_peak_prominence = 0.01,
                 use_peak_bases_for_amplitude=False,
                 include_idx = [0,-1],
                 exclude_idx = [],
                 print_errors = True):
        super().__init__(xdata,ydata,
                         include_idx=include_idx,exclude_idx=exclude_idx,
                         savgol_window=20)

        self._debug_plotting = debug_plotting

        try:
            popt = self._fit(self.xdata,self.ydata,
                             which_peak,
                             px_boxcar_smoothing,
                             fractional_peak_height_at_width,
                             use_peak_bases_for_amplitude,
                             fractional_peak_prominence)
        except Exception as e:
            if print_errors:
                print(e)
            popt = [np.NaN] * 4
            self.y_fitdata = np.zeros(self.ydata.shape); self.y_fitdata.fill(np.NaN)

        amplitude, sigma, x_center, y_offset = popt
        self.popt = popt
        self.amplitude = amplitude
        self.sigma = sigma
        self.x_center = x_center
        self.y_offset = y_offset

        self.y_fitdata = self._fit_func(self.xdata,*popt)

        self.area = self.amplitude * np.sqrt( 2 * np.pi * self.sigma**2 )

    def _fit_func(self, x, amplitude, sigma, x_center, y_offset):
        return y_offset + amplitude * np.exp( -(x-x_center)**2 / (2 * sigma**2) )

    def _fit(self, x, y,
             which_peak,
             px_boxcar_smoothing,
             fractional_peak_height_at_width,
             use_peak_bases_for_amplitude,
             fractional_peak_prominence):
        """Returns the gaussian fit parameters for y(x).

        Fit equation: offset + amplitude * np.exp( -(x-x0)**2 / (2 * sigma**2) )

        Args:
            x (np.array):
            y (np.array):
            which_peak (int, optional): Which peak (in order of prominence) to
            fit. Defaults to 0.

        Returns:
            popt: _description_
        """

        out = self._gaussian_guesses(x,y,
                                     which_peak,
                                     px_boxcar_smoothing,
                                     fractional_peak_height_at_width,
                                     use_peak_bases_for_amplitude,
                                     fractional_peak_prominence)
        fit_mask = out[0]
        guesses = out[1:]

        popt, pcov = curve_fit(self._fit_func, x[fit_mask], y[fit_mask],
                        p0=[*guesses],
                        bounds=((0,0,-np.inf,-np.inf),(np.inf,np.inf,np.inf,np.inf)))
        return popt
    
    def _gaussian_guesses(self,x,y,
                          which_peak,
                          px_boxcar_smoothing_width=10,
                          fractional_peak_height_at_width=0.4,
                          use_peak_bases=False,
                          fractional_peak_prominence=0.01):
        
        # smooth the data
        convwidth = px_boxcar_smoothing_width
        ysm = np.convolve(y,[1/convwidth]*convwidth,mode='same')
        # shift and normalize between 0 and 1
        ynorm = ysm-np.min(ysm)
        try:
            ynorm = ynorm/(np.max(ynorm) - np.min(ynorm))
        except:
            print(ynorm)

        peak_idx, prop = find_peaks(ynorm[convwidth:],prominence=fractional_peak_prominence)
        peak_idx += convwidth
        # get the most prominent peak if > 1
        prom = prop['prominences']
        idx_idx = np.flip(np.argsort(prom))[which_peak]
        peak_idx = peak_idx[idx_idx]
        prom = prom[idx_idx]

        # identify the x-position closest to the peak which has y-value closest
        # to fraction thr of peak y-value, use distance between this and
        # x-position of peak as width guess.
        if use_peak_bases:
            ybase_norm = (ynorm[prop['right_bases'][idx_idx]] + ynorm[prop['left_bases'][idx_idx]])/2
            ynorm_base_at_zero = ynorm - ybase_norm
        else:
            ynorm_base_at_zero = ynorm

        threshold_ynorm_at_width = fractional_peak_height_at_width*ynorm_base_at_zero[peak_idx]
        # construct a function miny which is minimized for y values near the threshold y value
        miny = np.abs(ynorm_base_at_zero - threshold_ynorm_at_width)
        how_close_is_close = 0.5 * threshold_ynorm_at_width
        mask = miny < how_close_is_close
  
        # find the x value in the region where the y value is near the threshold
        # value which is closest to the x value at the peak (x[idx])
        
        ## Debug plotting
        # import matplotlib.pyplot as plt
        # plt.figure()
        # plt.plot(x,miny)
        # plt.plot(x,ynorm_base_at_zero)
        # plt.scatter(x,miny)
        # plt.hlines(ynorm_base_at_zero[peak_idx],xmin=plt.xlim()[0],xmax=plt.xlim()[1])
        # plt.vlines(x[peak_idx],
        #            ymin=plt.ylim()[0],ymax=plt.ylim()[1],
        #            colors='k',label='center guess')
        # plt.scatter(x[mask],miny[mask])
        # plt.scatter(x[peak_idx],0,color=[1,0,0])
        # plt.show()

        idx_nearest = np.argmin(np.abs(x[mask] - x[peak_idx]))
        x_nearest = x[mask][idx_nearest]

        # construct a mask for the fitting based on a multiple of the estimated peak width
        peak_width_idx = np.abs(peak_idx - np.where(x == x_nearest)[0][0])
        if peak_width_idx == 1:
            peak_width_idx = 2
        N_peak_widths_mask = 4.
        mask_window_half_width = int(N_peak_widths_mask * peak_width_idx)
        fit_mask = np.arange((peak_idx-mask_window_half_width),(peak_idx+mask_window_half_width))
        fit_mask = np.intersect1d(range(len(x)),fit_mask)

        amplitude_guess = y[peak_idx] - np.min(y[fit_mask])
        x_center_guess = x[peak_idx]
        sigma_guess = np.abs(x[peak_idx] - x_nearest)
        y_offset_guess = np.min(y[fit_mask])

        ## Debug plotting
        if self._debug_plotting:
            fig, ax = plt.subplots(1,2,layout='constrained')
            ax[0].plot(x,ynorm_base_at_zero)
            ax[0].plot(x,miny)
            ax[0].scatter(x,miny)
            ax[0].vlines(x[peak_idx],
                    ymin=ax[0].get_ylim()[0],ymax=ax[0].get_ylim()[1],
                    colors=[0,0,0.3],label='center guess')
            ax[0].scatter(x[mask],miny[mask])
            ax[0].scatter([x[mask][idx_nearest],
                        x[peak_idx]],
                        [ynorm_base_at_zero[mask][idx_nearest],
                        ynorm_base_at_zero[peak_idx]],color=[1,0,0],
                        label='width guess')
            ax[0].vlines([x[fit_mask][0],x[fit_mask][-1]],
                    ymin=ax[0].get_ylim()[0],ymax=ax[0].get_ylim()[1],
                    colors=[0.5,0.5,0.5],
                    label='fit mask bounds')
            
            ax[1].plot(x,y)
            ax[1].vlines(x_center_guess,
                    ymin=ax[1].get_ylim()[0],ymax=ax[1].get_ylim()[1],
                    colors=[0,0,0.3],label='center guess')
            ax[1].vlines([x_center_guess+sigma_guess,
                        x_center_guess-sigma_guess],
                    ymin=ax[1].get_ylim()[0],ymax=ax[1].get_ylim()[1],
                    colors=[1,0,0],linestyle='--',
                    label='center +/- sigma guess')
            ax[1].vlines([x[fit_mask][0],x[fit_mask][-1]],
                    ymin=ax[1].get_ylim()[0],ymax=ax[1].get_ylim()[1],
                    colors=[0.5,0.5,0.5],
                    label='fit mask bounds')
            ax[1].hlines([amplitude_guess, y_offset_guess],
                    xmin=ax[1].get_xlim()[0],xmax=ax[1].get_xlim()[1],
                    colors=[0,0.2,0],
                    linestyle='-.',
                    label='amp and offset guess')
            ax[1].legend(loc='lower left')

        return fit_mask, amplitude_guess, sigma_guess, x_center_guess, y_offset_guess
    
class MultiGaussianFit(GaussianFit,Fit):
    """Fits a distribution with N resolvable gaussian peaks. Returns fit
    parameters for each gaussian from left to right.
    """    
    def __init__(self,xdata,ydata,N_peaks,
                 debug_plots=False,
                 fractional_peak_prominence=0.01,
                 fractional_peak_height_at_width=0.6,
                 px_boxcar_smoothing_width=3,
                 peak_distance_px=3,
                 include_idx = [0,-1],
                 exclude_idx = []):
        super().__init__(xdata,ydata,
                         include_idx=include_idx,exclude_idx=exclude_idx)

        self._debug_plotting = debug_plots
        self.N_peaks = N_peaks
        n_params = 4
        self._prepare_fit_result_lists(N_peaks,n_params)
        self.popt = self._fit(self.xdata,self.ydata,0,
                              fractional_peak_prominence,
                              fractional_peak_height_at_width,
                              px_boxcar_smoothing_width,
                              peak_distance_px)
        self._assign_fit_results()

    def _prepare_fit_result_lists(self,N_peaks,n_params):
        self.popt = np.zeros(N_peaks * (n_params-1) + 1)
        self.amplitude = np.zeros(n_params)
        self.sigma = np.zeros(n_params)
        self.x_center = np.zeros(n_params)
        self.y_offset = 0.
        self.y_fitdata_single = np.zeros((n_params,) + self.xdata.shape)
        self.y_fitdata = np.zeros(self.xdata.shape)
        self.popt_single = np.zeros((N_peaks,n_params))

    def _assign_fit_results(self):
        self.y_offset = self.popt[0]
        self.amplitude = self.popt[1::3]
        self.sigma = self.popt[2::3]
        self.x_center = self.popt[3::3]

        # return peaks from left to right
        idx = np.argsort(self.x_center)
        self.amplitude = self.amplitude[idx]
        self.sigma = self.sigma[idx]
        self.x_center = self.x_center[idx]

        for i in range(self.N_peaks):
            self.popt_single[i] = [self.y_offset,self.amplitude[i],self.sigma[i],self.x_center[i]]
            self.y_fitdata_single[i] = self._fit_func(self.xdata,*self.popt_single[i])
        
        self.area = self.amplitude * np.sqrt(2 * np.pi * self.sigma**2)
        self.y_fitdata = self._fit_func(self.xdata, *self.popt)

    def plot_fit(self,
                 title_str = "",
                N_interp = 10000):
        import matplotlib.pyplot as plt
        plt.figure()
        plt.plot(self.xdata, self.ydata)
        xsm = np.linspace(self.xdata[0],self.xdata[-1],N_interp)
        ysm_total = np.zeros(xsm.shape)
        for idx in range(self.N_peaks):
            ysm = self._fit_func(xsm,*self.popt_single[idx])
            plt.plot(xsm, ysm, label=f"fit {idx+1}/{self.N_peaks}")
            ysm_total += ysm
        plt.plot(xsm,self._fit_func(xsm,*self.popt),label='total fit')
        plt.xlabel('position (m)')
        plt.ylabel('sum od')
        plt.legend()
        if title_str:
            plt.title(title_str)
        plt.show()

    def _fit_func(self, x, y_offset, *args):
        y = np.ones(x.shape) * y_offset
        for idx in range(len(args)//3):
            amplitude = args[3*idx]
            sigma = args[3*idx+1]
            x_center = args[3*idx+2]
            y += amplitude * np.exp( -(x-x_center)**2 / (2 * sigma**2) )
        return y

    def _fit(self, x, y,
            which_peak,
            fractional_peak_prominence,
            fractional_peak_height_at_width,
            px_boxcar_smoothing_width,
            peak_distance_px):
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
        if not np.all(y == 0):
            offsets = []
            guesses = []
            for i in range(self.N_peaks):
                out = self._gaussian_guesses(x,y,which_peak=i,
                                             fractional_peak_prominence=fractional_peak_prominence,
                                             fractional_peak_height_at_width=fractional_peak_height_at_width,
                                             px_boxcar_smoothing_width=px_boxcar_smoothing_width,
                                             peak_distance_px=peak_distance_px)
                offsets.append(out[1])
                guess = out[2:]
                for g in guess:
                    guesses.append(g)
            y_offset_guess = np.mean(offsets)
        else:
            guesses = [0] * 3 * self.N_peaks
            y_offset_guess = 0

        bound_low = (-np.inf,)
        bound_high = (np.inf,)
        for n in range(self.N_peaks):
            bound_low += (0,0,-np.inf)
            bound_high += (np.inf,np.inf,np.inf)

        popt, pcov = curve_fit(self._fit_func, x, y,
                        p0=[y_offset_guess,*guesses],
                        bounds=(bound_low,bound_high))
        return popt

    def _gaussian_guesses(self,x,y,
                          which_peak,
                          fractional_peak_prominence=0.01,
                          fractional_peak_height_at_width=0.4,
                          px_boxcar_smoothing_width=3,
                          peak_distance_px=3):
        # smooth the data
        convwidth = px_boxcar_smoothing_width
        ysm = np.convolve(y,[1/convwidth]*convwidth,mode='same')
        # shift and normalize between 0 and 1
        ynorm = ysm-np.min(ysm)
        try:
            ynorm = ynorm/(np.max(ynorm) - np.min(ynorm))
        except:
            print(ynorm)

        peak_idx, prop = find_peaks(ynorm[convwidth:],prominence=fractional_peak_prominence,
                                    distance=peak_distance_px)
        peak_idx += convwidth
        # get the "which_peak"th most prominent peak
        prom = prop['prominences']
        prom_indices = np.flip(np.argsort(prom))
        # check to see there were enough peaks found
        if len(prom_indices) > which_peak:
            idx_idx = prom_indices[which_peak]
        else:
            idx_idx = prom_indices[-1]
        peak_idx = peak_idx[idx_idx]
        prom = prom[idx_idx]

        # identify the x-position closest to the peak which has y-value closest
        # to fraction thr of peak y-value, use distance between this and
        # x-position of peak as width guess.
        # ybase_norm = (ynorm[prop['right_bases'][idx_idx]] + ynorm[prop['left_bases'][idx_idx]])/2
        # ybase_norm = np.min([ynorm[prop['right_bases'][idx_idx]],
        #                       ynorm[prop['left_bases'][idx_idx]]])
        # ynorm_base_at_zero = ynorm - ybase_norm
        ynorm_base_at_zero = ynorm

        threshold_ynorm_at_width = fractional_peak_height_at_width*ynorm_base_at_zero[peak_idx]
        # construct a function miny which is minimized for y values near the threshold y value
        miny = np.abs(ynorm_base_at_zero - threshold_ynorm_at_width)
        how_close_is_close = 0.5 * threshold_ynorm_at_width
        mask = miny < how_close_is_close
  
        # find the x value in the region where the y value is near the threshold value which is closest to the x value at the peak (x[idx])
        idx_nearest = np.argmin(np.abs(x[mask] - x[peak_idx]))
        x_nearest = x[mask][idx_nearest]

        # construct a mask for the fitting based on a multiple of the estimated peak width
        peak_width_idx = np.abs(peak_idx - np.where(x == x_nearest)[0][0])
        if peak_width_idx == 1:
            peak_width_idx = 2
        N_peak_widths_mask = 2.
        mask_window_half_width = int(N_peak_widths_mask * peak_width_idx)
        fit_mask = np.arange((peak_idx-mask_window_half_width),(peak_idx+mask_window_half_width))
        fit_mask = np.intersect1d(range(len(x)),fit_mask)

        amplitude_guess = y[peak_idx] - np.min(y[fit_mask])
        x_center_guess = x[peak_idx]
        sigma_guess = np.abs(x[peak_idx] - x_nearest)
        y_offset_guess = np.min(y[fit_mask])

        ## Debug plotting
        if self._debug_plotting:
            fig, ax = plt.subplots(1,2,layout='constrained')
            ax[0].plot(x,ynorm_base_at_zero)
            ax[0].plot(x,miny)
            ax[0].scatter(x,miny)
            ax[0].vlines(x[peak_idx],
                    ymin=ax[0].get_ylim()[0],ymax=ax[0].get_ylim()[1],
                    colors=[0,0,0.3],label='center guess')
            ax[0].scatter(x[mask],miny[mask])
            ax[0].scatter([x[mask][idx_nearest],
                        x[peak_idx]],
                        [ynorm_base_at_zero[mask][idx_nearest],
                        ynorm_base_at_zero[peak_idx]],color=[1,0,0],
                        label='width guess')
            ax[0].vlines([x[fit_mask][0],x[fit_mask][-1]],
                    ymin=ax[0].get_ylim()[0],ymax=ax[0].get_ylim()[1],
                    colors=[0.5,0.5,0.5],
                    label='fit mask bounds')
            ax[0].hlines([how_close_is_close],
                    xmin=ax[0].get_xlim()[0],xmax=ax[0].get_xlim()[1],
                    colors=[1,0.7,0],
                    linestyle='-.')
            
            ax[1].plot(x,y)
            ax[1].vlines(x_center_guess,
                    ymin=ax[1].get_ylim()[0],ymax=ax[1].get_ylim()[1],
                    colors=[0,0,0.3],label='center guess')
            ax[1].vlines([x_center_guess+sigma_guess,
                        x_center_guess-sigma_guess],
                    ymin=ax[1].get_ylim()[0],ymax=ax[1].get_ylim()[1],
                    colors=[1,0,0],linestyle='--',
                    label='center +/- sigma guess')
            ax[1].vlines([x[fit_mask][0],x[fit_mask][-1]],
                    ymin=ax[1].get_ylim()[0],ymax=ax[1].get_ylim()[1],
                    colors=[0.5,0.5,0.5],
                    label='fit mask bounds')
            ax[1].hlines([amplitude_guess, y_offset_guess],
                    xmin=ax[1].get_xlim()[0],xmax=ax[1].get_xlim()[1],
                    colors=[0,0.2,0],
                    linestyle='-.',
                    label='amp and offset guess')
            ax[1].legend(loc='lower left')

        return fit_mask, y_offset_guess, amplitude_guess, sigma_guess, x_center_guess

class BECFit(Fit):
    def __init__(self,xdata,ydata,
                 include_idx = [0,-1],
                 exclude_idx = []):
        super().__init__(xdata,ydata,
                         include_idx=include_idx,exclude_idx=exclude_idx,
                         savgol_window=20)

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
    def __init__(self, xdata, ydata,
                 include_idx = [0,-1],
                 exclude_idx = []):
        super().__init__(xdata,ydata,
                         include_idx=include_idx,exclude_idx=exclude_idx,
                         savgol_window=4,savgol_degree=2)

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