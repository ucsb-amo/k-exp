import numpy as np
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt
from scipy.signal import find_peaks
from kexp.analysis import atomdata
from kexp.analysis.helper import *

dv = -1000.
dv_fit_guess_rabi_frequency = 1.e5

class TOF():
    def __init__(self,
                 atomdata,
                 sigma_fit_axis,
                 shot_idx=0,
                 include_idx = [0,-1],
                 exclude_idx = []):
        
        ad = atomdata
        
        if sigma_fit_axis == 'y':
            cloudfits = ad.cloudfit_y
        elif sigma_fit_axis == 'x':
            cloudfits = ad.cloudfit_x

        if ad.Nvars == 1:
            self.sigmas = ad._extract_attr(cloudfits,'sigma')
            self.atom_numbers = ad.atom_number[:]
        elif ad.Nvars == 2:
            self.sigmas = ad._extract_attr(cloudfits[shot_idx],'sigma')
            self.atom_numbers = ad.atom_number[:]
            self.xvarname = ad.xvarnames[0]
            self.xvar = ad.xvars[0]

        self.t_tof = ad.params.t_tof
        
        from kexp.analysis.fitting.gaussian import GaussianTemperatureFit
        
        self.fit = GaussianTemperatureFit(self.t_tof, self.sigmas,
                                          include_idx = include_idx,
                                          exclude_idx = exclude_idx)
        
        self.sigma_r0 = self.fit.y_fitdata[0]
        self.average_atom_number = np.mean(self.atom_numbers)
        self.T = self.fit.T
        
        self.phase_space_density = 0.
        self.compute_phase_space_density()

    def compute_phase_space_density(self,
                                    num_tweezers=2,
                                    tweezer_waist=3.6e-6,
                                    trap_wavelength=1064.e-9,
                                    tweezer_final_frequency=455.):
        import kamo.constants as c
        # phase_space_density = self.average_atom_number / num_tweezers \
        #     / (np.sqrt(2) * np.pi) * (trap_wavelength / tweezer_waist) \
        #     * ( c.hbar**2/(c.kB * self.T * c.m_K * self.sigma_r0**2) )**(3/2)
        # self.phase_space_density = phase_space_density

        phase_space_density = self.average_atom_number / num_tweezers \
            / (np.sqrt(2) * np.pi) * (trap_wavelength / tweezer_waist) \
            * ( (c.hbar * 2 * np.pi * tweezer_final_frequency)/(c.kB * self.T) )**(3)
        self.phase_space_density = phase_space_density

def get_B(f_mf0_mf1_transition,
          F0=2.,mF0=0.,F1=1.,mF1=1.,
          min_B=0.,max_B=600.):

        from kamo.atom_properties.k39 import Potassium39
        k = Potassium39()
        B = np.linspace(min_B,max_B,1000000)
        f_transitions = abs(k.get_microwave_transition_frequency(4,0,.5,F0,mF0,F1,mF1,B)) * 1.e6

        def find_xval(y_val,y_vec,x_vec):
            y = np.asarray(y_vec)
            idx = (np.abs(y - y_val)).argmin()
            return x_vec[idx]

        return find_xval(f_mf0_mf1_transition,f_transitions,B)

