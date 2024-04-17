import matplotlib.pyplot as plt
import numpy as np
from kexp.analysis import atomdata

def plot_image_grid(ad:atomdata, var1_idx=0, var2_idx=1,
                    xvarformat="1.2f",
                     xvar0format="",
                     xvar1format="",
                     xvar0mult=1.,
                     xvar1mult=1.,
                     max_od=0.,
                     figsize=[]):
    if not xvar0format:
        xvar0format = xvarformat
    if not xvar1format:
        xvar1format = xvarformat
    # Extract necessary attributes
    od = ad.od
    if max_od == 0.:
        max_od = np.max(od)
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
            ax.imshow(img,vmin=0.,vmax=max_od)
            ax.set_xticks([])
            ax.set_yticks([])
    
    # Label each side of the grid with the corresponding element of xvarnames
    # Label along the appropriate side with the value of the corresponding independent variable
            if i == num_var1_values - 1:
                ax.set_xlabel(f'{var2_values[j]*xvar1mult:{xvar1format}}',rotation=90)
            if j == 0:
                ax.set_ylabel(f'{var1_values[i]*xvar0mult:{xvar0format}}')

            ax.tick_params('x',labelrotation=90)
    
    fig.supylabel(xvarnames[var1_idx])
    fig.supxlabel(xvarnames[var2_idx])
    plt.suptitle(f"Run ID: {ad.run_info.run_id}")

    plt.tight_layout()
    plt.show()

    return fig, ax

def mixOD_grid(ad,
                xvarformat="1.2g",
                xvar0format="",
                xvar1format="",
                xvar0mult=1.,
                xvar1mult=1.,
                max_od=0.,
                figsize=[]):

    # Assuming you have already loaded your 'ad' object
    # Extract relevant attributes
    if not xvar0format:
        xvar0format = xvarformat
    if not xvar1format:
        xvar1format = xvarformat
    # Extract necessary attributes
    od = ad.od
    if max_od == 0.:
        max_od = np.max(od)
        
    xvarnames = ad.xvarnames
    xvars = ad.xvars

    # Get dimensions
    n_1, n_2, px, py = od.shape

    # Create a grid to hold the stitched images
    grid_rows = n_1
    grid_cols = n_2
    full_image = np.zeros((grid_rows * px, grid_cols * py))

    # Stitch the images into the grid
    for i in range(n_1):
        for j in range(n_2):
            full_image[i * px: (i + 1) * px, j * py: (j + 1) * py] = od[i, j]

    # Create a figure and plot the stitched image
    if figsize:
        plt.figure(figsize=figsize)
    else:
        plt.figure(figsize=(10, 8))
    plt.imshow(full_image,vmin=0.,vmax=max_od)
    plt.title(f"Run ID: {ad.run_info.run_id}")
    plt.xlabel(xvarnames[1])  # Label x-axis with the second x-variable name
    plt.ylabel(xvarnames[0])  # Label y-axis with the first x-variable name

    # Set ticks and labels for x and y axes
    plt.xticks(np.arange(0.5 * py, grid_cols * py, py), f"{xvars[1]*xvar1mult:{xvar1format}}", rotation=90)
    plt.yticks(np.arange(0.5 * px, grid_rows * px, px), f"{xvars[0]*xvar0mult:{xvar0format}}")

    plt.show()

def plot_sum_od_fits(ad:atomdata,axis=0,
                     xvarformat='1.3f',
                     xvar0format='',
                     xvar1format='',
                     xvar0mult=1.,
                     xvar1mult=1.,
                     max_od=0.,
                     figsize=[]):
    
    if not xvar0format:
        xvar0format = xvarformat
    if not xvar1format:
        xvar1format = xvarformat
    # Extract necessary attributes
    od = ad.od
    if max_od == 0.:
        max_od = np.max(od)

    if axis == 0:
        fits = ad.cloudfit_x
        label = "x"
    elif axis == 1:
        fits = ad.cloudfit_y
        label = "y"
    else:
        raise ValueError("Axis must be 0 (x) or 1 (y)")
    
    ydata = [[fit.ydata for fit in fitt] for fitt in fits]
    yfitdata = [[fit.y_fitdata for fit in fitt] for fitt in fits]
    
    n0 = ad.od.shape[0]
    n1 = ad.od.shape[1]

    if figsize:
        fig, ax = plt.subplots(ad.od.shape[0], ad.od.shape[1], figsize=figsize)
    else:
        fig, ax = plt.subplots(ad.od.shape[0], ad.od.shape[1])

    ymax = 1.1*np.max(ydata)

    for i0 in range(n0):
        for i1 in range(n1):
            ax[i0][i1].plot(ydata[i0][i1])
            ax[i0][i1].plot(yfitdata[i0][i1])
            ax[i0][i1].set_ylim(0,ymax)
            ax[i0,i1].set_yticklabels([])
            
            if i1 == 0:
                ax[i0][i1].set_ylabel(f"{ad.xvars[0][i0]*xvar0mult:{xvar0format}}")
            else:
                ax[i0][i1].set_yticks([])
                
            if i0 == n0-1:
                ax[i0][i1].set_xlabel(f"{ad.xvars[1][i1]*xvar1mult:{xvar1format}}", rotation='vertical')
            else:
                ax[i0,i1].set_xticks([])

    fig.supylabel(f"{ad.xvarnames[0]}")
    fig.supxlabel(f"{ad.xvarnames[1]}")
    fig.suptitle(f"Run ID: {ad.run_info.run_id}\nsum_od_{label}")
    fig.tight_layout()
    plt.show() 

    return fig, ax