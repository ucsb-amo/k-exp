import numpy as np
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt
from scipy.signal import find_peaks
from kexp.analysis import atomdata
from kexp.analysis.helper.datasmith import normalize, crop_array_by_index, find_n_max_indices

def get_best_result_idx(ad:atomdata,
                        figure_of_merit_key='atom_number',
                        figure_of_merit_array=[],
                        N_best_shots=5):
    
    fom_array = np.array([])
    try:
        fom_array = vars(ad)[figure_of_merit_key]
        fom_array: np.ndarray
    except Exception as e:
        pass
    
    figure_of_merit_label = ""
    figure_of_merit_array = np.asarray(figure_of_merit_array)
    if np.size(figure_of_merit_array):
        fom_array = figure_of_merit_array
        print(f"figure_of_merit_param is set to '{figure_of_merit_key}', but argument figure_of_merit_array. Using figure_of_merit_array.")
        figure_of_merit_label = input("input a label for the figure of merit:")
    elif figure_of_merit_label == "":
        figure_of_merit_label = figure_of_merit_key
        
    if fom_array.size != np.prod(ad.xvardims):
        raise ValueError("Figure of merit array must have one value per shot. Examples are atom_number, fit_sd_x, etc. Cannot be an array per shot as in, od, sum_od, etc.")
    
    n_max_idx = find_n_max_indices(fom_array, N=N_best_shots)
    n_best_shot_dict_list = [dict() for _ in range(N_best_shots)]
    for j in range(N_best_shots):
        n_best_shot_dict_list[j]['idx'] = n_max_idx[j]
        n_best_shot_dict_list[j]['fom_key'] = figure_of_merit_label
        n_best_shot_dict_list[j]['fom'] = fom_array[n_max_idx[j]]
        for i in range(ad.Nvars):
            n_best_shot_dict_list[j][ad.xvarnames[i]] = ad.xvars[i][n_max_idx[j][i]]

    return n_best_shot_dict_list

def plot_n_best_od(ad:atomdata,
                figure_of_merit_key = 'atom_number',
                figure_of_merit_array = [],
                figure_of_merit_label = "",
                N_best_shots = 5,
                lines=False,
                max_od=0.,
                figsize=[],
                aspect='auto'):
# Extract necessary information

    n_best_shots = get_best_result_idx(ad,
                                    figure_of_merit_key,
                                    figure_of_merit_array,
                                    N_best_shots)
    
    figure_of_merit_label = n_best_shots[0]['fom_key']

    od = []
    for j in range(N_best_shots):
        od.append(ad.od[n_best_shots[j]['idx']])
    od = np.array(od)

    if max_od == 0.:
        max_od = np.max(od)

    # Calculate the dimensions of the stitched image
    n, px, py = od.shape
    # n_repeats = int(ad.params.N_repeats)
    n_repeats = 1

    total_width = N_best_shots * px
    max_height = n_repeats * py

    # Create a figure and axis for plotting
    if figsize:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig, ax = plt.subplots()

    # Initialize x position for each image
    x_pos = 0
    y_pos = 0

    # Plot each image and label with xvar value
    for i in range(N_best_shots):
        for j in range(n_repeats):
            idx = j + i*n_repeats
            img = od[idx]
            ax.imshow(img, extent=[x_pos, x_pos+px, y_pos, y_pos+py],
                    vmin=0.,vmax=max_od, origin='lower')
            ax.axvline()
            y_pos += py
        y_pos = 0
        x_pos += px

    plt.gca().set_aspect(aspect)

    # Set axis labels and title
    ax.set_xlabel(f'ranking by {figure_of_merit_label}')
    ax.set_title(f"Run ID: {ad.run_info.run_id}")

    # Set the x-axis limits to show all images
    ax.set_xlim(0, total_width)
    ax.set_ylim(0, max_height)

    # Remove y-axis ticks and labels
    ax.yaxis.set_visible(False)
    ax.xaxis.set_ticks([])

    def make_labels():
        labels = []
        for n in range(N_best_shots):
            ndict = n_best_shots[n]
            label = ""
            label += f"index: {str(ndict['idx'])}\n"
            label += f"{figure_of_merit_label}={ndict['fom']:1.3g}\n"
            keylist = list(ndict.keys())[2:]
            for xvidx in range(len(keylist)):
                key = keylist[xvidx]
                label += f"{key}[{ndict['idx'][xvidx]}]={ndict[key]:1.6g}\n"
            labels.append(label)
        return labels

    # Set ticks at the center of each sub-image and rotate them vertically
    tick_positions = np.arange(px/2, total_width, px)
    ax.set_xticks(tick_positions)
    xvarlabels = make_labels()
    ax.set_xticklabels(xvarlabels, rotation='vertical', ha='center')
    plt.minorticks_off()

    if lines:
        for pos in np.arange(px, total_width, px):
            ax.axvline(pos, color='white', linewidth=0.5)

    # Show the plot
    fig.tight_layout()
    plt.show()

    return n_best_shots
