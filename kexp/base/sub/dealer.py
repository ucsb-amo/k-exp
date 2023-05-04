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

    def shuffle_xvars(self,sort_preshuffle=1):
        rng = np.random.default_rng()
        sort_idx = []
        len_list = []

        Nvars = len(self.xvarnames)

        for i in range(Nvars):
            xvar = vars(self.params)[self.xvarnames[i]]
            if sort_preshuffle:
                xvar = np.sort(xvar)
                vars(self.params)[self.xvarnames[i]] = xvar
            
            N_i = len(xvar)
            
            if N_i in len_list:
                match_idx = len_list.index(N_i)
                sort_idx.append(sort_idx[match_idx])
            else:
                sort_idx.append( np.arange(N_i) )
                rng.shuffle(sort_idx[i])
            len_list.append(N_i)
        
        for i in range(Nvars):
            xvar = vars(self.params)[self.xvarnames[i]]
            if isinstance(xvar,list):
                xvar = np.array(xvar)
            scrambled_list = xvar.take(sort_idx[i])
            vars(self.params)[self.xvarnames[i]] = scrambled_list

        sort_idx_w_duplicates = list(zip(len_list,sort_idx))
        self.sort_idx = []
        self.sort_N = []
        for elem in sort_idx_w_duplicates:
            if elem[0] not in self.sort_N:
                self.sort_N.append(elem[0])
                self.sort_idx.append(elem[1])
