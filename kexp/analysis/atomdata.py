from kexp.analysis.image_processing.compute_ODs import compute_OD
from kexp.analysis.image_processing.compute_gaussian_cloud_params import fit_gaussian_sum_dist
from kexp.analysis.roi import ROI
from kexp.util.data.data_vault import DataSaver
import numpy as np
from kamo.atom_properties.k39 import Potassium39

from kexp.util.data.run_info import RunInfo
from kexp.config.expt_params import ExptParams
from kexp.config.camera_id import CameraParams
from kexp.base.sub.dealer import Dealer
from kexp.base.sub.scanner import xvar

import kexp.util.data.server_talk as st
import h5py

import datetime

from kexp.config.camera_id import img_types as img

def unpack_group(file,group_key,obj):
    """Looks in an open h5 file in the group specified by key, and iterates over
    every dataset in that h5 group, and for each dataset assigns an attribute of
    the object obj" with that dataset's key and value.

    Args:
        file (h5py.File, h5py dataset): An open h5py file object or dataset.
        group_key (str): The key of the group in the h5py file.
        obj (object): Any object to be populated with attributes by the fields
        in the provided dataset. 
    """            
    g = file[group_key]
    keys = list(g.keys())
    for k in keys:
        vars(obj)[k] = g[k][()]

class analysis_tags():
    """A simple container to hold analysis tags for analysis logic.
    """    
    def __init__(self,roi_id,imaging_type):
        self.roi_id = roi_id
        self.imaging_type = imaging_type
        self.xvars_shuffled = False
        self.transposed = False
        self.averaged = False

class expt_code():
    """A simple container to organize experiment text.
    """    
    def __init__(self,
                 experiment,
                 params,
                 cooling,
                 imaging):
        self.experiment = experiment
        self.params = params
        self.cooling = cooling
        self.imaging = imaging

