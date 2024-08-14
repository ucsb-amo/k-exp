from kexp.analysis.image_processing.compute_ODs import *
from kexp.analysis.image_processing.compute_gaussian_cloud_params import fit_gaussian_sum_dist
from kexp.util.data.data_vault import DataSaver
import numpy as np
from kamo.atom_properties.k39 import Potassium39

from kexp.util.data.run_info import RunInfo
from kexp.config.expt_params import ExptParams
from kexp.config.camera_params import CameraParams

class analysis_tags():
    def __init__(self,crop_type,absorption_analysis,unshuffle_xvars):
        self.crop_type = crop_type
        self.absorption_analysis = absorption_analysis
        self.unshuffle_xvars = unshuffle_xvars
        self.transposed = False
        self.averaged = False

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
    def __init__(self, xvarnames, images, image_timestamps,
                  params: ExptParams, camera_params:CameraParams,
                  run_info: RunInfo, sort_idx, sort_N, expt_text,
                    unshuffle_xvars = True, crop_type='',
                    transpose_idx=[], avg_repeats=False):

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
            self._analysis_tags.transposed = True
            self.transpose_data(transpose_idx=False,reanalyze=False)

        self.compute_raw_ods()

        if avg_repeats:
            self.avg_repeats(reanalyze=False)

        self.analyze_ods()

    def _sort_images(self):
        if self._analysis_tags.absorption_analysis:
            self._sort_images_absorption()
        else:
            self._sort_images_fluor()

    def compute_atom_number(self):
        self.atom_cross_section = self.atom.get_cross_section()
        self.atom_number_density = self.od / self.atom_cross_section * (self.camera_params.pixel_size_m / self.camera_params.magnification)**2
        self.atom_number = np.sum(np.sum(self.atom_number_density,-2),-1)

    def recrop(self,crop_type=''):
        # if crop_type != self._analysis_tags.crop_type:
        self.analyze_ods(crop_type=crop_type,unshuffle_xvars=False)
        self._analysis_tags.crop_type = crop_type
        # else:
        #     raise ValueError(f'The specified crop_type ({crop_type}) already applied ({self._analysis_tags.crop_type}).')

    def avg_repeats(self,xvars_to_avg=[],reanalyze=True):
        """
        Averages the images along the axes specified in xvars_to_avg. Uses
        absorption imaging analysis.

        Args:
            xvars_to_avg (list, optional): A list of xvar indices to average.
            reanalyze (bool, optional): _description_. Defaults to True.
        """        
        if not self._analysis_tags.unshuffle_xvars:
            raise ValueError("Can only average repeats on runs loaded with unshuffle_xvars = True. Set unshuffle_xvars = True and reload data.")
        
        if not self._analysis_tags.averaged:
            if not xvars_to_avg:
                xvars_to_avg = list(range(len(self.xvars)))
            if not isinstance(xvars_to_avg,list):
                xvars_to_avg = [xvars_to_avg]

            from copy import deepcopy
            # self._xvars_stored = deepcopy(self.xvars)
            def store_values(struct,keylist):
                for key in keylist:
                    array = vars(struct)[key]
                    # save the old information
                    newkey = "_" + key + "_stored"
                    vars(struct)[newkey] = deepcopy(array)

            self._store_keys = ['xvars','xvardims','od_raw']
            store_values(self,self._store_keys)

            self._store_param_keys = ['N_repeats',*self.xvarnames]
            store_values(self.params,self._store_param_keys)

            avg_keys = ['od_raw']
            for xvar_idx in xvars_to_avg:
                for key in avg_keys:
                    array = vars(self)[key]
                    array = self._avg_repeated_ndarray( array, xvar_idx )
                    vars(self)[key] = array
                # write in the unaveraged xvars
                self.xvars[xvar_idx] = np.unique(self.xvars[xvar_idx])
                vars(self.params)[self.xvarnames[xvar_idx]] = self.xvars[xvar_idx]
                self.xvardims[xvar_idx] = self.xvars[xvar_idx].shape[0]

            self.params.N_repeats = np.ones(len(self.xvars),dtype=int)
        
            if reanalyze:
                # don't unshuffle xvars again -- that will be confusing
                self.analyze_ods(unshuffle_xvars=False)

            self._analysis_tags.averaged = True
        else:
            print('Atomdata is already repeat averaged. To revert to original atomdata, use Atomdata.revert_repeats().')
                
    def _avg_repeated_ndarray(self,arr:np.ndarray,xvar_idx,N_repeats_for_this_xvar=-1):
        i = xvar_idx
        if N_repeats_for_this_xvar == - 1:
            # N = self.params.N_repeats[i]
            _, counts = np.unique(self.xvars[xvar_idx], return_counts=True)
            ucounts = np.unique(counts)
            if ucounts.size == 1:
                N = ucounts[0]
            else:
                raise ValueError('Number of repeats per value of an xvar must be the same for all values.')
        else:
            N = N_repeats_for_this_xvar
        arr = np.mean( arr.reshape(*arr.shape[0:i],-1,N,*arr.shape[(i+1):]), axis=i+1, dtype=np.float64)
        return arr
    
    def revert_repeats(self):
        if self._analysis_tags.averaged:

            def retrieve_values(struct,keylist):
                for key in keylist:
                    newkey = "_" + key + "_stored"
                    vars(struct)[key] = vars(struct)[newkey]
            retrieve_values(self,self._store_keys)
            retrieve_values(self.params,self._store_param_keys)

            self.analyze_ods(unshuffle_xvars=False)
            self._analysis_tags.averaged = False
        else:
            print("Atomdata is not repeat averaged. To average, use Atomdata.avg_repeats().")

    def transpose_data(self,new_xvar_idx=[], reanalyze=True):
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
        def reorder_listlike(struct,keys):
            for key in keys:
                attr = vars(struct)[key]
                new_attr = [attr[i] for i in new_xvar_idx]
                if isinstance(attr,np.ndarray):
                    new_attr = np.array(new_attr)
                vars(struct)[key] = new_attr

        listlike_keys = ['xvars','sort_idx','xvarnames','sort_N']
        reorder_listlike(self,listlike_keys)

        param_keys = ['N_repeats']
        reorder_listlike(self.params,param_keys)

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

        if reanalyze:
            self.analyze(unshuffle_xvars=False)

        self._analysis_tags.transposed = not self._analysis_tags.transposed

    ### Analysis

    def compute_raw_ods(self):
        if self._analysis_tags.absorption_analysis:
            self.od_raw = compute_OD(self.img_atoms,self.img_light,self.img_dark)
        else:
            self.od_raw = self.img_atoms.astype(np.int16) - self.img_light.astype(np.int16)

    def analyze_ods(self,crop_type='',unshuffle_xvars=-1,absorption_analysis=-1):

        if not crop_type:
            crop_type = self._analysis_tags.crop_type
        if unshuffle_xvars == -1:
            unshuffle_xvars = self._analysis_tags.unshuffle_xvars
        if absorption_analysis == -1:
            absorption_analysis = self._analysis_tags.absorption_analysis

        if absorption_analysis:
            self._analyze_absorption_images(crop_type)
            self.compute_atom_number()
        else:
            self._analyze_fluorescence_images(crop_type)
        self._remap_fit_results()
    
        if unshuffle_xvars:
            self.unshuffle_ad()
            self.xvars = self._unpack_xvars() # re-unpack xvars to get unshuffled xvars

    def analyze(self,crop_type='',unshuffle_xvars=-1,absorption_analysis=-1):
        if not crop_type:
            crop_type = self._analysis_tags.crop_type
        if unshuffle_xvars == -1:
            unshuffle_xvars = self._analysis_tags.unshuffle_xvars
        if absorption_analysis == -1:
            absorption_analysis = self._analysis_tags.absorption_analysis

        self.compute_raw_ods()
        self.analyze_ods(crop_type,unshuffle_xvars,absorption_analysis)

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
        
        self.od, self.sum_od_x, self.sum_od_y = process_ODs(self.od_raw, crop_type, self.Nvars)
        self.cloudfit_x = fit_gaussian_sum_dist(self.sum_od_x,self.camera_params)
        self.cloudfit_y = fit_gaussian_sum_dist(self.sum_od_y,self.camera_params)

    def _analyze_fluorescence_images(self,crop_type=''):
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
        self.od = roi.crop_OD(self.od_raw,crop_type,self.Nvars)
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
        #print(self._img_atoms[34][511])

        # construct empty matrix of size xvardim[0] x xvardim[1] x pixels_y x pixels_x
        img_dims = np.shape(self.images[0])
        #print(img_dims)
        sorted_img_dims = tuple(self.xvardims) + tuple(img_dims)
        #print('hef')
        #print(self.xvardims)
        #print(sorted_img_dims)
        dtype = self.images.dtype
        self.img_atoms = np.zeros(sorted_img_dims,dtype=dtype)
        self.img_light = np.zeros(sorted_img_dims,dtype=dtype)
        self.img_dark = np.zeros(sorted_img_dims,dtype=dtype)
        self.img_tstamps = np.empty(tuple(self.xvardims),dtype=list)

        #how to generalize to N-D
        #loop thru N-D array using N-D looper
        #---idea -flatten array 
        #loop thru flattened fing, with each boundary decided by how far in N it has gotten\
       
        # print(self.xvardims[0])
        # if self.Nvars == 1:
        #     self.img_atoms = self._img_atoms
        #     self.img_light = self._img_light
        #     self.img_dark = self._img_dark
        #     for i in range(self.xvardims[0]):
        #         self.img_tstamps[i] = list([self._img_atoms_tstamp[i],
        #                             self._img_light_tstamp[i],
        #                             self._img_dark_tstamp[i]])
        #     if len(self.xvars[0]) == 1:
        #         self.img_atoms = np.array([self.img_atoms])
        #         self.img_light = np.array([self.img_light])
        #         self.img_dark = np.array([self.img_dark])
        
        # if self.Nvars == 2:
        #     n1 = self.xvardims[0]
        #     n2 = self.xvardims[1]
        #     for i1 in range(n1):
        #         for i2 in range(n2):
        #             idx = i1*n2 + i2
        #             self.img_atoms[i1][i2] = self._img_atoms[idx]
        #             self.img_light[i1][i2] = self._img_light[idx]
        #             self.img_dark[i1][i2] = self._img_dark[idx]
        #             self.img_tstamps[i1][i2] = [self._img_atoms_tstamp[idx],
        #                                              self._img_light_tstamp[idx],
        #                                              self._img_dark_tstamp[idx]]
                    
        # if self.Nvars == 3:
        #     n1 = self.xvardims[0]
        #     n2 = self.xvardims[1]
        #     n3 = self.xvardims[2]
        #     for i1 in range(n1):
        #         for i2 in range(n2):
        #                 for i3 in range(n3):
        #                     idx = (i1*n2 + i2)*n3 + i3 #standard 3d indexing
        #                     self.img_atoms[i1][i2][i3] = self._img_atoms[idx]
        #                     self.img_light[i1][i2][i3] = self._img_light[idx]
        #                     self.img_dark[i1][i2][i3] = self._img_dark[idx]
        #                     self.img_tstamps[i1][i2][i3] = [self._img_atoms_tstamp[idx],
        #                                                     self._img_light_tstamp[idx],
        #                                                     self._img_dark_tstamp[idx]]

        #flat_img_atoms = self._img_atoms_tstamp.flatten()
        # flat_img_light = self._img_light_tstamp.flatten()
        # flat_img_dark = self._img_dark_tstamp.flatten()
        # index = np.zeros(sorted_img_dims,dtype=dtype)
        # print(index)
        # for i in range(len(flat_img_atoms)):
        #     #find index from img_dims
        #     #need mapping from 1D index to ND index
        #     #first D is a mod of the XVar length, 
        #     #Then mod of the YVar length into the XVar
        #     #Then Z into Y
        #     #T into Z ...

        ###rd 3
        ##loop thro dimensions
        ##need to create flattened 


        ######This code should do what the above code does?

        ###Essentially puts each image object into the expected place in a matrix which first dimensions are the dependant variables
        flat_img_atoms = (self._img_atoms.flatten())
        flat_img_light = (self._img_light.flatten())
        flat_img_dark = (self._img_dark.flatten())
        flat_img_tstamp = np.concatenate((self._img_atoms_tstamp.flatten(),self._img_light_tstamp.flatten(),self._img_dark_tstamp.flatten()))
        self.img_atoms = flat_img_atoms.reshape(sorted_img_dims)
        self.img_light = flat_img_light.reshape(sorted_img_dims)
        self.img_dark = flat_img_dark.reshape(sorted_img_dims)        
        tstamp_dim = tuple(self.xvardims)+(3,)
        self.img_tstamps = flat_img_tstamp.reshape(tstamp_dim)
        
 
        #for i in range(self.Nvars):

            
            



        
                    
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