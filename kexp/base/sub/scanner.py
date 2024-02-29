from kexp.config import ExptParams
from artiq.experiment import *
import numpy as np

dv = -100.
dvlist = np.array([])

class Scanner():
    def __init__(self):
        self.params = ExptParams()
        self.xvarnames = []
        self.scan_xvars = []
        self.update_nvars()

    def add_xvar(self,key,values):
        """Adds an xvar to the experiment.

        Args:
            key (str): The key of the ExptParams attribute to scan.
            values (ndarray): Values to scan over. Can be n-dimensional, scan will step over first index.
        """
        this_xvar = xvar(key,values,position=len(self.scan_xvars))
        self.scan_xvars.append(this_xvar)
        # check if params has this xvar key already -- if not, add it
        params_keylist = list(self.params.__dict__.keys())
        if this_xvar.key not in params_keylist:
            self.xvarnames.append(this_xvar.key)
            # set value to a single value (vs list), it will be overwritten per shot in scan
            vars(self.params)[this_xvar.key] = this_xvar.values[0] 
        self.update_nvars()

    def update_nvars(self):
        """Updates the number of xvars to be scanned.
        """
        self.Nvars = len(self.scan_vars)

    @kernel
    def scan_kernel(self):
        """The kernel function to be scanned in the experiment. 
        
        It should correspond to a single "shot" (single set of images to
        generate one OD).

        The scan kernel should accept no arguments. 
        
        Any parameters being scanned should be referenced in the scan kernel as
        an attribute of the experiment parameters attribute of the experiment
        class.
        """
        pass

    @kernel
    def scan(self,scan_kernel):
        """
        Runs the scan_kernel function for each value of the xvars specified.
        
        The xvars are scanned as if looping over nested for loops, with the last xvar
        as the innermost loop.

        Args:
            scan_kernel (kernel function): A single shot of the experiment. 
        """        
        self.scanning = True
        while self.scanning:
            for this_xvar in self.scan_xvars:
                self.write_value_to_param(this_xvar)
            ### ADD COMPUTE DERIVED HERE ###
            scan_kernel()
            self.step_scan()

    @kernel
    def write_value_to_param(self,xvar):
        vars(self.params)[xvar.key] = xvar.values[xvar.counter]

    @kernel
    def step_scan(self,idx=0):
        '''
        Advances the counters of the xvars to the next step in the scan.

        Advances counters as if the xvars were looped over in nested for loops,
        with the last xvar being the innermost loop.
        '''
        xvars = list(reversed(self.scan_xvars))
        last_xvar_idx = self.Nvars - 1
        last_xval_idx = xvars[idx].Nvals - 1
        if idx < self.Nvars:
            if xvars[idx].counter == last_xval_idx:
                if idx != last_xvar_idx:
                    xvars[idx].counter = 0
                    self.step_scan(idx+1)
                else:
                    self.scanning = False
            else:
                xvars[idx].counter += 1

    def cleanup_scanned(self):
        """
        Sets the parameters in ExptParams to the lists that were used to take
        the data. 
        
        These are put in in the order the data was taken -- no unshuffling is
        done. 
        
        This is good for recordkeeping, and ensures backward compatability with
        analysis code.
        """
        for xvar in self.scan_xvars:
            vars(self.params)[xvar.key] = xvar.values
        self.params.compute_derived()

class xvar():
    def __init__(self,key:str,values:np.ndarray,position=0):
        """Defines an variable that will be scanned over in the scan_kernel.

        Args:
            key (str): The key of the ExptParams attribute to be scanned. Does
            not have to exist in ExptParams beforehand.
            values (np.ndarray): The values over which the attribute referenced
            by "key" should be scanned.
        """
        self.key = key
        self.values = np.asarray(values)
        self.position = position
        self.counter = 0
        self.sort_idx = []
        self.Nvals = np.shape(self.values)[0]