class atomdata():
    '''
    Use to store and do basic analysis on data for every experiment.
    '''
    def __init__(self, idx=0, roi_id=None, path = "",
                 lite = False,
                 skip_saved_roi = False,
                 transpose_idx = [], avg_repeats = False):
        '''
        Returns the atomdata stored in the `idx`th newest file at `path`.

        Parameters
        ----------
        idx: int
            If a positive value is specified, it is interpreted as a run_id (as
            stored in run_info.run_id), and that data is found and loaded. If zero
            or a negative number are given, data is loaded relative to the most
            recent dataset (idx=0).
        roi_id: None, int, or string
            Specifies which crop to use. If roi_id=None, defaults to the ROI saved in
            the data if it exists, otherwise prompts the user to select an ROI using
            the GUI. If an int, interpreted as an run ID, which will be checked for
            a saved ROI and that ROI will be used. If a string, interprets as a key
            in the roi.xlsx document in the PotassiumData folder.
        path: str
            The full path to the file to be loaded. If not specified, loads the file
            as dictated by `idx`.
        skip_saved_roi: bool
            If true, ignore saved ROI in the data file.

        Returns
        -------
        ad: atomdata
        '''

        self._lite = lite

        self._load_data(idx,path,lite)

        ### Helper objects
        self._ds = DataSaver()
        self.atom = Potassium39()
        self._dealer = self._init_dealer()
        self._analysis_tags = analysis_tags(roi_id,self.run_info.imaging_type)
        self.roi = ROI(run_id = self.run_info.run_id,
                       roi_id = roi_id,
                       use_saved_roi = not skip_saved_roi,
                       lite = self._lite)

        self._unshuffle_old_data()
        self._initial_analysis(transpose_idx,avg_repeats)

    ###
    def recrop(self,roi_id=None,use_saved=False):
        """Selects a new ROI and re-runs the analysis. Uses the same logic as
        kexp.ROI.load_roi.

        Args:
            roi_id (None, int, or str): Specifies which crop to use. If None,
            defaults to the ROI saved in the data if it exists, otherwise
            prompts the user to select an ROI using the GUI. If an int,
            interpreted as an run ID, which will be checked for a saved ROI and
            that ROI will be used. If a string, interprets as a key in the
            roi.xlsx document in the PotassiumData folder.

            use_saved (bool): If False, ignores saved ROI and forces creation of
            a new one. Default is False.
        """        
        self.roi.load_roi(roi_id,use_saved)
        self.analyze_ods()

    ### ROI management
    def save_roi_excel(self,key=""):
        self.roi.save_roi_excel(key)

    def save_roi_h5(self):
        self.roi.save_roi_h5(lite=self._lite)
            
    ### Analysis

    def _initial_analysis(self,transpose_idx,avg_repeats):
        self._sort_images()
        if transpose_idx:
            self._analysis_tags.transposed = True
            self.transpose_data(transpose_idx=False,reanalyze=False)
        self.compute_raw_ods()
        if avg_repeats:
            self.avg_repeats(reanalyze=False)
        self.analyze_ods()

    def analyze(self):
        self.compute_raw_ods()
        self.analyze_ods()

    def compute_raw_ods(self):
        """Computes the ODs. If not absorption analysis, OD = (pwa - dark)/(pwoa - dark).
        """        
        self.od_raw = compute_OD(self.img_atoms,self.img_light,self.img_dark,
                                 imaging_type=self._analysis_tags.imaging_type)

    def analyze_ods(self):
        """Crops ODs, computes sum_ods, gaussian fits to sum_ods, and populates
        fit results.
        """
        self.od = self.roi.crop(self.od_raw)
        self.sum_od_x = np.sum(self.od,self.od.ndim-2)
        self.sum_od_y = np.sum(self.od,self.od.ndim-1)

        self.axis_x = self.camera_params.pixel_size_m / self.camera_params.magnification * np.arange(self.sum_od_x.shape[-1])
        self.axis_y = self.camera_params.pixel_size_m / self.camera_params.magnification * np.arange(self.sum_od_x.shape[-1])
        
        self.cloudfit_x = fit_gaussian_sum_dist(self.sum_od_x,self.camera_params)
        self.cloudfit_y = fit_gaussian_sum_dist(self.sum_od_y,self.camera_params)
        
        self._remap_fit_results()
        
        if self._analysis_tags.imaging_type == img.ABSORPTION:
            self.compute_atom_number()

    def _sort_images(self):
        imgs_tuple = self._dealer.deal_data_ndarray(self.images)
        self.img_atoms = imgs_tuple[0]
        self.img_light = imgs_tuple[1]
        self.img_dark = imgs_tuple[2]

        img_timestamp_tuple = self._dealer.deal_data_ndarray(self.image_timestamps)
        self.img_timestamp_atoms = img_timestamp_tuple[0]
        self.img_timestamp_light = img_timestamp_tuple[1]
        self.img_timestamp_dark = img_timestamp_tuple[2]
        
        if self.params.N_pwa_per_shot > 1:
            self.xvarnames = np.append(self.xvarnames,'idx_pwa')
            self.xvars.append(np.arange(self.params.N_pwa_per_shot))
        else:
            self.img_atoms = self._dealer.strip_shot_idx_axis(self.img_atoms)[0]
            self.img_light = self._dealer.strip_shot_idx_axis(self.img_light)[0]
            self.img_dark = self._dealer.strip_shot_idx_axis(self.img_dark)[0]

            self.img_timestamp_atoms = self._dealer.strip_shot_idx_axis(self.img_timestamp_atoms)[0]
            self.img_timestamp_light = self._dealer.strip_shot_idx_axis(self.img_timestamp_light)[0]
            self.img_timestamp_dark = self._dealer.strip_shot_idx_axis(self.img_timestamp_dark)[0]

    ### Physics
    def compute_atom_number(self):
        self.atom_cross_section = self.atom.get_cross_section()
        dx_pixel = self.camera_params.pixel_size_m / self.camera_params.magnification
        
        self.atom_number_fit_area_x = self.fit_area_x * dx_pixel / self.atom_cross_section
        self.atom_number_fit_area_y = self.fit_area_y * dx_pixel / self.atom_cross_section

        self.atom_number_density = self.od * dx_pixel**2 / self.atom_cross_section
        self.atom_number = np.sum(np.sum(self.atom_number_density,-2),-1)

    ### Averaging and transpose

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
            self._xvars_stored = deepcopy(self.xvars)
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

        listlike_keys = ['xvars','xvarnames']
        reorder_listlike(self,listlike_keys)

        param_keys = ['N_repeats']
        reorder_listlike(self.params,param_keys)

        # for things of an ndarraylike nature which have one axis per xvar, and
        # so should have the order of their axes switched.
        ndarraylike_keys = ['img_atoms','img_light','img_dark']
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

        self._dealer = self._init_dealer()

        if reanalyze:
            self.analyze()

        self._analysis_tags.transposed = not self._analysis_tags.transposed

    ### Data handling

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
            self._sort_images()
            self.analyze()
            self._analysis_tags.xvars_shuffled = True
        else:
            print("Data is already in shuffled order.")

    def unshuffle(self,reanalyze=True):
        if self._analysis_tags.xvars_shuffled == True:
            self.images = self._dealer.unscramble_images(reshuffle=False)
            self._dealer._unshuffle_struct(self, reshuffle=False)
            self._dealer._unshuffle_struct(self.params, reshuffle=False)
            self.xvars = self._unpack_xvars()
            if reanalyze:
                self._sort_images()
                self.analyze()
            self._analysis_tags.xvars_shuffled = False
        else:
            print("Data is already in unshuffled order.")

    def _unshuffle_old_data(self):
        """Unshuffles data that was taken before we started saving data in
        sorted order (before 2024/10/02).
        """        
        if datetime.datetime(*self.run_info.run_datetime[:3]) < datetime.datetime(2024,10,2):
            self._analysis_tags.xvars_shuffled = True
            self.unshuffle(reanalyze=False)

    ### Setup

    def _init_dealer(self) -> Dealer:
        dealer = Dealer()
        dealer.params = self.params
        dealer.run_info = self.run_info
        dealer.images = self.images
        dealer.image_timestamps = self.image_timestamps
        dealer.sort_idx = self.sort_idx
        dealer.sort_N = self.sort_N
        # reconstruct the xvar objects
        for idx in range(len(self.xvarnames)):
            this_xvar = xvar(self.xvarnames[idx],
                             self.xvars[idx],
                             position=idx)
            if np.any(self.sort_idx):
                sort_idx_idx = np.where(self.sort_N == len(this_xvar.values))[0][0]
                this_xvar.sort_idx = self.sort_idx[sort_idx_idx]
            else:
                this_xvar.sort_idx = []
            dealer.scan_xvars.append(this_xvar)
            dealer.xvardims.append(len(this_xvar.values))
        dealer.N_xvars = len(self.xvardims)
        return dealer

    def _load_data(self, idx=0, path = "", lite=False):

        file, rid = st.get_data_file(idx,path,lite)
    
        print(f"run id {rid}")
        with h5py.File(file,'r') as f:
            self.params = ExptParams()
            self.camera_params = CameraParams()
            self.run_info = RunInfo()
            unpack_group(f,'params',self.params)
            unpack_group(f,'camera_params',self.camera_params)
            unpack_group(f,'run_info',self.run_info)
            self.images = f['data']['images'][()]
            self.image_timestamps = f['data']['image_timestamps'][()]
            self.xvarnames = f.attrs['xvarnames'][()]
            self.xvars = self._unpack_xvars()
            try:
                experiment_text = f.attrs['expt_file']
                params_text = f.attrs['params_file']
                cooling_text = f.attrs['cooling_file']
                imaging_text = f.attrs['imaging_file']
            except:
                experiment_text = ""
                params_text = ""
                cooling_text = ""
                imaging_text = ""
            self.experiment_code = expt_code(experiment_text,
                                             params_text,
                                             cooling_text,
                                             imaging_text)
            try:
                self.sort_idx = f['data']['sort_idx'][()]
                self.sort_N = f['data']['sort_N'][()]
            except:
                self.sort_idx = []
                self.sort_N = []

