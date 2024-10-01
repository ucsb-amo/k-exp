from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential

from kexp.config import ExptParams

import numpy as np

class Dealer():
    def __init__(self):
        self.sort_idx = []
        self.sort_N = []
        self.params = ExptParams()
        self.xvarnames = []

        self.scan_xvars = []
        self.Nvars = 0

    def repeat_xvars(self,N_repeats=[]):
        """
        For each xvar in the scan_xvars list, replaces xvar.values with
        np.repeat(xvar.values,self.params.N_repeats).

        Parameters
        ----------
        N_repeats (int/list/ndarray, optional): The number of repeats to be
        implemented. Can be omitted to use the stored value of
        self.params.N_repeats. Must be either int or list/array of length one,
        or a list/array with one element per element of self.xvarnames.
        """        
        Nvars = self.Nvars

        # allow user to overwrite repeats number when repeat_xvars called
        if N_repeats != []:
            self.params.N_repeats = N_repeats

        error_msg = "self.params.repeats must have either have one element or length equal to the number of xvarnames"
        if isinstance(self.params.N_repeats,int):
            N_repeat = self.params.N_repeats
            self.params.N_repeats = [1 for _ in range(Nvars)]
            self.params.N_repeats[0] = N_repeat
        elif isinstance(self.params.N_repeats,list):
            if len(self.params.N_repeats) == 1:
                N_repeat = self.params.N_repeats[0]
                self.params.N_repeats = [1 for _ in range(Nvars)]
                self.params.N_repeats[0] = N_repeat
            elif len(self.params.N_repeats) != Nvars:
                raise ValueError(error_msg)
        elif isinstance(self.params.N_repeats,np.ndarray):
            if len(self.params.N_repeats) == 1:
                self.params.N_repeats = np.repeat(self.params.N_repeats,Nvars)
            elif len(self.params.N_repeats) != Nvars:
                raise ValueError(error_msg)

        for xvar in self.scan_xvars:
            xvar.values = np.repeat(xvar.values, self.params.N_repeats[xvar.position],axis=0)

    def shuffle_xvars(self,sort_preshuffle=False):
        """
        For each attribute of self.params with key specified in self.xvarnames,
        replaces the corresponding array with a shuffled version of that array.
        The shuffle orders are stored in self.sort_idx to be used in re-sorting
        derived arrays.

        Example: self.xvarnames = ['t_tof']. User specifies self.params.t_tof =
        [4.,6.,8.]. This function might rewrite-in-place self.params.t_tof =
        [8.,4.,6.], and record self.sort_idx = [3,1,2].

        Args:
            sort_preshuffle (bool, optional): If True, each xvar will be sorted
            so that its elements are sequential before being shuffled, such that
            when un-shuffled, the elements are in order. Defaults to True.
        """        
        rng = np.random.default_rng()
        sort_idx = []
        len_list = []

        # loop through xvars
        for xvar in self.scan_xvars:
            if sort_preshuffle:
                xvar.values = np.sort(xvar.values)

            # create list of scramble indices for each xvar
            # use same index list for xvars of same length
            ### Note: with new xvar class, this is not necessary. Update later.
            if xvar.values.shape[0] in len_list:
                match_idx = len_list.index(xvar.values.shape[0])
                sort_idx.append(sort_idx[match_idx])
            else:
                sort_idx.append( np.arange(xvar.values.shape[0]) )
                rng.shuffle(sort_idx[xvar.position])
                xvar.sort_idx = sort_idx[xvar.position]
            len_list.append(xvar.values.shape[0])
        
        # shuffle arrays with the scrambled indices
        for xvar in self.scan_xvars:
            scrambled_list = xvar.values.take(sort_idx[xvar.position],axis=0)
            xvar.values = scrambled_list

        # remove duplicates (shouldn't exist anyway), sort into lists
        sort_idx_w_duplicates = list(zip(len_list,sort_idx))
        self.sort_idx = []
        self.sort_N = []
        for elem in sort_idx_w_duplicates:
            if elem[0] not in self.sort_N:
                self.sort_N.append(elem[0])
                self.sort_idx.append(elem[1])

        # pad with [-1]s to allow saving in hdf5 (avoid staggered array)
        maxN = np.max(self.sort_N)
        for i in range(len(self.sort_idx)):
            N_to_pad = maxN - len(self.sort_idx[i])
            self.sort_idx[i] = np.append(self.sort_idx[i], [-1]*N_to_pad)

    # def shuffle_derived(self):
    #     '''
    #     Loop through all the attributes of params which are not in the list of
    #     protected keys. For each attribute which has a dimension of size equal
    #     to the length of one of the xvars specified in xvarnames, scramble that
    #     axis of the attribute in the same way that the xvar of matching length
    #     was scrambled.
    #     '''
    #     sort_N = self.sort_N
    #     if not isinstance(sort_N,np.ndarray):
    #         sort_N = np.array(sort_N)
    #     sort_idx = self.sort_idx

    #     protected_keys = ['xvarnames','sort_idx','images','img_timestamps','sort_N','sort_idx','xvars','N_repeats','N_shots']
    #     # get a list of the variable keys (that are not protected)
    #     ks = self.params.__dict__.keys()
    #     sort_ks = [k for k in ks if k not in protected_keys if k not in self.xvarnames]
    #     # loop over the keys
    #     for k in sort_ks:
    #         # get the value of the attribute with that key
    #         var = vars(self.params)[k]
    #         # cast arrays as np.ndarrays
    #         if isinstance(var,list):
    #             var = np.array(var)
    #         if isinstance(var,np.ndarray):
    #             # get a list of the dimensions to check for sorting, loop over them
    #             sdims = self._dims_to_sort(var)
    #             for dim in sdims:
    #                 N = var.shape[dim]
    #                 # check to see if this dimension is of a length which matches one of the xvars
    #                 # (sort_N is a list of the lengths of the xvars)
    #                 if N in sort_N:
    #                     # if this dim's length matches that of one of the xvars,
    #                     # grab the index of the match
    #                     i = np.where(sort_N == N)[0][0]
    #                     # get the indices used to shuffle the matching xvar
    #                     shuf_idx = sort_idx[i]
    #                     # remove padding [-1]s (added since the shuffling idx
    #                     # have to be the same length in the hdf5 later)
    #                     shuf_idx = shuf_idx[shuf_idx >= 0].astype(int)
    #                     # scramble the var along the this dimension according to
    #                     # the shuffling idx 
    #                     var = var.take(shuf_idx,dim)
    #                     # save the shuffled variable into params
    #                     vars(self.params)[k] = var

    def _dims_to_sort(self,var):
        '''
        Create a list of which dimensions should be checked for sorting.
        TBH I do not remember why that if statement is necessary.
        '''
        ndims = var.ndim
        last_dim_to_sort = ndims
        if last_dim_to_sort < 0: last_dim_to_sort = 0
        dims_to_sort = np.arange(0,last_dim_to_sort)
        return dims_to_sort