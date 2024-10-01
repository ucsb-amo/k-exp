from kexp.analysis.image_processing.compute_ODs import *
from kexp.analysis.image_processing.compute_gaussian_cloud_params import fit_gaussian_sum_dist
from kexp.util.data.data_vault import DataSaver
import numpy as np
from kamo.atom_properties.k39 import Potassium39

from kexp.util.data.run_info import RunInfo
from kexp.config.expt_params import ExptParams
from kexp.config.camera_params import CameraParams
from kexp.base.sub import Dealer
from kexp.base.sub import xvar

import datetime

class analysis_tags():
    def __init__(self,crop_type,absorption_analysis):
        self.crop_type = crop_type
        self.absorption_analysis = absorption_analysis
        self.xvars_shuffled = False
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
                  run_info: RunInfo, sort_idx, sort_N, 
                  expt_text, params_text, cooling_text, imaging_text,
                    crop_type='', transpose_idx=[], avg_repeats=False):

        self._ds = DataSaver()

        self.run_info = run_info
        absorption_analysis = self.run_info.absorption_image
        self._analysis_tags = analysis_tags(crop_type,
                                            absorption_analysis)
    
        self.images = images
        self.img_timestamps = image_timestamps
        self.params = params
        self.camera_params = camera_params

        self.experiment = expt_text
        self.params_file = params_text
        self.cooling_file = cooling_text
        self.imaging_file = imaging_text

        self.xvarnames = xvarnames
        self.xvars = self._unpack_xvars()

        self.sort_idx = sort_idx
        self.sort_N = sort_N

        self.atom = Potassium39()

        self._dealer = self._init_dealer()

        if self.run_info.run_datetime < datetime.datetime(2024,10,2):
            self._analysis_tags.xvars_shuffled = True
            self.unshuffle()

        self._sort_images()

        if transpose_idx:
            self._analysis_tags.transposed = True
            self.transpose_data(transpose_idx=False,reanalyze=False)

        self.compute_raw_ods()

        if avg_repeats:
            self.avg_repeats(reanalyze=False)

        self.analyze_ods()

    def _init_dealer(self) -> Dealer:
        dealer = Dealer()
        dealer.params = self.params
        dealer.run_info = self.run_info
        dealer.images = self.images
        dealer.img_timestamps = self.img_timestamps
        dealer.sort_idx = self.sort_idx
        dealer.sort_N = self.sort_N
        # reconstruct the xvar objects
        for idx in range(len(self.xvarnames)):
            this_xvar = xvar(self.xvarnames[idx],
                             self.xvars[idx],
                             position=idx)
            this_xvar.sort_idx = self.sort_idx[idx]
            dealer.scan_xvars.append(this_xvar)
        return dealer

    def _sort_images(self):
        imgs_tuple = self._dealer.sort_images()
        if self._analysis_tags.absorption_analysis:
            self.img_atoms = imgs_tuple[0]
            self.img_light = imgs_tuple[1]
            self.img_dark = imgs_tuple[2]
        else:
            self.img_atoms = imgs_tuple[0]
            self.img_dark = imgs_tuple[1]
        self.img_timestamps.reshape(-1,3)

    def compute_atom_number(self):
        self.atom_cross_section = self.atom.get_cross_section()
        dx_pixel = self.camera_params.pixel_size_m / self.camera_params.magnification
        
        self.atom_number_fit_area_x = self.fit_area_x * dx_pixel / self.atom_cross_section
        self.atom_number_fit_area_y = self.fit_area_y * dx_pixel / self.atom_cross_section

        self.atom_number_density = self.od * dx_pixel**2 / self.atom_cross_section
        self.atom_number = np.sum(np.sum(self.atom_number_density,-2),-1)

    def recrop(self,crop_type=''):
        self.analyze_ods(crop_type=crop_type)
        self._analysis_tags.crop_type = crop_type

    def avg_repeats(self,xvars_to_avg=[],reanalyze=True):
        """
        Averages the images along the axes specified in xvars_to_avg. Uses
        absorption imaging analysis.

        Args:
            xvars_to_avg (list, optional): A list of xvar indices to average.
            reanalyze (bool, optional): _description_. Defaults to True.
        """
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
                self.analyze_ods()

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

            self.analyze_ods()
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
            self.analyze()

        self._analysis_tags.transposed = not self._analysis_tags.transposed

    ### Analysis

    def compute_raw_ods(self):
        if self._analysis_tags.absorption_analysis:
            self.od_raw = compute_OD(self.img_atoms,self.img_light,self.img_dark)
        else:
            self.od_raw = self.img_atoms.astype(np.int16) - self.img_light.astype(np.int16)

    def analyze_ods(self,crop_type='',absorption_analysis=-1):

        if not crop_type:
            crop_type = self._analysis_tags.crop_type
        if absorption_analysis == -1:
            absorption_analysis = self._analysis_tags.absorption_analysis

        if absorption_analysis:
            self._analyze_absorption_images(crop_type)
            self._remap_fit_results()
            self.compute_atom_number()
        else:
            self._analyze_fluorescence_images(crop_type)
            self._remap_fit_results()

    def analyze(self,crop_type='',absorption_analysis=-1):
        if not crop_type:
            crop_type = self._analysis_tags.crop_type
        if absorption_analysis == -1:
            absorption_analysis = self._analysis_tags.absorption_analysis

        self.compute_raw_ods()
        self.analyze_ods(crop_type,absorption_analysis)

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
        
        self.od, self.sum_od_x, self.sum_od_y = process_ODs(self.od_raw, crop_type)
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
        linarray = np.reshape(ndarray,np.size(ndarray))
        vals = [vars(y)[attr] for y in linarray]
        out = np.reshape(vals,ndarray.shape+(-1,))
        if out.ndim == 2 and out.shape[-1] == 1:
            out = out.flatten()
        return out

    def _map(self,ndarray,func):
        linarray = np.reshape(ndarray,np.size(ndarray))
        vals = [func(y) for y in linarray]
        return np.reshape(vals,ndarray.shape+(-1,))
    
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
    
    def reshuffle(self):
        if self._analysis_tags.xvars_shuffled == False:
            self.images = self._dealer.unscramble_images(reshuffle=True)
            self._dealer._unshuffle_struct(self, reshuffle=True)
            self._dealer._unshuffle_struct(self.params, reshuffle=True)
            self.xvars = self._unpack_xvars()
            self.analyze()
            self._analysis_tags.xvars_shuffled = True
        else:
            print("Data is already in shuffled order.")

    def unshuffle(self):
        if self._analysis_tags.xvars_shuffled == True:
            self.images = self._dealer.unscramble_images(reshuffle=False)
            self._dealer._unshuffle_struct(self, reshuffle=False)
            self._dealer._unshuffle_struct(self.params, reshuffle=False)
            self.xvars = self._unpack_xvars()
            self.analyze()
            self._analysis_tags.xvars_shuffled = False
        else:
            print("Data is already in unshuffled order.")

    ### data saving

    def save_data(self):
        self._ds.save_data(self)