# class ConcatAtomdata(atomdata):
#     def __init__(self,rids=[],roi_id=None,lite=False):

#         self.params = ExptParams()
#         self.camera_params = CameraParams()
#         self.run_info = RunInfo()

#         file, rid = st.get_data_file(rids[0],lite=lite)
#         with h5py.File(file,'r') as f:
#             params = ExptParams()
#             unpack_group(f,'params',params)
#             self.xvarnames = f.attrs['xvarnames'][()]

#             images = f['data']['images'][()]
#             image_timestamps = f['data']['image_timestamps'][()]

#             self.images = np.zeros( np.shape(rids) + images.shape,
#                                     dtype=images.dtype )
#             self.image_timestamps = np.zeros( np.shape(rids) + image_timestamps.shape,
#                                               dtype=image_timestamps.dtype)

#         self.sort_idx = []
#         self.sort_N = []

#         for rid in rids:
#             file, rid = st.get_data_file(rid,lite=lite)
    
#             print(f"run id {rid}")
#             with h5py.File(file,'r') as f:
#                 params = ExptParams()
#                 camera_params = CameraParams()
#                 run_info = RunInfo()
#                 unpack_group(f,'params',params)
#                 unpack_group(f,'camera_params',camera_params)
#                 unpack_group(f,'run_info',run_info)
#                 self.images = f['data']['images'][()]
#                 self.image_timestamps = f['data']['image_timestamps'][()]
#                 self.xvarnames = f.attrs['xvarnames'][()]
#                 self.xvars = self._unpack_xvars()
#                 try:
#                     experiment_text = f.attrs['expt_file']
#                     params_text = f.attrs['params_file']
#                     cooling_text = f.attrs['cooling_file']
#                     imaging_text = f.attrs['imaging_file']
#                 except:
#                     experiment_text = ""
#                     params_text = ""
#                     cooling_text = ""
#                     imaging_text = ""
#                 self.experiment_code = expt_code(experiment_text,
#                                                 params_text,
#                                                 cooling_text,
#                                                 imaging_text)
                    

