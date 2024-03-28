import numpy as np
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt
from scipy.signal import find_peaks

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

def rabi_oscillation(ad,plot_bool=True,
                     pi_time_at_peak=True):
    """Fits the signal (max-min sumOD) vs. pulse time to extract the rabi
    frequency and pi-pulse time, and produces a plot.

    Args:
        ad (atomdata)
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
    popt, pcov = curve_fit(_fit_func_rabi_oscillation, times, populations, p0=[1000., np.pi, 10., 0.])

    y_fit = _fit_func_rabi_oscillation(times, *popt)

    # Print the fit parameters
    print(r"Fit function: f(t) = A * (cos(Omega t / 2 + phi))**2 + B")
    print(f"Omega = {popt[0]},\n phi = {popt[1]},\n B = {popt[2]},\n A = {popt[3]}")

    if plot_bool:
    # Plot the data and the fit
        plt.scatter(times*1.e6, populations, label='Data')
        plt.plot(times*1.e6, y_fit, 'k-', label='Fit')
        plt.ylabel('max(sum od x) - min(sum od x)')
        plt.xlabel('t (us)')
        plt.legend()
        title = f"Run ID: {ad.run_info.run_id}\n"
        title += r"f(t) = $A \ \cos^2(\Omega t / 2 + \phi) + B$"
        title += f"\n$\\Omega = 2\\pi \\times {popt[0]/1.e3:1.2f}$ kHz\n"
        title += f"RF frequency = {ad.params.frequency_rf/1.e6:1.2f} MHz"
        plt.title(title)
        plt.show()

    if not pi_time_at_peak:
        y_fit = -y_fit
    peak_idx, _ = find_peaks(y_fit)
    t_pi = times[peak_idx][0]

    return t_pi

def rabi_oscillation_2d(ad,
                        plot_bool=True,
                        subplots_bool=True,
                        pi_time_at_peak=True,
                        detect_dips=False):
    """Fits the signal (max-min sumOD) vs. pulse time to extract the rabi
    frequency and pi-pulse time, and produces a plot.

    Data must be taken with the rf frequency as the first xvar, and the pulse
    time as the second.

    Args:
        ad (atomdata)
        plot_bool (bool, optional): If True, plots the data and fit. Defaults to True.
        pi_time_at_peak (bool, optional): If True, assumes the initial
        population is zero and extracts the pi-pulse time as the location of the
        first peak in the fitted oscillation. If False, identifies the minimum
        as the pi-pulse time. Defaults to True.

    Returns:
        t_pi: The pi pulse time in seconds.
    """    

    rel_amps = np.asarray([[np.max(sumod_x)-np.min(sumod_x) for sumod_x in sumod_for_this_field] for sumod_for_this_field in ad.sum_od_x])
    if detect_dips:
        rel_amps = -rel_amps

    xvar0_idx = 0

    # Define the Rabi oscillation function
    def _fit_func_rabi_oscillation(t, Omega, phi, B, A):
        return A * np.abs(np.cos(0.5 * Omega * t + phi))**2 + B

    # Suppose these are your data
    times = ad.xvars[0]  # replace with your pulse times

    if subplots_bool:
        plt.figure()
        fig, ax = plt.subplots(1,len(ad.xvars[0]))

    for rel_amp in rel_amps:

        populations = rel_amp  # replace with your atom populations

        # Fit the data
        popt, pcov = curve_fit(_fit_func_rabi_oscillation, times, populations, p0=[1000., np.pi, 10., 0.])

        y_fit = _fit_func_rabi_oscillation(times, *popt)

        # Print the fit parameters
        print(r"Fit function: f(t) = A * (cos(Omega t / 2 + phi))**2 + B")
        print(f"Omega = {popt[0]},\n phi = {popt[1]},\n B = {popt[2]},\n A = {popt[3]}")

        if subplots_bool:
        # Plot the data and the fit
            ax[xvar0_idx].scatter(times*1.e6, populations, label='Data')
            ax[xvar0_idx].plot(times*1.e6, y_fit, 'k-', label='Fit')
            ax[xvar0_idx].set_ylabel('max(sum od x) - min(sum od x)')
            ax[xvar0_idx].set_xlabel('t (us)')
            ax[xvar0_idx].legend()
            # title = f"Run ID: {ad.run_info.run_id}\n"
            # title += r"f(t) = $A \ \cos^2(\Omega t / 2 + \phi) + B$"
            title = f"$\\Omega = 2\\pi \\times {popt[0]/1.e3:1.2f}$ kHz\n"
            title += f"\nRF frequency = {ad.xvars[0][xvar0_idx]/1.e6:1.2f} MHz"
            ax[xvar0_idx].set_title(title)

        if subplots_bool:
            title = f"Run ID: {ad.run_info.run_id}"
            title += f"\nscanned var = {ad.xvarnames[0]}"
            fig.suptitle(title)
            fig.supxlabel(ad.xvarnames[0])
            fig.tight_layout()
            plt.show()

        plt.show()

        if plot_bool:
            plt.figure()
            title = f"Run ID: {ad.run_info.run_id}"
            title += f"\nRabi frequency vs. {ad.xvarnames[0]}"
            

        if not pi_time_at_peak:
            y_fit = -y_fit
        peak_idx, _ = find_peaks(y_fit)
        t_pi = times[peak_idx][0]

        xvar0_idx += 1

    return t_pi

def magnetometry_1d(ad,F0=2.,mF0=0.,F1=1.,mF1=1.,
                 plot_bool=True,
                 detect_dips=False,
                 xvar_of_interest='',
                 peak_index=-1,
                 peak_prominence=10):
    """Analyzes the sum_od_x for each shot and produces an array of the max-min
    OD ("signal") vs. the RF center frequency. Extracts the peak signal from each 
    of these arrays, and finds the frequency where it occurs. Based on expected
    microwave frequency for the known transition (specified by user), looks up
    the magnitude of magnetic field. Produces a plot of the magnetic field vs.
    the scanned variable (the first xvar).

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
        set_xvar
    """
    
    sm_sum_ods = [sumod_x for sumod_x in ad.sum_od_x]
    rel_amps = [np.max(sumod_x)-np.min(sumod_x) for sumod_x in sm_sum_ods]

    if detect_dips:
        rel_amps = - rel_amps
    
    peak_idx, _ = find_peaks(rel_amps,prominence=peak_prominence)
    x_peaks = ad.xvars[0][peak_idx]
    try:
        this_transition = x_peaks[peak_index]
        print(this_transition)
        B_measured = get_B(this_transition,F0,mF0,F1,mF1)
    except Exception as e:
        print(e)
        B_measured = None

    if plot_bool:
        plt.figure()
        plt.scatter(ad.xvars[0],rel_amps)
        yylim = plt.ylim()
        plt.vlines(x=x_peaks,
                ymin=yylim[0],ymax=yylim[1],
                colors='k',linestyles='--')
        plt.ylabel("peak sumOD - min sumOD")
        plt.xlabel(f"{ad.xvarnames[0]}")
        title = f"Run ID: {ad.run_info.run_id}"
        # if set_xvar:
            # title += f"\n{}={ad.params.v_zshim_current_op} V"
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