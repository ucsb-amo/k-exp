import numpy as np
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt
from scipy.signal import find_peaks
from kexp.analysis import atomdata

def get_B(f_mf0_mf1_transition,
          F0=2.,mF0=0.,F1=1.,mF1=1.):

        from kamo.atom_properties.k39 import Potassium39
        k = Potassium39()
        B = np.linspace(0.,10.,20000)
        f_transitions = abs(k.get_microwave_transition_frequency(4,0,.5,F0,mF0,F1,mF1,B)) * 1.e6

        def find_xval(y_val,y_vec,x_vec):
            y = np.asarray(y_vec)
            idx = (np.abs(y - y_val)).argmin()
            return x_vec[idx]

        return find_xval(f_mf0_mf1_transition,f_transitions,B)

def rabi_oscillation(ad,rf_frequency_hz,
                     plot_bool=True,
                     pi_time_at_peak=True):
    """Fits the signal (max-min sumOD) vs. pulse time to extract the rabi
    frequency and pi-pulse time, and produces a plot.

    xvar: rf pulse time.

    Args:
        ad (atomdata)
        rf_frequency_hz (float): The RF drive frequency in Hz.
        plot_bool (bool, optional): If True, plots the data and fit. Defaults to True.
        pi_time_at_peak (bool, optional): If True, assumes the initial
        population is zero and extracts the pi-pulse time as the location of the
        first peak in the fitted oscillation. If False, identifies the minimum
        as the pi-pulse time. Defaults to True.

    Returns:
        t_pi: The pi pulse time in seconds.
    """

    # Define the Rabi oscillation function
    def _fit_func_rabi_oscillation(t, Omega, phi, B, A):
        return A * np.abs(np.cos(0.5 * Omega * t + phi))**2 + B

    # Suppose these are your data
    times = ad.xvars[0]  # replace with your pulse times

    sm_sum_ods = [sumod_x for sumod_x in ad.sum_od_x]
    rel_amps = [np.max(sumod_x)-np.min(sumod_x) for sumod_x in sm_sum_ods]
    populations = rel_amps  # replace with your atom populations

    # Fit the data
    popt, _ = curve_fit(_fit_func_rabi_oscillation, times, populations, p0=[1000., np.pi, 10., 0.])

    y_fit = _fit_func_rabi_oscillation(times, *popt)

    # Print the fit parameters
    print(r"Fit function: f(t) = A * (cos(Omega t / 2 + phi))**2 + B")
    print(f"Omega = {popt[0]},\n phi = {popt[1]},\n B = {popt[2]},\n A = {popt[3]}")

    rabi_frequency_hz = popt[0] / (2*np.pi)

    if plot_bool:
    # Plot the data and the fit
        plt.scatter(times*1.e6, populations, label='Data')
        plt.plot(times*1.e6, y_fit, 'k-', label='Fit')
        plt.ylabel('max(sum od x) - min(sum od x)')
        plt.xlabel('t (us)')
        plt.legend()
        title = f"Run ID: {ad.run_info.run_id}\n"
        title += r"f(t) = $A \ \cos^2(\Omega t / 2 + \phi) + B$"
        title += f"\n$\\Omega = 2\\pi \\times {rabi_frequency_hz/1.e3:1.3f}$ kHz\n"
        title += f"RF frequency = {rf_frequency_hz/1.e6:1.2f} MHz"

        plt.title(title)
        plt.show()

    if not pi_time_at_peak:
        y_fit = -y_fit
    peak_idx, _ = find_peaks(y_fit)
    t_pi = times[peak_idx][0]

    return t_pi

