import matplotlib.pyplot as plt
import numpy as np
from kexp.analysis import atomdata

def plot_mixOD(ad:atomdata,xvarformat="1.2f",lines=False,max_od=0.):
    # Extract necessary information
    od = ad.od
    xvarnames = ad.xvarnames
    xvars = ad.xvars

    if max_od == 0.:
        max_od = np.max(od)

    # Calculate the dimensions of the stitched image
    n, px, py = od.shape
    total_width = n * px
    max_height = py

    # Create a figure and axis for plotting
    fig, ax = plt.subplots(figsize=(10, 6))

    # Initialize x position for each image
    x_pos = 0

    # Plot each image and label with xvar value
    for i in range(n):
        img = od[i]
        ax.imshow(img, extent=[x_pos, x_pos + px, 0, py], aspect='auto',
                  vmin=0.,vmax=max_od)
        ax.axvline()
        x_pos += px

    # Set axis labels and title
    ax.set_xlabel(xvarnames[0])
    ax.set_title(f"Run ID: {ad.run_info.run_id}")

    # Set the x-axis limits to show all images
    ax.set_xlim(0, total_width)

    # Remove y-axis ticks and labels
    ax.yaxis.set_visible(False)
    ax.xaxis.set_ticks([])

    # Set ticks at the center of each sub-image and rotate them vertically
    tick_positions = np.arange(px/2, total_width, px)
    ax.set_xticks(tick_positions)
    xvarticks = [f"{val:{xvarformat}}" for val in xvars[0]]
    ax.set_xticklabels(xvarticks, rotation='vertical', ha='center')
    plt.minorticks_off()

    if lines:
        for pos in np.arange(px, total_width, px):
            ax.axvline(pos, color='white', linewidth=0.5)

    # Show the plot
    fig.tight_layout()
    plt.show()

    return fig, ax

def plot_sum_od_fits(ad:atomdata,axis=0,
                    xvarformat='3.3g'):
    if axis == 0:
        fits = ad.cloudfit_x
        label = "x"
    elif axis == 1:
        fits = ad.cloudfit_y
        label = "y"
    else:
        raise ValueError("Axis must be 0 (x) or 1 (y)")
    
    ymax = np.max([np.max(fit.ydata) for fit in fits])

    fig, ax = plt.subplots(ad.params.N_repeats[0],ad.params.N_shots,layout='constrained')

    Nr = ad.params.N_repeats[0]
    Ns = ad.params.N_shots

    xvar = ad.xvars[0]

    if ad.params.N_repeats == 1:
        for i in range(Ns):

            yfit = fits[i].y_fitdata
            ydata = fits[i].ydata
            xdata = fits[i].xdata

            ax[i].plot(xdata*1.e6,ydata)
            ax[i].plot(xdata*1.e6,yfit)
            ax[i].set_ylim([0,1.1*ymax])
            ax[i].set_xlabel(f"{xvar[i]:{xvarformat}}")
            ax[i].set_xticks([])

            if i != 0:
                ax[i].set_yticklabels([])
            else:
                ax[i].set_yticks([])
    else:
        for j in range(Nr):
            for i in range(Ns):

                idx = j + i*Nr

                yfit = fits[idx].y_fitdata
                ydata = fits[idx].ydata
                xdata = fits[idx].xdata

                ax[j,i].plot(xdata*1.e6,ydata)
                ax[j,i].plot(xdata*1.e6,yfit)
                ax[j,i].set_ylim([0,1.1*ymax])

                ax[j,i].set_xticks([])
                
                if i != 0:
                    ax[j,i].set_yticklabels([])
                else:
                    ax[j,i].set_yticks([])

                if j == Nr-1:
                    ax[j,i].set_xlabel(f"{xvar[idx]:{xvarformat}}")

    fig.suptitle(f"Run ID: {ad.run_info.run_id}\nsum_od_{label}")
    fig.supxlabel(ad.xvarnames[0])

    fig.set_figheight(3)
    fig.set_figwidth(18)

    return fig, ax

def plot_fit_residuals(ad:atomdata,axis=0,
                       xvarformat='1.3g'):
    if axis == 0:
        fits = ad.cloudfit_x
        label = "x"
    elif axis == 1:
        fits = ad.cloudfit_y
        label = "y"
    else:
        raise ValueError("Axis must be 0 (x) or 1 (y)")

    fits_yfitdata = [fit.y_fitdata for fit in fits]
    fits_ydata = [fit.ydata for fit in fits]
    xdata = fits[0].xdata
    sum_od_residuals = np.asarray(fits_ydata) - np.asarray(fits_yfitdata)
    print(sum_od_residuals.shape)
    fig, ax = plt.subplots(ad.params.N_repeats[0],ad.params.N_shots)

    bools = ~np.isinf(sum_od_residuals) & ~np.isnan(sum_od_residuals)
    ylimmin = np.min(sum_od_residuals[bools])
    ylimmax = np.max(sum_od_residuals[bools])

    Nr = ad.params.N_repeats[0]
    Ns = ad.params.N_shots

    xvar = ad.xvars[0]

    if ad.params.N_repeats == 1:
        for i in range(Ns):
            ax[i].plot(xdata,sum_od_residuals[i])
            ax[i].set_xlabel(f"{xvar[i]:{xvarformat}}")
            ax[i].set_ylim(ylimmin,ylimmax)
            ax[i].set_xticks([])
            ax[i].set_yticks([])
    else:
        for j in range(Nr):
            for i in range(Ns):
                idx = j + i*Nr
                ax[j,i].plot(xdata,sum_od_residuals[idx])
                ax[j,i].set_xlabel(f"{xvar[idx]:{xvarformat}}")
                ax[j,i].set_ylim(ylimmin,ylimmax)
                ax[j,i].set_xticks([])
                ax[j,i].set_yticks([])
    fig.suptitle(f"Run ID: {ad.run_info.run_id}\nsum_od_{label} fit residuals")
    fig.supxlabel(ad.xvarnames[0])
    fig.set_figwidth(18)
    fig.tight_layout()

    plt.show()

    return fig, ax