def rabi_oscillation(ad:atomdata,
                     rf_frequency_hz,
                     pulse_times_array=[],
                     populations_array=[],
                     include_idx=[0,-1],
                     exclude_idx=[],
                     normalize_maximum_idx=None,
                     map_minimum_to_zero=None,
                     normalize_minimum_idx=None,
                     avg_repeats=True,
                     plot_bool=True,
                     plot_raw_data=True,
                     fit_params_on_plot=True,
                     fit_params_on_left=True,
                     fit_guess_frequency=dv_fit_guess_rabi_frequency,
                     fit_guess_phase=np.pi/2,
                     fit_guess_amp=1.,
                     fit_guess_offset=1.,
                     fit_guess_decay_tau=dv,
                     figsize=[]):
    """Fits the signal (max-min sumOD) vs. pulse time to extract the rabi
    frequency and pi-pulse time, and produces a plot.

    xvar: rf pulse time.

    Args:
        ad (atomdata)
        rf_frequency_hz (float): The RF drive frequency in Hz.
        populations_array (array, optional): An array of the populations, if
        left empty uses max(ad.sum_od_x) - min(ad.sum_od_x).
        pulse_times_array (array, optional): An array of the pulse times. If
        left empty uses ad.xvars[0].
        include_idx (list, optional): Specifies the first and last index of the
        data that will be used for the fit. -1 in the second element uses to the
        end of the list.
        normalize_maximum_idx (int, optional): If a value is provided,
        normalizes the data so that the value at the index provided is mapped to
        1. Otherwise, normalizes to the maximum value in the populations array.
        If avg_repeats is True, the value of the mean at this index in the
        repeat averaged array.
        map_minimum_to_zero (bool, optional): If True, normalizes the data so
        that it is scaled between 0 and 1, where the value mapped to zero is
        chosen according to `normalize_minimum_idx`. If `normalize_minimum_idx`
        is not None, then this bool is overridden to True.
        normalize_minimum_idx (int, optional): If a value is provided,
        normalizes the data so that the value at the provided index is mapped to
        zero 0 (full intial contrast), where the value at the provided index is
        mapped to zero.
        avg_repeats (bool, optional): If True, averages repeats and plots with error bars.
        plot_bool (bool, optional): If True, plots the data and fit. Defaults to True.
        fit_params_on_plot (bool, optional): If True, puts the fit parameter values on the plot.
        fit_params_on_left (bool, optional): If True, puts the fit parameter box
        on the left side of the plot.
        

    Returns:
        t_pi: The pi pulse time in seconds.
        popt: The fit result (order Omega, phi, B, A, tau)
    """

    # Define the Rabi oscillation function
    def _fit_func_rabi_oscillation(t, Omega, phi, B, A, tau):
        return B + A/2 * np.exp(-t/tau) * np.cos(Omega * t + phi)

    # Suppose these are your data
    pulse_times_array = np.asarray(pulse_times_array)
    pulse_times_array = pulse_times_array.flatten()
    if pulse_times_array.size:
        times = pulse_times_array
    else:
        times = ad.xvars[0]  # replace with your pulse times
    
    populations_array = np.asarray(populations_array)
    populations_array = populations_array.flatten()
    if populations_array.size:
        populations = populations_array
    else:
        sm_sum_ods = [sumod_x for sumod_x in ad.sum_od_x]
        rel_amps = [np.max(sumod_x)-np.min(sumod_x) for sumod_x in sm_sum_ods]
        populations = rel_amps  # replace with your atom populations

    populations = crop_array_by_index(populations,include_idx,exclude_idx)
    times = crop_array_by_index(times,include_idx,exclude_idx)

    populations, times = remove_infnan(populations, times)

    
        
    if avg_repeats:
        
        Nr = ad.params.N_repeats
        if isinstance(Nr,np.ndarray):
            Nr = Nr[0]
        mean, err = get_repeat_std_error(populations, Nr)

        if normalize_maximum_idx != None:
            override_normalize_max = mean[normalize_maximum_idx]
        else:
            override_normalize_max = mean[np.argmax(mean)]

        if normalize_minimum_idx:
            override_normalize_min = mean[normalize_minimum_idx]
        elif map_minimum_to_zero:
            override_normalize_min = mean[np.argmin(mean)]
        else:
            override_normalize_min = None

    else:

        if normalize_maximum_idx != None:
            override_normalize_max = populations[normalize_maximum_idx]
        else:
            override_normalize_max = None

        if normalize_minimum_idx:
            override_normalize_min = populations[normalize_minimum_idx]
        elif map_minimum_to_zero:
            override_normalize_min = populations[np.argmin(populations)]
        else:
            override_normalize_min = None
    
    populations = normalize(populations,
                            map_minimum_to_zero=map_minimum_to_zero,
                            override_normalize_minimum=override_normalize_min,
                            override_normalize_maximum=override_normalize_max)
    
    if avg_repeats:
        mean, err = get_repeat_std_error(populations, Nr)

    if fit_guess_decay_tau == dv:
        convwidth = 3
        psm = np.convolve(populations,[1/convwidth]*convwidth,mode='same')
        peak_idx, peak_prop = find_peaks(psm,height=0.3)
        y = peak_prop['peak_heights']
        def _fit_func_decay(t, tau):
            return np.exp(-t/tau)
        
        if fit_guess_frequency == dv:
            dt_peaks = np.mean(np.diff(times[peak_idx]))
            fit_guess_frequency = 1/dt_peaks

        
        popt_decay, _ = curve_fit(_fit_func_decay,times[0:2],y[0:2])
        fit_guess_decay_tau = popt_decay[0]

    try:
        # Fit the data
        popt, _ = curve_fit(_fit_func_rabi_oscillation, times, populations,
                            p0=[fit_guess_frequency, fit_guess_phase,
                                 fit_guess_amp, fit_guess_offset,
                                   fit_guess_decay_tau],
                            bounds=((0.,0.,0.,0.,0.),(np.inf,2*np.pi,1.,1.,np.inf)))
        
        y_fit = _fit_func_rabi_oscillation(times, *popt)

        # Print the fit parameters
        print(r"Fit function: f(t) = A * exp(-t/tau) * (cos(Omega t / 2 + phi))**2 + B")
        print(f"Omega = 2*pi*{popt[0]/(2*np.pi)/1.e3:1.2f} kHz"
              +f"\n phi = {popt[1]},\n A = {popt[3]},"
              +f"\n B = {popt[2]},"
              +f"\n tau = {popt[4]}")

        rabi_frequency_hz = popt[0] / (2*np.pi)
    except Exception as e:
        print(e)
        y_fit = np.array([None]*len(times))
        popt = [None]*5
        rabi_frequency_hz = None

    
    # Plot the data and the fit
    if plot_bool:
        if figsize:
            fig, ax = plt.subplots(1,1,figsize=figsize)
        else:
            fig, ax = plt.subplots(1,1)

        c = [0.,0.4,1.]
        c_data = [0.,0.4,1.,1.]
        c_fit = [0.,0.4,1.,0.6]
        
        if avg_repeats:
            plt.scatter(times[::Nr]*1.e6, mean, color=c, label=f'Data (N={Nr})')
            if Nr > 1:
                plt.errorbar(times[::Nr]*1.e6, mean, err, fmt='None', ecolor=c)
            if plot_raw_data:
                c_data[3] = 0.4
                plt.scatter(times*1.e6, populations, color=c_data, s=5, label=f'Raw data')
        else:
            plt.scatter(times*1.e6, populations, color=c_data, label=f'Raw data')
                

        t_sm = np.linspace(times[0],times[-1],10000)
        try:
            ax.plot(t_sm*1.e6, _fit_func_rabi_oscillation(t_sm,*popt), color=c_fit, label='fit')
        except:
            pass
        ax.set_ylabel('fractional state population')
        ax.set_xlabel('t (us)')

        ax.legend(loc='lower right')
        
        title = f"Run ID: {ad.run_info.run_id}\n"
        title += f"RF frequency = {rf_frequency_hz/1.e6:1.2f} MHz\n"
        # title += r"f(t) = $A \ \exp(-t/\tau) \cos^2(\Omega t / 2 + \phi) + B$"
        title += r"$f(t) = B + (A/2) \exp(-t/\tau) \ \cos(\Omega t + \phi)$"
        if rabi_frequency_hz:
            title += f"\n$\\Omega = 2\\pi \\times {rabi_frequency_hz/1.e3:1.3f}$ kHz"

        ax.set_title(title)
        ax.set_ylim([-0.1,1.1])

        if fit_params_on_plot:
            try:
                fit_params_str = f"$\Omega$ = $2\pi \\times {popt[0]/(2*np.pi)/1.e3:1.2f}$ kHz"\
                    +f"\n$A = {popt[3]:1.2f}$, $B = {popt[2]:1.2f}$"\
                    +f"\n$\\tau = {popt[4]*1.e6:1.2f}$ us"
                if fit_params_on_left:
                    x_pos = 0.05
                    ha = 'left'
                else:
                    x_pos = 0.6
                    ha = 'left'
                ax.text(x_pos, 0.75, fit_params_str, transform=ax.transAxes,
                        bbox=dict(facecolor='white', alpha=0.5, edgecolor='black', boxstyle='round,pad=0.5'),
                        ha=ha)
            except:
                pass

    try:
        t_pi = np.pi / popt[0]
        print(f'pi time = {t_pi:1.4e} s')
    except:
        t_pi = None

    return t_pi, popt