def rabi_oscillation_2d(ad:atomdata,
                        plot_bool=True,
                        subplots_bool=True,
                        pi_time_at_peak=True,
                        detect_dips=False,
                        xvar0format='1.4f',xvar0mult=1.e-6,xvar0unit='MHz',
                        subplots_figsize=[],
                        plot_figsize=[]):
    """Fits the signal (max-min sumOD) vs. pulse time to extract the rabi
    frequency and pi-pulse time, and produces a plot.

    xvar0: rf frequency
    xvar1: pulse time

    Args:
        ad (atomdata)
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

    Returns:
        rabi_frequencies_hz (np.array): The Rabi frequency in Hz.
        t_pi (np.array): The pi pulse times in seconds.
        rf_frequencies (np.array): The RF frequencies at which each Rabi
        frequency / pi pulse time was measured.
    """    
    
    rabi_frequencies_hz = []
    t_pis = []

    rel_amps = np.asarray([[np.max(sumod_x)-np.min(sumod_x) for sumod_x in sumod_for_this_field] for sumod_for_this_field in ad.sum_od_x])
    if detect_dips:
        rel_amps = -rel_amps
 
    xvar0_idx = 0

    # Define the Rabi oscillation function
    def _fit_func_rabi_oscillation(t, Omega, phi, B, A):
        return A * np.abs(np.cos(0.5 * Omega * t + phi))**2 + B

    times = ad.xvars[1]

    if subplots_bool:
        plt.figure()
        if subplots_figsize:
            fig, ax = plt.subplots(1,len(ad.xvars[0]),figsize=subplots_figsize)
        else:
            fig, ax = plt.subplots(1,len(ad.xvars[0]),figsize=(15,3))

    for rel_amp in rel_amps:

        populations = rel_amp

        popt, pcov = curve_fit(_fit_func_rabi_oscillation, times, populations,
                                p0=[2000., np.pi, 10., 5.])

        y_fit = _fit_func_rabi_oscillation(times, *popt)

        rabi_frequencies_hz.append(popt[0]/(2*np.pi))

        if not pi_time_at_peak:
            y_fit = -y_fit
        peak_idx, _ = find_peaks(y_fit)
        if peak_idx.size > 0:
            t_pis.append(times[peak_idx][0])
        else:
            t_pis.append([0.])

        if subplots_bool:
        # Plot the data and the fit
            ax[xvar0_idx].scatter(times*1.e6, populations, label='Data')
            ax[xvar0_idx].plot(times*1.e6, y_fit, 'k-', label='Fit')
            title = f"$f_R = {rabi_frequencies_hz[xvar0_idx]/1.e3:1.2f}$"
            xlabel = f"{ad.xvarnames[1]}"
            xlabel += f"\n\n{ad.xvars[0][xvar0_idx]*xvar0mult:{xvar0format}}"
            ax[xvar0_idx].set_xlabel(xlabel)
            ax[xvar0_idx].set_title(title)
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
        title += r"$y(t) = A \ \cos^2(\Omega t / 2 + \phi) + B$"
        title += f"\n$f_{{Rabi}} = \\Omega / 2\\pi$ (kHz)"
        fig.suptitle(title)
        fig.supxlabel(f"{ad.xvarnames[0]} ({xvar0unit})")
        fig.tight_layout()
        plt.show()

    if plot_bool:
        if plot_figsize:
            rabi_fig = plt.figure(figsize=plot_figsize)
        else:
            rabi_fig = plt.figure()
        title = f"Run ID: {ad.run_info.run_id}\n"
        title += r"$f(t) = A \ \cos^2(\Omega t / 2 + \phi) + B$"
        title += f"\nRabi frequency vs. {ad.xvarnames[0]}"
        plt.title(title)
        plt.scatter(ad.xvars[0],rabi_frequencies_hz/1.e3)
        # plt.xlabel(f'{ad.xvars[0]*xvar0mult:{xvar0format}}')
        plt.xlabel(ad.xvarnames[0])
        plt.ylabel(r'Rabi frequency = $\Omega / 2 \pi$ (kHz)')
        plt.tight_layout()
        plt.show()

    rf_frequencies = ad.xvars[0]

    return rabi_frequencies_hz, t_pis, rf_frequencies

def magnetometry_1d(ad,F0=2.,mF0=0.,F1=1.,mF1=1.,
                 plot_bool=True,
                 find_field=True,
                 detect_dips=False,
                 param_of_interest='',
                 peak_index=-1,
                 peak_prominence=10):
    """Analyzes the sum_od_x for each shot and produces an array of the max-min
    OD ("signal") vs. the RF center frequency. Extracts the peak signal from each 
    of these arrays, and finds the frequency where it occurs. Based on expected
    microwave frequency for the known transition (specified by user), looks up
    the magnitude of magnetic field. 
    
    Produces a plot of the magnetic field vs. the scanned variable.

    Args:
        ad (atomdata): _description_
        F0 (int, optional): Defaults to 2.
        mF0 (int, optional): Defaults to 0.
        F1 (int, optional): Defaults to 2.
        mF1 (int, optional): Defaults to 1.
        plot_bool (bool, optional): If True, plots the signal vs. frequency
        for each value of the scanned xvar. Defaults to True.
        detect_dips (bool, optional): If True, inverts the signal to identify a
        loss signal. Defaults to False.
        param_of_interest (str, optional): If specified, adds the key and value
        of the param with that key to the title.
        peak_index (int, optional): The index of the peak corresponding to the
        state specified by the quantum numbers F0, mF0, F1, mF1.
        peak_prominence (float, optional): Specifies how prominent a peak has to
        be in order to be counted.
    """
    
    sm_sum_ods = [sumod_x for sumod_x in ad.sum_od_x]
    rel_amps = [np.max(sumod_x)-np.min(sumod_x) for sumod_x in sm_sum_ods]

    if detect_dips:
        rel_amps = - rel_amps
    
    peak_idx, _ = find_peaks(rel_amps,prominence=peak_prominence)
    x_peaks = ad.xvars[0][peak_idx]
    if find_field:
        try:
            this_transition = x_peaks[peak_index]
            print(this_transition)
            B_measured = get_B(this_transition,F0,mF0,F1,mF1)
        except Exception as e:
            print(e)
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

    return x_peaks

