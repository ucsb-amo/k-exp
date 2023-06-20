from kexp.analysis.image_processing.compute_ODs import *
from kexp.analysis.image_processing.compute_gaussian_cloud_params import fit_gaussian_sum_OD
from kexp.util.data.data_vault import DataSaver
from kexp.util.data.run_info import RunInfo
import numpy as np
from kamo.atom_properties.k39 import Potassium39

class atomdata():
    '''
    Use to store and do basic analysis on data for every experiment.

    xvarnames should be provided as a string indicating the params attribute
    corresponding to the the independent variable(s). They should be provided in
    the order over which they were looped, with the outermost loop first.

    Any attribute which does not start with '_' will be saved to the dataset in
    _save_data().

    This class also handles saving parameters from expt.params to the dataset.
    '''
    def __init__(self, xvarnames, images, image_timestamps, params, camera_params,
                  run_info, sort_idx, sort_N, unshuffle_xvars = True, crop_type='mot'):

        self._ds = DataSaver()
        self.run_info = run_info
        
        self.images = images
        self.img_timestamps = image_timestamps
        self.params = params
        self.camera_params = camera_params

        self.xvarnames = xvarnames
        self.xvars = self._unpack_xvars()

        self.sort_idx = sort_idx
        self.sort_N = sort_N

        self._sort_images()
        self._analyze_absorption_images(crop_type)
        self._remap_fit_results()

        self.atom = Potassium39()
        self.atom_cross_section = self.atom.get_cross_section()
        self.atom_number_density = self.od / self.atom_cross_section * (self.camera_params.pixel_size_m / self.camera_params.magnification)**2
        self.atom_number = np.sum(np.sum(self.atom_number_density,-2),-1)

        if unshuffle_xvars:
            self.unshuffle_ad()

        self.xvars = self._unpack_xvars() # re-unpack xvars to get unshuffled xvars

    ### Analysis

    def _analyze_absorption_images(self,crop_type='mot'):
        '''
        Saves the images, image timestamps (in ns), computes ODs, summed ODs,
        and gaussian fits to the OD profiles.

        Parameters
        ----------
        expt: EnvExperiment
            The experiment object, called to save datasets.

        crop_type: str
            Picks what crop settings to use for the ODs. Default: 'mot'. Allowed
            options: 'mot'.
        '''

        self.od_raw, self.od, self.sum_od_x, self.sum_od_y = \
            compute_ODs(self.img_atoms,
                        self.img_light,
                        self.img_dark,
                        crop_type,
                        self.Nvars)
        self.cloudfit_x = fit_gaussian_sum_OD(self.sum_od_x,self.camera_params)
        self.cloudfit_y = fit_gaussian_sum_OD(self.sum_od_y,self.camera_params)

    def _remap_fit_results(self):
        try:
            fits_x = self.cloudfit_x
            self.fit_sd_x = self._extract_attr(fits_x,'sigma')
            self.fit_center_x = self._extract_attr(fits_x,'x_center')
            self.fit_amp_x = self._extract_attr(fits_x,'amplitude')
            self.fit_offset_x = self._extract_attr(fits_x,'y_offset')

            fits_y = self.cloudfit_y
            self.fit_sd_y = self._extract_attr(fits_y,'sigma')
            self.fit_center_y = self._extract_attr(fits_y,'x_center')
            self.fit_amp_y = self._extract_attr(fits_y,'amplitude')
            self.fit_offset_y = self._extract_attr(fits_y,'y_offset')
        except:
            print("Unable to extract fit parameters. The gaussian fit must have failed")

    def _extract_attr(self,ndarray,attr):
        dims = np.shape(ndarray)
        frame = np.empty(dims,dtype=float)
        if len(dims) == 1:
            for (i0,), fit in np.ndenumerate(ndarray):
                frame[i0] = vars(fit)[attr]
        elif len(dims) == 2:
            for (i0,i1), fit in np.ndenumerate(ndarray):
                frame[i0][i1] = vars(fit)[attr]
        return frame

    ### image handling, sorting by xvars

    def _sort_images(self):

        self._split_images()

        # construct empty matrix of size xvardim[0] x xvardim[1] x pixels_y x pixels_x
        img_dims = np.shape(self.images[0])
        sorted_img_dims = tuple(self.xvardims) + tuple(img_dims)

        self.img_atoms = np.zeros(sorted_img_dims)
        self.img_light = np.zeros(sorted_img_dims)
        self.img_dark = np.zeros(sorted_img_dims)
        self.img_tstamps = np.empty(tuple(self.xvardims),dtype=list)

        if self.Nvars == 1:
            self.img_atoms = self._img_atoms
            self.img_light = self._img_light
            self.img_dark = self._img_dark
            for i in range(self.xvardims[0]):
                self.img_tstamps[i] = list([self._img_atoms_tstamp[i],
                                    self._img_light_tstamp[i],
                                    self._img_dark_tstamp[i]])
        
        if self.Nvars == 2:
            n1 = self.xvardims[0]
            n2 = self.xvardims[1]
            for i1 in range(n1):
                for i2 in range(n2):
                    idx = i1*n2 + i2
                    self.img_atoms[i1][i2] = self._img_atoms[idx]
                    self.img_light[i1][i2] = self._img_light[idx]
                    self.img_dark[i1][i2] = self._img_dark[idx]
                    self.img_tstamps[i1][i2] = [self._img_atoms_tstamp[idx],
                                                     self._img_light_tstamp[idx],
                                                     self._img_dark_tstamp[idx]]
                    
    def _split_images(self):
        
        atom_img_idx = 0
        light_img_idx = 1
        dark_img_idx = 2
        
        self._img_atoms = np.array(self.images[atom_img_idx::3])
        self._img_light = np.array(self.images[light_img_idx::3])
        self._img_dark = np.array(self.images[dark_img_idx::3])

        self._img_atoms_tstamp = self.img_timestamps[atom_img_idx::3]
        self._img_light_tstamp = self.img_timestamps[light_img_idx::3]
        self._img_dark_tstamp = self.img_timestamps[dark_img_idx::3]
    
    def _unpack_xvars(self):
        # fetch the arrays for each xvar from parameters

        if not isinstance(self.xvarnames,list) and not isinstance(self.xvarnames,np.ndarray):
            self.xvarnames = [self.xvarnames]

        xvarnames = self.xvarnames

        self.Nvars = len(xvarnames)
        xvars = []
        for i in range(self.Nvars):
            xvars.append(vars(self.params)[xvarnames[i]])
        
        # figure out dimensions of each xvar
        self.xvardims = np.zeros(self.Nvars,dtype=int)
        for i in range(self.Nvars):
            self.xvardims[i] = np.int32(len(xvars[i]))

        return xvars
    
    ## Unshuffling
    
    def unshuffle_ad(self):
        self._unshuffle(self)
        self._unshuffle(self.params)

    def _unshuffle(self,struct):

        # only unshuffle if list has been shuffled
        if np.any(self.sort_idx):
            sort_N = self.sort_N
            sort_idx = self.sort_idx

            protected_keys = ['xvarnames','sort_idx','images','img_timestamps','sort_N','sort_idx','xvars']
            ks = struct.__dict__.keys()
            sort_ks = [k for k in ks if k not in protected_keys]
            for k in sort_ks:
                var = vars(struct)[k]
                if isinstance(var,list):
                    var = np.array(var)
                if isinstance(var,np.ndarray):
                    sdims = self._dims_to_sort(var)
                    for dim in sdims:
                        N = var.shape[dim]
                        if N in sort_N:
                            i = np.where(sort_N == N)[0][0]
                            shuf_idx = sort_idx[i]
                            shuf_idx = shuf_idx[shuf_idx >= 0].astype(int) # remove padding [-1]s
                            unshuf_idx = np.zeros_like(shuf_idx)
                            unshuf_idx[shuf_idx] = np.arange(N)
                            var = var.take(unshuf_idx,dim)
                            vars(struct)[k] = var
            
    def _dims_to_sort(self,var):
        ndims = var.ndim
        last_dim_to_sort = ndims
        if last_dim_to_sort < 0: last_dim_to_sort = 0
        dims_to_sort = np.arange(0,last_dim_to_sort)
        return dims_to_sort

    ### data saving

    def save_data(self):
        self._ds.save_data(self)    