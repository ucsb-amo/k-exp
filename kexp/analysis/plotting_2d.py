import matplotlib.pyplot as plt
import numpy as np
from kexp.analysis import atomdata

def plot_image_grid(ad:atomdata, var1_idx=0, var2_idx=1,
                    xvarformat="1.2f",
                     xvar1format="",
                     xvar2format="",
                     xvar1mult=1.,
                     xvar2mult=1.,
                     od_max=0.,
                     figsize=[]):
    if not xvar1format:
        xvar1format = xvarformat
    if not xvar2format:
        xvar2format = xvarformat
    # Extract necessary attributes
    od = ad.od
    if od_max == 0.:
        od_max = np.max(od)
    xvars = ad.xvars
    xvarnames = ad.xvarnames
    
    # Get the values of the two independent variables
    var1_values = xvars[var1_idx]
    var2_values = xvars[var2_idx]
    
    # Get the dimensions of the grid
    num_var1_values = len(var1_values)
    num_var2_values = len(var2_values)
    
    # Create the plot grid
    if figsize:
        fig, axes = plt.subplots(num_var1_values, num_var2_values, figsize=figsize)
    else:
        fig, axes = plt.subplots(num_var1_values, num_var2_values)
    
    # Plot each image in the grid
    for i in range(num_var1_values):
        for j in range(num_var2_values):
            ax = axes[i, j]
            img = od.take(indices=[i], axis=var1_idx).take(indices=[j], axis=var2_idx).squeeze()
            ax.imshow(img,vmin=0.,vmax=od_max)
            ax.set_xticks([])
            ax.set_yticks([])
    
    # Label each side of the grid with the corresponding element of xvarnames
    # Label along the appropriate side with the value of the corresponding independent variable
            if i == num_var1_values - 1:
                ax.set_xlabel(f'{var2_values[j]*xvar2mult:{xvar2format}}')
            if j == 0:
                ax.set_ylabel(f'{var1_values[i]*xvar1mult:{xvar1format}}')
    
    fig.supylabel(xvarnames[var1_idx])
    fig.supxlabel(xvarnames[var2_idx])
    plt.suptitle(f"Run ID: {ad.run_info.run_id}")

    plt.tight_layout()
    plt.show()

    return fig, ax