def magnetometry_2d(ad,F0=2.,mF0=0.,F1=1.,mF1=1.,
                 subplots_bool=True,
                 detect_dips=False,
                 average_multiple_peaks=False,
                 peak_idx = -1,
                 peak_prominence=10):
    """Analyzes the sum_od_x for each shot and produces an array of the max-min
    OD ("signal") for each value of the scanned variable vs. the RF center
    frequency. Extracts the peak signal from each of these arrays, and finds the
    frequency where it occurs. Based on expected microwave frequency for the
    known transition (specified by user), looks up the magnitude of magnetic
    field. Produces a plot of the magnetic field vs. the scanned variable (the
    first xvar).

    Args:
        ad (atomdata): _description_
        F0 (int, optional): Defaults to 2.
        mF0 (int, optional): Defaults to 0.
        F1 (int, optional): Defaults to 2.
        mF1 (int, optional): Defaults to 1.
        subplots_bool (bool, optional): If True, plots the signal vs. frequency
        for each value of the scanned xvar. Defaults to True.
        detect_dips (bool, optional): If True, inverts the signal to identify a
        loss signal. Defaults to False.
        average_multiple_peaks (bool, optional): If True, averages multiple
        peaks detected to obtain the center frequency. Use at your own risk --
        be sure that only one feature is visible. Defaults to False.
        peak_idx (int, optional): state specified by the quantum numbers F0,
        mF0, F1, mF1. Default is the last peak.
        peak_prominence (float, optional): Specifies how prominent a peak has to
        be in order to be counted.
    """    
    
    # if frequency_scan_axis == 1:
    #     scanned_xvar_axis = 0
    # elif frequency_scan_axis == 0:
    #     scanned_xvar_axis = 1

    rel_amps = np.asarray([[np.max(sumod_x)-np.min(sumod_x) for sumod_x in sumod_for_this_field] for sumod_for_this_field in ad.sum_od_x])
    if detect_dips:
        rel_amps = -rel_amps

    xvar0_idx = 0

    B_measured_array = []

    if subplots_bool:
        plt.figure()
        fig, ax = plt.subplots(1,len(ad.xvars[0]))

    for rel_amp in rel_amps:

        peak_idx, _ = find_peaks(rel_amp,prominence=peak_prominence)
        x_peaks = ad.xvars[1][peak_idx]
    
        if average_multiple_peaks:
            x_peaks = np.average(x_peaks, weights=rel_amp[peak_idx])
            x_peaks = np.array([x_peaks])

        try:
            f_this_transition = x_peaks[-1]
            B_measured = get_B(f_this_transition,F0,mF0,F1,mF1)
            B_measured_array.append(B_measured)
        except Exception as e:
            print(e)
            f_this_transition = None
            B_measured = None
            B_measured_array.append(None)

        if subplots_bool:
            ax[xvar0_idx].plot(ad.xvars[1]/1.e6,rel_amp)
            ax[xvar0_idx].tick_params('x',labelrotation=90)
            ax[xvar0_idx].set_yticklabels([])
            yylim = ax[xvar0_idx].get_ylim()
            ax[xvar0_idx].vlines(x=x_peaks/1.e6,
                    ymin=yylim[0],ymax=yylim[1],
                    colors='k',linestyles='--')
            title = f"{ad.xvars[0][xvar0_idx]:1.3f} V"
            if B_measured:
                title += f"\nB = {B_measured:1.3f} G"
            ax[xvar0_idx].set_title(title)

        xvar0_idx += 1

    if subplots_bool:
        title = f"Run ID: {ad.run_info.run_id}"
        title += f"\nscanned var = {ad.xvarnames[0]}"
        fig.suptitle(title)
        fig.supxlabel(ad.xvarnames[0])
        fig.tight_layout()
        plt.show()

    plt.figure()
    title = f"Run ID: {ad.run_info.run_id}"
    plt.scatter(ad.xvars[0],B_measured_array)
    plt.xlabel(f"{ad.xvarnames[0]} V")
    plt.ylabel('measured B field (G)')
    plt.title(title)
    plt.show()