def rabi_oscillation_2d(ad:atomdata,
                        populations_array=[],
                        include_idx=[0,-1],
                        exclude_idx=[],
                        normalize_maximum_idx=None,
                        map_minimum_to_zero=None,
                        normalize_minimum_idx=None,
                        plot_bool=True,
                        subplots_bool=True,
                        pi_time_at_peak=True,
                        detect_dips=False,
                        xvar0format='1.2e',xvar0mult=1.,xvar0unit='',
                        subplots_figsize=[],
                        plot_figsize=[],
                        fit_guess_frequency=dv_fit_guess_rabi_frequency,
                        fit_guess_phase=np.pi/2,
                        fit_guess_amp=1.,
                        fit_guess_offset=1.,
                        fit_guess_decay_tau=dv,
                        rabi_freq_threshold=500.):
    """Fits the signal (max-min sumOD) vs. pulse time to extract the rabi
    frequency and pi-pulse time, and pro
    duces a plot.

    xvar0: rf frequency
    xvar1: pulse time

    Args:
        ad (atomdata)
        include_idx (list, optional): Specifies the first and last index of the
        data that will be used for the fit. -1 in the second element uses to the
        end of the list.
        normalize_maximum_idx (int, optional): If a value is provided,
        normalizes the data so that the value at the index provided is mapped to
        1. Otherwise, normalizes to the maximum value in the populations array.
        If avg_repeats is True, the value of the mean at this index in the
        repeat averaged array.
        map_minimum_to_zero (bool, optional): If True, normalizes the data so
        that it is scaled between 0 and 1, where the value mapped to zero is
        chosen according to `normalize_minimum_idx`. If `normalize_minimum_idx`
        is not None, then this bool is overridden to True.
        normalize_minimum_idx (int, optional): If a value is provided,
        normalizes the data so that the value at the provided index is mapped to
        zero 0 (full intial contrast), where the value at the provided index is
        mapped to zero.
        avg_repeats (bool, optional): If True, averages repeats and plots with error bars.
        plot_bool (bool, optional): If True, plots the data and fit. Defaults to True.
        subplots_bool (bool, optional): If True, plots subplots for each set of
        scans over pulse time at fixed RF frequency. Includes fits.
        pi_time_at_peak (bool, optional): If True, assumes the initial
        population is zero and extracts the pi-pulse time as the location of the
        first peak in the fitted oscillation. If False, identifies the minimum
        as the pi-pulse time. Defaults to True.
        xvar0format (str, optional): Defaults to '1.2f'
        xvar0mult (float, optional): Defaults to 1.e-6 (to convert Hz to MHz)
        xvar0unit (str, optional): Defaults to 'MHz'.
        subplots_figsize (tuple, optional): 
        plot_figsize (tuple, optional):
        fit_guess_frequency,
        fit_guess_phase,
        fit_guess_amp,
        fit_guess_offset,
        rabi_freq_threshold (float, optional): The threshold below which a fit
        resulting in this rabi frequency will be discarded.

    Returns:
        rabi_frequencies_hz (np.array): The Rabi frequency in Hz.
        t_pi (np.array): The pi pulse times in seconds.
        rf_frequencies (np.array): The RF frequencies at which each Rabi
        frequency / pi pulse time was measured.
    """    
    
    rabi_frequencies_hz = []
    t_pis = []

    populations_array = np.asarray(populations_array)

    if populations_array.size:
        populations_array = populations_array
    else:
        rel_amps = np.asarray([[np.max(sumod_x)-np.min(sumod_x) for sumod_x in sumod_for_this_field] for sumod_for_this_field in ad.sum_od_x])
        populations_array = rel_amps

    if detect_dips:
        populations_array = -populations_array

    xvar0_idx = 0

    # Define the Rabi oscillation function
    def _fit_func_rabi_oscillation(t, Omega, phi, B, A, tau):
        # return A * np.exp(-t/tau) * np.abs(np.cos(0.5 * Omega * t + phi))**2
        return 0.5 * (B + A * np.exp(-t/tau) * np.cos(Omega * t + phi) )

    times0 = ad.xvars[1]

    if subplots_bool:
        plt.figure()
        if subplots_figsize:
            fig, ax = plt.subplots(1,len(ad.xvars[0]),figsize=subplots_figsize)
        else:
            fig, ax = plt.subplots(1,len(ad.xvars[0]),figsize=(15,3))

    fit_results = []

    for populations in populations_array:
        times = times0

        populations = populations.flatten()
        populations = crop_array_by_index(populations,include_idx,exclude_idx)
        times = crop_array_by_index(times,include_idx,exclude_idx)
        populations, times = remove_infnan(populations, times)

        # mask = rm_outliers(populations,'mean',0.5)
        # populations = populations[mask]
        # times = times[mask]

        if normalize_maximum_idx != None:
            override_normalize_max = populations[normalize_maximum_idx]
        else:
            override_normalize_max = None

        if normalize_minimum_idx:
            override_normalize_min = populations[normalize_minimum_idx]
        elif map_minimum_to_zero:
            override_normalize_min = populations[np.argmin(populations)]
        else:
            override_normalize_min = None

        populations = normalize(populations,
                                map_minimum_to_zero=map_minimum_to_zero,
                                override_normalize_minimum=override_normalize_min,
                                override_normalize_maximum=override_normalize_max)

        if fit_guess_decay_tau == dv:
            peak_idx, peak_prop = find_peaks(populations,height=0.5)
            y = peak_prop['peak_heights']
            def _fit_func_decay(t, tau):
                return np.exp(-t/tau)
            popt_decay, _ = curve_fit(_fit_func_decay,times[peak_idx],y)
            fit_guess_decay_tau = popt_decay[0]

        # Fit the data
        try:
            popt, _ = curve_fit(_fit_func_rabi_oscillation, times, populations,
                            p0=[fit_guess_frequency, fit_guess_phase,
                                 fit_guess_amp, fit_guess_offset,
                                   fit_guess_decay_tau],
                            bounds=((0.,0.,0.,0.,0.),(np.inf,2*np.pi,1.,1.,np.inf)))

            y_fit = _fit_func_rabi_oscillation(times, *popt)
            f_rabi = popt[0]/(2*np.pi)
            # if f_rabi < rabi_freq_threshold:
            #     raise ValueError(f"Fitted Rabi frequency ({f_rabi/1.e3} kHz) below threshold ({rabi_freq_threshold/1.e3} kHz)")
            rabi_frequencies_hz.append(f_rabi)
        except Exception as e:
            print(e)
            popt = [None]*5
            y_fit = np.array([None]*len(times))
            rabi_frequencies_hz.append(None)
            
        fit_results.append(popt)

        try:
            if not pi_time_at_peak:
                y_fit = -y_fit
            peak_idx, _ = find_peaks(y_fit)
            t_pis.append(times[peak_idx][0])
        except:
            t_pis.append([None])

        if subplots_bool:
        # Plot the data and the fit
            c = [0.,0.4,1.]
            ax[xvar0_idx].scatter(times*1.e6, populations, label='Data', color=c)
            t_sm = np.linspace(times[0],times[-1],10000)
            if np.all(popt != None):
                ax[xvar0_idx].plot(t_sm*1.e6, _fit_func_rabi_oscillation(t_sm,*popt), 'k-', label='Fit')
            if rabi_frequencies_hz[xvar0_idx]:
                title = f"$f_R = {rabi_frequencies_hz[xvar0_idx]/1.e3:1.2f}$"
                ax[xvar0_idx].set_title(title)
            xlabel = f"{ad.xvarnames[1]}"
            xlabel += f"\n\n{ad.xvars[0][xvar0_idx]*xvar0mult:{xvar0format}}"
            ax[xvar0_idx].set_xlabel(xlabel)
            if xvar0_idx != 0:
                ax[xvar0_idx].set_yticks([])
        
        xvar0_idx += 1

    rabi_frequencies_hz = np.array(rabi_frequencies_hz)

    if subplots_bool:
        ymax = 0
        ymin = 100000
        for ax0 in ax:
            this_ymin, this_ymax = ax0.get_ylim()
            if this_ymax > ymax:
                ymax = this_ymax
            if this_ymin < ymin:
                ymin = this_ymin
        [ax0.set_ylim([ymin,ymax]) for ax0 in ax]
        title = f"Run ID: {ad.run_info.run_id}\n"
        title += r"$f(t) = 0.5 \ \left[ B + A \exp(-t/\tau) \ \cos(\Omega t + \phi) \right]$"
        title += f"\n$f_{{Rabi}} = \\Omega / 2\\pi$ (kHz)"
        fig.suptitle(title)
        fig.supxlabel(f"{ad.xvarnames[0]} ({xvar0unit})")
        fig.tight_layout()
        plt.show()

    if np.all([f_rabi == None for f_rabi in rabi_frequencies_hz]):
        plot_bool = False

    if plot_bool:
        idx = (rabi_frequencies_hz != None)
        rabi_frequencies_hz[idx] = rabi_frequencies_hz[idx]/1.e3
        if plot_figsize:
            rabi_fig = plt.figure(figsize=plot_figsize)
        else:
            rabi_fig = plt.figure()
        title = f"Run ID: {ad.run_info.run_id}\n"
        title += r"$f(t) = 0.5 \ \left[ B + A \exp(-t/\tau) \ \cos(\Omega t + \phi) \right]$\n"
        title += f"\nRabi frequency vs. {ad.xvarnames[0]}"
        plt.title(title)
        plt.scatter(ad.xvars[0],rabi_frequencies_hz)
        # plt.xlabel(f'{ad.xvars[0]*xvar0mult:{xvar0format}}')
        plt.xlabel(ad.xvarnames[0])
        plt.ylabel(r'Rabi frequency = $\Omega / 2 \pi$ (kHz)')
        plt.tight_layout()
        plt.show()

    rf_frequencies = ad.xvars[0]

    return rabi_frequencies_hz, t_pis, rf_frequencies, fit_results

