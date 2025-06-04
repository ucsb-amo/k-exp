from pypylon import pylon
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from kexp.control import BaslerUSB
from kexp.analysis.image_processing import compute_ODs, fit_gaussian_sum_dist
import numpy as np
from kexp.config import camera_id
from kamo.atom_properties.k39 import Potassium39

from kexp.base.base import Cameras

from preview_experiment import T_TOF_US, T_MOTLOAD_S, CAMERA

####

CROP_TYPE = ''
ODLIM = 1.4
N_HISTORY = 10
PLOT_CENTROID = False
XAXIS_IMAGING = False


###

camera_handler = Cameras()
camera_handler.choose_camera(camera_select=CAMERA)
cam_p = camera_handler.camera_params
camera = BaslerUSB(BaslerSerialNumber=cam_p.serial_no,
                    ExposureTime=cam_p.exposure_time,
                    TriggerMode='On')

####

atom = Potassium39()
atom_cross_section = atom.get_cross_section()
convert_to_atom_number = 1/atom_cross_section * (cam_p.pixel_size_m / cam_p.magnification)**2

### useful functions

def find_idx(array, value):
    array = np.asarray(array)
    idx = (np.abs(array - value)).argmin()
    return idx, array[idx]

### axes setup

fig = plt.figure()
fig.set_figheight(7)
fig.set_figwidth(10)
grid = (5,6)
ax = [0]*8
ax[0] = plt.subplot2grid(grid,(0,0),colspan=2)
ax[1] = plt.subplot2grid(grid,(0,2),colspan=2)
ax[2] = plt.subplot2grid(grid,(0,4),colspan=2)
ax[3] = plt.subplot2grid(grid,(1,0),colspan=3,rowspan=2)
ax[4] = plt.subplot2grid(grid,(1,3),colspan=3,rowspan=1)
ax[5] = plt.subplot2grid(grid,(2,3),colspan=3,rowspan=1)
ax[6] = plt.subplot2grid(grid,(3,0),colspan=6,rowspan=1)
ax[7] = plt.subplot2grid(grid,(4,0),colspan=6,rowspan=1)
fig.show()
plt.ion()

plt.set_cmap('magma')

# start waiting for triggers
camera.StartGrabbingMax(10000,pylon.GrabStrategy_LatestImages)

### Setup

# empty arrays
images = []
count = 0
sigmas_x = np.zeros(N_HISTORY); sigmas_x.fill(np.NaN)
sigmas_y = np.zeros(N_HISTORY); sigmas_y.fill(np.NaN)
atom_N = np.zeros(N_HISTORY); atom_N.fill(np.NaN)
centers_x = np.zeros(N_HISTORY); centers_x.fill(np.NaN)
centers_y = np.zeros(N_HISTORY); centers_y.fill(np.NaN)
t_axis = np.linspace(-N_HISTORY+1,0,N_HISTORY)
centercolors = cm.gray(np.linspace(0.7,0.0,N_HISTORY))

### Running loop

# during camera grab...
while camera.IsGrabbing():
    try:
        # get an image if available
        grabResult = camera.RetrieveResult(30000, pylon.TimeoutHandling_ThrowException)
    except Exception as e:
        # close camera if it fucks up
        print(e)
        camera.Close()

    # when you get an image
    if grabResult.GrabSucceeded():
        # Access the image data
        img = np.uint8(grabResult.GetArray())
        images.append(img)
        # count up how many images you've gotten
        count += 1
        print(f'gotem {count}/3')
        # when you get 3 images (enough to compute an OD)
        if count == 3:
            # compute the OD
            _, OD, sum_od_x, sum_od_y = compute_ODs(images[0],images[1],images[2],crop_type=CROP_TYPE)
            # fit the summed ODs
            fit_x = fit_gaussian_sum_dist(sum_od_x,cam_p)
            fit_y = fit_gaussian_sum_dist(sum_od_y,cam_p)
            try:
                # add the new widths to the arrays of widths, ditto, centers
                sigmas_x = np.append(sigmas_x,fit_x[0].sigma * 1.e6)
                sigmas_y = np.append(sigmas_y,fit_y[0].sigma * 1.e6)

                xcenter_idx, _ = find_idx(fit_x[0].xdata,fit_x[0].x_center)
                ycenter_idx, _ = find_idx(fit_y[0].xdata,fit_y[0].x_center)
                centers_x = np.append(centers_x,xcenter_idx)
                centers_y = np.append(centers_y,ycenter_idx)

                # then remove oldest values
                sigmas_x = sigmas_x[1:]
                sigmas_y = sigmas_y[1:]
                centers_x = centers_x[1:]
                centers_y = centers_y[1:]
            except:
                print("The gaussian fitting must have failed")

            # do the same with atom number
            atom_N = atom_N[1:]
            atom_N = np.append(atom_N,np.sum(OD) * convert_to_atom_number)

            # clear the axes
            for a in ax:
                a.cla()
            # plot the raw images
            ax[0].imshow(images[0],vmax=np.max(images[0]),vmin=0)
            ax[0].set_title("atoms + light image")
            ax[1].imshow(images[1],vmax=np.max(images[1]),vmin=0)
            ax[1].set_xticklabels("")
            ax[1].set_yticklabels("")
            ax[1].set_title("light only image")
            ax[2].imshow(images[2],vmax=np.max(images[2]),vmin=0)
            ax[2].set_yticklabels("")
            ax[2].set_yticklabels("")
            ax[2].set_title("dark image")
            # plot the OD, hardcoded colorbar max for visual comparison between runs
            ax[3].imshow(OD[0],vmax=ODLIM,vmin=0,origin='lower')
            if PLOT_CENTROID:
                ax[3].scatter(centers_x,centers_y,s=50,c=centercolors)
            ax[3].set_title("OD")
            # plot the widths
            ax[4].plot(t_axis,sigmas_x,'.')
            ax[4].plot(t_axis,sigmas_y,'.')
            ax[4].legend(["sigma_x","sigma_y"],loc='lower left')
            ax[4].yaxis.set_label_position("right")
            ax[4].yaxis.tick_right()
            ax[4].set_ylabel("width (um)")
            ax[4].set_xticklabels("")
            # plot the atom number
            ax[5].plot(t_axis,atom_N,'.')
            ax[5].yaxis.set_label_position("right")
            ax[5].yaxis.tick_right()
            ax[5].set_ylabel("atom number")
            ax[5].set_xlabel("shot (relative to current shot)")
            # plot the sumodx and the fit
            ax[6].plot(fit_x[0].xdata,fit_x[0].ydata)
            ax[6].plot(fit_x[0].xdata,fit_x[0].y_fitdata)
            ax[6].set_xlabel("position (um)")
            ax[6].set_ylabel("sum_od_x")
            ax[6].legend(["data","fit"])
            # plot the sumodx fit residuals
            ax[7].plot(fit_x[0].xdata,fit_x[0].ydata - fit_x[0].y_fitdata)
            ax[7].set_xlabel("position (um)")
            ax[7].set_ylabel("sum_od_x fit residuals")

            plt.suptitle(f"t_tof = {T_TOF_US:1.0f} us, t_mot_load = {T_MOTLOAD_S} s")

            # update the figure
            plt.pause(0.1)
            fig.canvas.draw()
            
            # clear the images & counter to get ready for the next ones
            images = []
            count = 0

    grabResult.Release()