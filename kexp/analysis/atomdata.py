from kexp.analysis.image_processing.compute_ODs import *
from kexp.analysis.image_processing.compute_gaussian_cloud_params import fit_gaussian_sum_dist
from kexp.util.data.data_vault import DataSaver
import numpy as np
from kamo.atom_properties.k39 import Potassium39

class analysis_tags():
    def __init__(self,crop_type,absorption_analysis,unshuffle_xvars):
        self.crop_type = crop_type
        self.absorption_analysis = absorption_analysis
        self.unshuffle_xvars = unshuffle_xvars

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
                  run_info, sort_idx, sort_N, expt_text,
                    unshuffle_xvars = True, crop_type='',
                    transpose_idx=[]):

        self._ds = DataSaver()
        self.run_info = run_info
        absorption_analysis = self.run_info.absorption_image
        self._analysis_tags = analysis_tags(crop_type,
                                            absorption_analysis,
                                            unshuffle_xvars)
    
        self.images = images
        self.img_timestamps = image_timestamps
        self.params = params
        self.camera_params = camera_params

        self.experiment = expt_text

        self.xvarnames = xvarnames
        self.xvars = self._unpack_xvars()

        self.sort_idx = sort_idx
        self.sort_N = sort_N

        self.atom = Potassium39()

        self._sort_images()
        if transpose_idx:
            self.transpose_data(transpose_idx)
        else:
            self.analyze()

    def transpose_data(self,new_xvar_idx=[]):
        """Swaps xvar order, then reruns the analysis.

        Args:
            new_xvar_idx (list): The list of indices specifying the new order of
            the original xvars. 
            
            For example, in a run with four xvars, specifying [0,2,1,3] means
            that the second and third xvar will be swapped, while the first and
            fourth remain unchanged.

            No list needs to be provided for the case of one or two xvars. In
            the case of one xvar, does nothing.

            new_var_idx can also be set to True in the case of one or two xvars,
            for convenience.
        """        
        Nvars = len(self.xvars)

        if new_xvar_idx == [] or new_xvar_idx == True:
            if Nvars == 1:
                print('There is only one variable -- no dimensions to permute.')
                pass
            elif Nvars == 2:
                new_xvar_idx = [1,0] # by default, flip for just two vars
            else:
                raise ValueError('For more than two variables, you must specify the new xvar order.')
        elif len(new_xvar_idx) != Nvars:
            raise ValueError('You must specify a list of axis indices that match the number of xvars.')

        # for things of a listlike nature which have one element per xvar, and so
        # should have the elements along the first dimension reorderd according
        # to the new_xvar_idx (instead of their axes swapped).
        listlike_keys = ['xvars','sort_idx','xvarnames','sort_N']
        for key in listlike_keys:
            attr = vars(self)[key]
            new_attr = [attr[i] for i in new_xvar_idx]
            if isinstance(attr,np.ndarray):
                new_attr = np.array(new_attr)
            vars(self)[key] = new_attr

        # for things of an ndarraylike nature which have one axis per xvar, and
        # so should have the order of their axes switched.
        ndarraylike_keys = ['img_atoms','img_light','img_dark','img_tstamps']
        for key in ndarraylike_keys:
            attr = vars(self)[key]
            # figure out how many extra indices each has. add them to the new
            # axis index list without changing their order.
            ndim = np.ndim(attr)
            dims_to_add = ndim - Nvars
            axes_idx_to_add = [Nvars+i for i in range(dims_to_add)]
            new_idx = np.concatenate( (new_xvar_idx, axes_idx_to_add) ).astype(int)
            
            attr = np.transpose(attr,new_idx)
            vars(self)[key] = attr

        self.analyze()
    
    def _sort_images(self):
        if self._analysis_tags.absorption_analysis:
            self._sort_images_absorption()
        else:
            self._sort_images_fluor()

    def analyze(self,crop_type='',unshuffle_xvars=None,absorption_analysis=None):
        if not crop_type:
            crop_type = self._analysis_tags.crop_type
        if not unshuffle_xvars:
            unshuffle_xvars = self._analysis_tags.unshuffle_xvars
        if not absorption_analysis:
            absorption_analysis = self._analysis_tags.absorption_analysis

        if absorption_analysis:
            self._analyze_absorption_images(crop_type)
            self.atom_cross_section = self.atom.get_cross_section()
            self.atom_number_density = self.od / self.atom_cross_section * (self.camera_params.pixel_size_m / self.camera_params.magnification)**2
            self.atom_number = np.sum(np.sum(self.atom_number_density,-2),-1)
        else:
            self._analyze_fluorescence_images()
        self._remap_fit_results()
    
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
            options: 'mot', 'bigmot', 'cmot', 'gm'. If another string is
            supplied, defaults to full ROI.
        '''
        self.od_raw, self.od, self.sum_od_x, self.sum_od_y = \
            compute_ODs(self.img_atoms,
                        self.img_light,
                        self.img_dark,
                        crop_type,
                        self.Nvars)
        self.cloudfit_x = fit_gaussian_sum_dist(self.sum_od_x,self.camera_params)
        self.cloudfit_y = fit_gaussian_sum_dist(self.sum_od_y,self.camera_params)

    def _analyze_fluorescence_images(self,crop_type='tweezer'):
        '''
        Saves the images, image timestamps (in ns), computes a subtracted image,
        and performs gaussian fits to the profiles. Note: the subtracted image
        is called "od" in order to provide compatability and ease of use to the
        user. The computed difference is NOT an optical density.

        Parameters
        ----------
        expt: EnvExperiment
            The experiment object, called to save datasets.

            
        crop_type: str
            Picks what crop settings to use for the ODs. Default: 'mot'. Allowed
            options: 'mot'.
        '''
        self.img_atoms = self.img_atoms.astype(np.int16)
        self.img_light = self.img_light.astype(np.int16)

        self.od_raw = self.img_atoms - self.img_light
        # self.od_raw = self.img_atoms
        # self.od = roi.crop_OD(self.od_raw,crop_type)
        self.od = self.od_raw
        self.sum_od_x = np.sum(self.od,self.Nvars)
        self.sum_od_y = np.sum(self.od,self.Nvars+1)
        self.cloudfit_x = fit_gaussian_sum_dist(self.sum_od_x,self.camera_params)
        self.cloudfit_y = fit_gaussian_sum_dist(self.sum_od_y,self.camera_params)

    def _remap_fit_results(self):
        try:
            fits_x = self.cloudfit_x
            self.fit_sd_x = self._extract_attr(fits_x,'sigma')
            self.fit_center_x = self._extract_attr(fits_x,'x_center')
            self.fit_amp_x = self._extract_attr(fits_x,'amplitude')
            self.fit_offset_x = self._extract_attr(fits_x,'y_offset')
            self.fit_area_x = self._extract_attr(fits_x,'area')

            fits_y = self.cloudfit_y
            self.fit_sd_y = self._extract_attr(fits_y,'sigma')
            self.fit_center_y = self._extract_attr(fits_y,'x_center')
            self.fit_amp_y = self._extract_attr(fits_y,'amplitude')
            self.fit_offset_y = self._extract_attr(fits_y,'y_offset')
            self.fit_area_y = self._extract_attr(fits_y,'area')
            
        except Exception as e:
            print(e)
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
        elif len(dims) == 3:
            for (i0,i1,i2), fit in np.ndenumerate(ndarray):
                frame[i0][i1][i2] = vars(fit)[attr]
        return frame

    ### image handling, sorting by xvars

    def _sort_images_absorption(self):

        self._split_images_abs()

        # construct empty matrix of size xvardim[0] x xvardim[1] x pixels_y x pixels_x
        img_dims = np.shape(self.images[0])
        sorted_img_dims = tuple(self.xvardims) + tuple(img_dims)

        dtype = self.images.dtype
        self.img_atoms = np.zeros(sorted_img_dims,dtype=dtype)
        self.img_light = np.zeros(sorted_img_dims,dtype=dtype)
        self.img_dark = np.zeros(sorted_img_dims,dtype=dtype)
        self.img_tstamps = np.empty(tuple(self.xvardims),dtype=list)

        if self.Nvars == 1:
            self.img_atoms = self._img_atoms
            self.img_light = self._img_light
            self.img_dark = self._img_dark
            for i in range(self.xvardims[0]):
                self.img_tstamps[i] = list([self._img_atoms_tstamp[i],
                                    self._img_light_tstamp[i],
                                    self._img_dark_tstamp[i]])
            if len(self.xvars[0]) == 1:
                self.img_atoms = np.array([self.img_atoms])
                self.img_light = np.array([self.img_light])
                self.img_dark = np.array([self.img_dark])
        
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
                    
        if self.Nvars == 3:
            n1 = self.xvardims[0]
            n2 = self.xvardims[1]
            n3 = self.xvardims[2]
            for i1 in range(n1):
                for i2 in range(n2):
                        for i3 in range(n3):
                            idx = (i1*n2 + i2)*n3 + i3
                            self.img_atoms[i1][i2][i3] = self._img_atoms[idx]
                            self.img_light[i1][i2][i3] = self._img_light[idx]
                            self.img_dark[i1][i2][i3] = self._img_dark[idx]
                            self.img_tstamps[i1][i2][i3] = [self._img_atoms_tstamp[idx],
                                                            self._img_light_tstamp[idx],
                                                            self._img_dark_tstamp[idx]]
                    
    def _split_images_abs(self):
        
        atom_img_idx = 0
        light_img_idx = 1
        dark_img_idx = 2
        
        self._img_atoms = np.array(self.images[atom_img_idx::3])
        self._img_light = np.array(self.images[light_img_idx::3])
        self._img_dark = np.array(self.images[dark_img_idx::3])

        self._img_atoms_tstamp = self.img_timestamps[atom_img_idx::3]
        self._img_light_tstamp = self.img_timestamps[light_img_idx::3]
        self._img_dark_tstamp = self.img_timestamps[dark_img_idx::3]

    def _sort_images_fluor(self):

        self._split_images_fluor()

        # construct empty matrix of size xvardim[0] x xvardim[1] x pixels_y x pixels_x
        img_dims = np.shape(self.images[0])
        sorted_img_dims = tuple(self.xvardims) + tuple(img_dims)

        self.img_atoms = np.zeros(sorted_img_dims)
        self.img_light = np.zeros(sorted_img_dims)
        self.img_tstamps = np.empty(tuple(self.xvardims),dtype=list)

        if self.Nvars == 1:
            self.img_atoms = self._img_atoms
            self.img_light = self._img_light
            # if len(self.xvars[0]) == 1:
            #     self.img_atoms = np.array([self.img_atoms])
            #     self.img_light = np.array([self.img_light])
        
        if self.Nvars == 2:
            n1 = self.xvardims[0]
            n2 = self.xvardims[1]
            for i1 in range(n1):
                for i2 in range(n2):
                    idx = i1*n2 + i2
                    self.img_atoms[i1][i2] = self._img_atoms[idx]
                    self.img_light[i1][i2] = self._img_light[idx]

        if self.Nvars == 3:
            n1 = self.xvardims[0]
            n2 = self.xvardims[1]
            n3 = self.xvardims[2]
            for i1 in range(n1):
                for i2 in range(n2):
                    for i3 in range(n3):
                        idx = (i1*n2 + i2)*n3 + i3
                        self.img_atoms[i1][i2][i3] = self._img_atoms[idx]
                        self.img_light[i1][i2][i3] = self._img_light[idx]
                    
    def _split_images_fluor(self):
        
        atom_img_idx = 0
        light_img_idx = 1
        
        self._img_atoms = np.array(self.images[atom_img_idx::2])
        self._img_light = np.array(self.images[light_img_idx::2])

        self._img_atoms_tstamp = self.img_timestamps[atom_img_idx::2]
        self._img_light_tstamp = self.img_timestamps[light_img_idx::2]
    
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
    
    # def switch_axes(self,axis0,axis1):
    #     """Swaps axis0 and axis1 in the images, ods, xvarnames, and xvars. Does
    #     not change the order of params derived from the paramaters in xvarnames.

    #     Args:
    #         axis0 (int): The index of one of the axes to be switched.
    #         axis1 (int): The index of the other axis to be switched.
    #     """
    #     def swap(struct):
    #         struct = np.swapaxes(struct,axis0,axis1)
        
    #     swap(self.img_atoms)
    #     swap(self.img_light)
    #     swap(self.img_dark)
    
    ## Unshuffling
    
    def unshuffle_ad(self):
        self._unshuffle(self)
        self._unshuffle(self.params)

    def _unshuffle(self,struct):

        # only unshuffle if list has been shuffled
        if np.any(self.sort_idx):
            sort_N = self.sort_N
            sort_idx = self.sort_idx

            protected_keys = ['xvarnames','sort_idx','images','img_timestamps','sort_N','sort_idx','xvars','N_repeats','N_shots']
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