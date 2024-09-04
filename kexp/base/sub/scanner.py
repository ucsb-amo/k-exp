from kexp.config import ExptParams
from artiq.experiment import *
import numpy as np
from kexp.control.artiq.dummy_core import DummyCore
from artiq.language.core import kernel_from_string, now_mu
from artiq.experiment import delay

RPC_DELAY = 10.e-3

dv = -100.
dvlist = np.array([])

def nothing():
    pass

class Scanner():
    def __init__(self):
        self.params = ExptParams()
        self.xvarnames = []
        self.scan_xvars = []
        self.Nvars = 0
        self.update_nvars()
        self.compute_new_derived = nothing
        self.core = DummyCore()

        self._xvar_writer_floats = []
        self._xvar_writer_int32s = []
        # self._xvar_writer_int64s = []
        self._xvar_writer_arrays = []

        self._param_keylist_floats = []
        self._param_keylist_int32s = []
        # self._param_keylist_int64s = []
        self._param_keylist_arrays = []

    def logspace(self,start,end,n):
        return np.logspace(np.log10(start),np.log10(end),int(n))

    def xvar(self,key,values):
        """Adds an xvar to the experiment.

        Args:
            key (str): The key of the ExptParams attribute to scan.
            values (ndarray): Values to scan over. Can be n-dimensional, scan will step over first index.
        """
        this_xvar = xvar(key,values,position=len(self.scan_xvars))
        self.scan_xvars.append(this_xvar)
        self.xvarnames.append(this_xvar.key)
        # check if params has this xvar key already -- if not, add it
        self.new_param_check(this_xvar)
        self.update_nvars()

    def new_param_check(self,xvar):
        self.param_police(xvar)
        
        params_keylist = list(self.params.__dict__.keys())
        if xvar.key not in params_keylist:
            # set value to a single value (vs list), it will be overwritten per shot in scan
            vars(self.params)[xvar.key] = xvar.values[0]

    def param_police(self,xvar):
        forbidden_chars = [":",",","."," ","-","+","(",")","@","#","$","%","^","&","*","=","!","[","]",";","/","\\","`","~"]
        if any([fc in xvar.key for fc in forbidden_chars]):
            raise ValueError("Key contains forbidden characters.")

    def update_nvars(self):
        """Updates the number of xvars to be scanned.
        """
        self.Nvars = len(self.scan_xvars)

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
    def pre_scan(self):
        """This method is run in scan before the scan loop.
        """        
        pass

    @kernel
    def init_scan_kernel(self):
        """This method is run between each shot just before scan_kernel.
        """
        pass

    @kernel
    def cleanup_scan_kernel(self):
        """This method is run just after each scan_kernel completes.
        """
        pass
        
    @kernel
    def scan(self):
        """
        Runs the scan_kernel function for each value of the xvars specified.
        
        The xvars are scanned as if looping over nested for loops, with the last
        xvar as the innermost loop.

        On each step of the scan, the host ExptParams is updated with the next
        values of the xvars and derived parameters are recomputed. Then, the
        updated host ExptParams values are written into the corresponding kernel
        ExptParams.
        """

        self.pre_scan()

        scanning = True

        while scanning:
            
            self.core.wait_until_mu(now_mu())
            self.update_params_from_xvars()
            delay(RPC_DELAY)

            self.core.wait_until_mu(now_mu())
            self.write_host_params_to_kernel()
            delay(RPC_DELAY)
            self.core.break_realtime()

            self.init_scan_kernel()

            self.scan_kernel()

            self.cleanup_scan_kernel()

            delay(self.params.t_recover)
            self.core.break_realtime()

            self.core.wait_until_mu(now_mu())
            scanning = self.step_scan()

            self.core.break_realtime()

    def update_params_from_xvars(self):
        """Updates the host ExptParams attributes and recomputes derived
        parameters according to the current values of the scanned xvars.

        Does not update the values of the kernel ExptParams -- to do so, use
        write_host_params_to_kernel().
        """

        # update each xvar parameter in the host params
        for xvar in self.scan_xvars:
            vars(self.params)[xvar.key] = xvar.values[xvar.counter]
        # update derived params in the host params
        self.params.compute_derived()
        self.compute_new_derived()

    @kernel
    def write_host_params_to_kernel(self):
        """Loops over all experiment params, and assigns the values of the
        kernel ExptParam attributes to those of the of the host ExptParam
        attributes.

        Must have run generate_assignment_kernels() in build first.
        """
        int32val = 1
        # int64val = np.int64(1)
        floatval = 0.1
        arrayval = np.array([1.])
        for idx in range(len(self._param_keylist_int32s)):
            int32val = self.fetch_int32(idx)
            self._xvar_writer_int32s[idx](self,int32val)

        # for idx in range(len(self._param_keylist_int64s)):
        #     int64val = self.fetch_int64(idx)
        #     self._xvar_writer_int64s[idx](self,int64val)

        for idx in range(len(self._param_keylist_floats)):
            floatval = self.fetch_float(idx)
            self._xvar_writer_floats[idx](self,floatval)

        for idx in range(len(self._param_keylist_arrays)):
            arrayval = self.fetch_array(idx)
            self._xvar_writer_arrays[idx](self,arrayval)
            
    def fetch_float(self,i) -> TFloat:
        """Returns the value of the ith experiment parameter with datatype
        float.

        Args:
            i (int): index of the ith float experiment paramter in the list
            self._param_keylist_floats.

        Returns:
            TFloat: The value of the ith float ExptParam attribute.
        """        
        return vars(self.params)[self._param_keylist_floats[i]]
    
    def fetch_array(self,i) -> TArray(TFloat):
        """Returns the value of the ith experiment parameter with datatype
        ndarray.

        Args:
            i (int): index of the ith ndarray experiment paramter in the list
            self._param_keylist_arrays.

        Returns:
            TFloat: The value of the ith ndarray ExptParam attribute.
        """        
        return vars(self.params)[self._param_keylist_arrays[i]]
    
    # def fetch_int64(self,i) -> TInt64:
    #     """Returns the value of the ith experiment parameter with datatype
    #     int64.

    #     Args:
    #         i (int): index of the ith ndarray experiment paramter in the list
    #         self._param_keylist_int64s.

    #     Returns:
    #         TFloat: The value of the ith int64 ExptParam attribute.
    #     """      
    #     return vars(self.params)[self._param_keylist_int64s[i]]
    
    def fetch_int32(self,i) -> TInt32:
        """Returns the value of the ith experiment parameter with datatype
        int32.

        Args:
            i (int): index of the ith ndarray experiment paramter in the list
            self._param_keylist_int32s.

        Returns:
            TFloat: The value of the ith int32 ExptParam attribute.
        """     
        return vars(self.params)[self._param_keylist_int32s[i]]

    def generate_assignment_kernels(self):
        """Generates a list of kernel functions for each param datatype (int32,
        int64, ndarray, and float ) -- one for each ExptParam attribute. These
        can be called in the kernel to update the kernel experiment params with
        values from the host ExptParams returned by an RPC (the "fetch" functions).
        """

        keylist = list(self.params.__dict__.keys())
        for key in keylist:
            bodycode = f"self.params.{key} = value"
            dtype = str(type(vars(self.params)[key]))

            if 'int' in dtype:
                # if 'numpy.int64' in dtype:
                #     self._param_keylist_int64s.append(key)
                #     self._xvar_writer_int64s.append( kernel_from_string(["self","value"],bodycode) )
                # else:
                self._param_keylist_int32s.append(key)
                self._xvar_writer_int32s.append( kernel_from_string(["self","value"],bodycode) )
            elif 'float' in dtype:
                self._param_keylist_floats.append(key)
                self._xvar_writer_floats.append( kernel_from_string(["self","value"],bodycode) )

            elif 'ndarray' in dtype:
                self._param_keylist_arrays.append(key)
                self._xvar_writer_arrays.append( kernel_from_string(["self","value"],bodycode) )

    def step_scan(self,idx=0) -> TBool:
        '''
        Advances the counters of the xvars to the next step in the scan.

        Advances counters as if the xvars were looped over in nested for loops,
        with the last xvar being the innermost loop.
        '''
        out = True
        xvars = list(reversed(self.scan_xvars))
        last_xvar_idx = self.Nvars - 1
        last_xval_idx = xvars[idx].values.shape[0] - 1
        if idx < self.Nvars:
            if xvars[idx].counter == last_xval_idx:
                if idx != last_xvar_idx:
                    xvars[idx].counter = 0
                    out = self.step_scan(idx+1)
                else:
                    out = False
            else:
                xvars[idx].counter += 1
        return out

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
        try:
            self.params.compute_derived()
            self.compute_new_derived()
        except Exception as e:
            print(e)
            print('Derived parameters were not updated.')

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
        if type(values) == float or type(values) == int:
            values = [values]
        self.values = np.asarray(values,dtype=float)
        self.position = position
        self.counter = 0
        self.sort_idx = []