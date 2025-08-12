import numpy as np
import matplotlib.pyplot as plt

def xlabels_1d(xvar0, xvarmult, xvarformat):
    xvarlabels = []
    for val in xvar0:
        label = ""
        if isinstance(val,np.ndarray) or isinstance(val,list):
            for i in range(len(val)):
                if i == 0:
                    label += "["
                if i != 0:
                    label += ", "
                label += f"{val[i]*xvarmult:{xvarformat}}"
                if i == (len(val)-1):
                    label += "]"
        else:
            label += f"{val*xvarmult:{xvarformat}}"
        xvarlabels.append(label)
    return xvarlabels

def remap_xticks(func, fmt='', axis=0, ax=None):
    """
    Remap the current xtick labels by converting their text to float,
    mapping through func, and setting new labels at the same locations.

    Parameters:
        func: function to apply to the float values of the xtick labels
        ax: matplotlib axis (default: plt.gca())
    """
    if ax is None:
        ax = plt.gca()
    label_vals = get_ticklabel_values(axis,ax)
    new_labels = [f"{val:{fmt}}" for val in func(label_vals)]
    if axis == 0:
        ax.set_xticklabels(new_labels)
    elif axis == 1:
        ax.set_yticklabels(new_labels)

def format_xticks(fmt, axis=0, ax=None):
    """
    Change the x tick label format for the current axis.

    Parameters:
        fmt: format string, e.g. '1.2f', '1.1e', etc.
    """
    if ax == None:
        ax = plt.gca()
    label_vals = get_ticklabel_values(ax)
    new_labels = [f"{val:{fmt}}" for val in label_vals]
    if axis == 0:
        ax.set_xticklabels(new_labels)
    elif axis == 1:
        ax.set_yticklabels(new_labels)

def get_ticklabel_values(axis=0,ax=None):
    """
    Get the float values of the current x tick labels.
    """
    if ax == None:
        ax = plt.gca()
    # Get current tick locations and labels
    if axis == 0:
        ticklocs = ax.get_xticks()
        ticklabels = ax.get_xticklabels()
    elif axis == 1:
        ticklocs = ax.get_yticks()
        ticklabels = ax.get_yticklabels()
    # Convert label text to float
    try:
        label_vals = np.array([float(lbl.get_text()) for lbl in ticklabels])
    except ValueError:
        # fallback: use tick locations if labels are not numeric
        label_vals = ticklocs

    return label_vals