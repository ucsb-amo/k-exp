import matplotlib.pyplot as plt
import numpy as np
from kexp.analysis import atomdata

def plot_image_grid(ad:atomdata, var1_idx=0, var2_idx=1,
                    xvarformat="1.2f",
                     xvar1format="",
                     xvar2format="",
                     xvar1mult=1.,
                     xvar2mult=1.,
                     od_max=0.):
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

def plot_mixOD(ad,xvarformat="1.2f",lines=False):
    # Extract necessary information
    od = ad.od
    xvarnames = ad.xvarnames
    xvars = ad.xvars

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
        ax.imshow(img, extent=[x_pos, x_pos + px, 0, py], aspect='auto')
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