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

    def shuffle_xvars(self,sort_preshuffle=True):
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

        Nvars = len(self.xvarnames)

        # loop through xvars
        for i in range(Nvars):
            xvar = vars(self.params)[self.xvarnames[i]]
            if sort_preshuffle:
                xvar = np.sort(xvar)
                vars(self.params)[self.xvarnames[i]] = xvar
            N_i = len(xvar)

            # create list of scramble indices for each xvar
            # use same index list for xvars of same length
            if N_i in len_list:
                match_idx = len_list.index(N_i)
                sort_idx.append(sort_idx[match_idx])
            else:
                sort_idx.append( np.arange(N_i) )
                rng.shuffle(sort_idx[i])
            len_list.append(N_i)
        
        # shuffle arrays with the scrambled indices
        for i in range(Nvars):
            xvar = vars(self.params)[self.xvarnames[i]]
            if isinstance(xvar,list):
                xvar = np.array(xvar)
            scrambled_list = xvar.take(sort_idx[i])
            vars(self.params)[self.xvarnames[i]] = scrambled_list

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
                
            