def magnetometry_1d(ad,F0=2.,mF0=0.,F1=1.,mF1=1.,
                    axis = 0,
                 plot_bool=True,
                 find_field=True,
                 detect_dips=False,
                 average_multiple_peaks=False,
                 param_of_interest='',
                 transition_peak_idx=-1,
                 min_B = 0.,
                 max_B = 600.,
                 peak_prominence=10):
    """Analyzes the sum_od_x for each shot and produces an array of the max-min
    OD ("signal") vs. the RF center frequency. Extracts the peak signal from each 
    of these arrays, and finds the frequency where it occurs. Based on expected
    microwave frequency for the known transition (specified by user), looks up
    the magnitude of magnetic field. 
    
    Produces a plot of the magnetic field vs. the scanned variable.

    Args:
        ad (atomdata): _description_
        F0 (int, optional): The F quantum number of the initial state. Defaults to 2.
        mF0 (int, optional): The mF quantum number of the inital state. Defaults to 0.
        F1 (int, optional): The F quantum number of the final state. Defaults to 2.
        mF1 (int, optional): The mF quantum number of the inital state. Defaults to 1.
        axis (int, optional): The axis of the sumod to use for the peak finding.
        Defaults to 0 (x).
        plot_bool (bool, optional): If True, plots the signal vs. frequency
        for each value of the scanned xvar. Defaults to True.
        detect_dips (bool, optional): If True, inverts the signal to identify a
        loss signal. Defaults to False.
        param_of_interest (str, optional): If specified, adds the key and value
        of the param with that key to the title.
        transition_peak_idx (int, optional): state specified by the quantum numbers F0,
        mF0, F1, mF1. Indexes as a list, with the peaks from lowest to highest
        frequency. Default is the last peak (-1).
        min_B (float, optional): the minimum B value in Gauss to use for the
        calculation, useful if the transition frequency is non-monatonic with
        magnetic field. Defaults to 0.
        max_B (float, optional): the maximum B value in Gauss to use for the
        calculation, useful if the transition frequency is non-monatonic with
        magnetic field. Defaults to 600.
        peak_prominence (float, optional): Specifies how prominent a peak has to
        be in order to be counted.
    """
    if axis == 0:
        sumdist = ad.sum_od_x
    elif axis == 1:
        sumdist = ad.sum_od_y
    sm_sum_ods = [dist for dist in sumdist]
    rel_amps = [np.max(dist)-np.min(dist) for dist in sm_sum_ods]

    if detect_dips:
        rel_amps = - rel_amps
    
    peak_idx, _ = find_peaks(rel_amps,prominence=peak_prominence)
    x_peaks = ad.xvars[0][peak_idx]
    if average_multiple_peaks:
        x_peaks = np.average(x_peaks, weights=rel_amps[peak_idx])
        x_peaks = np.array([x_peaks])
    if find_field:
        try:
            this_transition = x_peaks[transition_peak_idx]
            B_measured = get_B(this_transition,F0,mF0,F1,mF1,min_B=min_B,max_B=max_B)
        except Exception as e:
            B_measured = None
    else:
        B_measured = None

    if plot_bool:
        plt.figure()
        plt.plot(ad.xvars[0],rel_amps)
        yylim = plt.ylim()
        plt.vlines(x=x_peaks,
                ymin=yylim[0],ymax=yylim[1],
                colors='k',linestyles='--')
        plt.ylabel("peak sumOD - min sumOD")
        plt.xlabel(f"{ad.xvarnames[0]}")
        title = f"Run ID: {ad.run_info.run_id}"
        if param_of_interest:
            try:
                title += f"\n{param_of_interest}={vars(ad.params)[param_of_interest]}"
            except:
                pass
        if B_measured:
            title += f"\nB = {B_measured:1.3f} G"

    plt.title(title)
    plt.tight_layout()
    plt.show()

    return B_measured, x_peaks

