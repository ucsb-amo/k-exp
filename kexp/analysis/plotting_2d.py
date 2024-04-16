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