def magnetometry_2d(ad,F0=2.,mF0=0.,F1=1.,mF1=1.,
                    axis=0,
                 subplots_bool=True,
                 detect_dips=False,
                 average_multiple_peaks=False,
                 transition_peak_idx = -1,
                 peak_prominence=10,
                 min_B = 0.,
                 max_B = 600.,
                 subplots_figsize=[]):
    """Analyzes the sum_od_x for each shot and produces an array of the max-min
    OD ("signal") for each value of the scanned variable vs. the RF center
    frequency. Extracts the peak signal from each of these arrays, and finds the
    frequency where it occurs. Based on expected microwave frequency for the
    known transition (specified by user), looks up the magnitude of magnetic
    field. Produces a plot of the magnetic field vs. the scanned variable (the
    first xvar).

    xvar0: scanned variable
    xvar1: rf frequency

    Args:
        ad (atomdata): _description_
        F0 (int, optional): The F quantum number of the initial state. Defaults to 2.
        mF0 (int, optional): The mF quantum number of the inital state. Defaults to 0.
        F1 (int, optional): The F quantum number of the final state. Defaults to 2.
        mF1 (int, optional): The mF quantum number of the inital state. Defaults to 1.
        axis (int, optional): The axis of the sumod to use for the peak finding.
        Defaults to 0 (x).
        subplots_bool (bool, optional): If True, plots the signal vs. frequency
        for each value of the scanned xvar. Defaults to True.
        detect_dips (bool, optional): If True, inverts the signal to identify a
        loss signal. Defaults to False.
        average_multiple_peaks (bool, optional): If True, averages multiple
        peaks detected to obtain the center frequency. Use at your own risk --
        be sure that only one feature is visible. Defaults to False.
        transition_peak_idx (int, optional): state specified by the quantum numbers F0,
        mF0, F1, mF1. Indexes as a list, with the peaks from lowest to highest
        frequency. Default is the last peak (-1).
        min_B (float, optional): the minimum B value in Gauss to use for the
        calculation, useful if the transition frequency is non-monatonic with
        magnetic field. Defaults to 0.
        max_B (float, optional): the maximum B value in Gauss to use for the
        calculation, useful if the transition frequency is non-monatonic with
        magnetic field. Defaults to 600.
        peak_prominence (float, optional): Specifies how prominent a peak has to
        be in order to be counted.
    """    
    
    # if frequency_scan_axis == 1:
    #     scanned_xvar_axis = 0
    # elif frequency_scan_axis == 0:
    #     scanned_xvar_axis = 1
    
    if axis == 0:
        sumdist = ad.sum_od_x
    elif axis == 1:
        sumdist = ad.sum_od_y

    rel_amps = np.asarray([[np.max(sumod)-np.min(sumod) for sumod in sumod_for_this_field] for sumod_for_this_field in sumdist])
    if detect_dips:
        rel_amps = -rel_amps

    xvar0_idx = 0
    ymax = 0
    ymin = 100000

    B_measured_array = []
    transition_peaks = []
    all_peaks = []

    if subplots_bool:
        plt.figure()
        if subplots_figsize:
            fig, ax = plt.subplots(1,len(ad.xvars[0]),figsize=subplots_figsize)
        else:
            fig, ax = plt.subplots(1,len(ad.xvars[0]))

    for rel_amp in rel_amps:

        peak_idx, _ = find_peaks(rel_amp,prominence=peak_prominence)

        if peak_idx.size > 0:
            x_peaks = ad.xvars[1][peak_idx]
        
            if average_multiple_peaks:
                x_peaks = np.average(x_peaks, weights=rel_amp[peak_idx])
                x_peaks = np.array([x_peaks])
        else:
            x_peaks = np.array([])
        all_peaks.append(x_peaks)

        try:
            f_this_transition = x_peaks[transition_peak_idx]
            transition_peaks.append(f_this_transition)
            B_measured = get_B(f_this_transition,F0,mF0,F1,mF1,min_B=min_B,max_B=max_B)
            B_measured_array.append(B_measured)
        except Exception as e:
            f_this_transition = None
            B_measured = None
            B_measured_array.append(None)

        if subplots_bool:
            ax[xvar0_idx].plot(ad.xvars[1]/1.e6,rel_amp)
            ax[xvar0_idx].tick_params('x',labelrotation=90)
            if xvar0_idx != 0:
                ax[xvar0_idx].set_yticklabels([])
            else:
                ax[xvar0_idx].set_ylabel("maxOD-minOD")

            title = f"xvar0 = {ad.xvars[0][xvar0_idx]:1.3f}"

            if B_measured:
                title += f"\nB = {B_measured:1.3f} G"
            else:
                title += "\n"
            ax[xvar0_idx].set_title(title)

        xvar0_idx += 1

    if subplots_bool:

        for ax0 in ax:
                this_ymin, this_ymax = ax0.get_ylim()
                if this_ymax > ymax:
                    ymax = this_ymax
                if this_ymin < ymin:
                    ymin = this_ymin

        for i in range(len(ax)):
            ax[i].set_ylim([ymin,ymax])
            these_peaks = all_peaks[i]
            for peak in these_peaks:
                if peak:
                    ax[i].vlines(x=peak/1.e6,
                            ymin=ymin,ymax=ymax,
                            colors='k',linestyles='--')

        title = f"Run ID: {ad.run_info.run_id}"
        title += f"\nxvar0 = {ad.xvarnames[0]}"
        fig.suptitle(title)
        fig.supxlabel(ad.xvarnames[1])
        fig.tight_layout()
        plt.show()

    if not np.all([B == None for B in B_measured_array]):
        plt.figure()
        title = f"Run ID: {ad.run_info.run_id}"
        plt.scatter(ad.xvars[0],B_measured_array)
        plt.xlabel(f"{ad.xvarnames[0]}")
        plt.ylabel('measured B field (G)')
        plt.title(title)
        plt.show()

    

    return B_measured_array, transition_peaks