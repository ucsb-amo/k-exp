import numpy as np
from artiq.experiment import TFloat, portable, rpc

@portable(flags={"fast-math"})
def tweezer_vpd1_to_vpd2(vpd_pid1) -> TFloat:
    #Calibration coefficients are from
    #k-jam\analysis\measurements\PID1_vs_PID2.ipynb
    slope =  123.42857154500274
    y_intercept =  -2.7238095329863836
    return vpd_pid1 * slope + y_intercept

# distance per MHz:
class tweezer_xmesh():
    def __init__(self):
        """
        Defines the calibration of tweezer frequency to position. The
        positive direction is to the right as viewed on the Andor.

        To recalibrate:
        1. Run tweezer_xpf_calibration.py, making sure that frequency, amplitude
        lists produce a pair of trapped tweezers for both ce (ce) and
        non-ce (nce).
        2. Run analysis file:
        k-jam/analysis/measurements/tweezer_xgrid_calibration.ipynb
        3. Replace x_per_f_ce, x_per_f_nce, x_and_f_ce, and x_and_f_nce (output
        of 2nd to last cell).

        The origin position is set by x_mesh_center. I typically set to the
        midpoint between two extreme tweezers.
        """

        # calibration run 12039

        ## calibration ROI, 'tweezer_array'
        # roix = [180,230]
        # roiy = [250,290]

        self.f_ce_max = 72.3e6
        self.f_ce_min = 70.e6

        self.f_nce_max = 82.e6
        self.f_nce_min = 75.5e6

        self.x_and_f_ce = (1.53e-05,7.21e+07)
        self.x_and_f_nce = (8.33e-06,7.6e+07)
        self.x_per_f_ce = -5.27e-12
        self.x_per_f_nce = 5.36e-12

        # origin wrt ROI above
        self.x_mesh_center = 1.9051162790697675e-05

    def arrcast(self,v,dtype=float):
            if not (isinstance(v,np.ndarray) or isinstance(v,list)):
                v = [v]
            return np.array(v,dtype=dtype)
        
    @portable
    def x_to_f(self, position, cateye):
        """Converts a tweezer position into the corresponding AOD frequency.

        Args:
            position (float or list/ndarray): position (in m)
            cateye_bool (bool or list/ndarray): whether or not the tweezer is
            cat-eyed.
        """
        if isinstance(position,np.ndarray) or isinstance(position,list):
            if len(position) != len(cateye):
                raise ValueError("The length of the cateye list and position list are not the same.")
        else:
            position = [position]
        if not (isinstance(cateye,np.ndarray) or isinstance(cateye,list)):
            cateye = [cateye]

        position = np.asarray(position)
        cateye = np.asarray(cateye)

        f_out = []
        for i in range(len(position)):
            x = position[i]
            c = cateye[i]
            if c:
                f_per_x = 1/self.x_per_f_ce
                x_sample = self.x_and_f_ce[0]
                f_sample = self.x_and_f_ce[1]
            else:
                f_per_x = 1/self.x_per_f_nce
                x_sample = self.x_and_f_nce[0]
                f_sample = self.x_and_f_nce[1]
            x_sample = x_sample - self.x_mesh_center
            f = f_per_x * (x - x_sample) + f_sample
            self.check_valid_range(f,c)
            f_out.append(f)
        return np.array(f_out)
        
    @portable
    def f_to_x(self, frequency):
        """Converts an AOD frequency (in Hz) into the corresponding real-space
        position.

        Args:
            frequency (float): AOD frequency (in Hz)
        """
        cateye = frequency < self.f_ce_max
        if not(isinstance(frequency,np.ndarray) or isinstance(frequency,list)):
            frequency = [frequency]
        if not (isinstance(cateye,np.ndarray) or isinstance(cateye,list)):
            cateye = [cateye]
        frequency = np.asarray(frequency)
        cateye = np.asarray(cateye)
        
        x_out = []
        for i in range(len(frequency)):
            f = frequency[i]
            c = cateye[i]
            self.check_valid_range(f,c)
            if c:
                x_per_f = self.x_per_f_ce
                x_sample = self.x_and_f_ce[0]
                f_sample = self.x_and_f_ce[1]
            else:
                x_per_f = self.x_per_f_nce
                x_sample = self.x_and_f_nce[0]
                f_sample = self.x_and_f_nce[1]
            x_sample = x_sample - self.x_mesh_center
            x = x_per_f * (f - f_sample) + x_sample
            x_out.append(x)
        return np.array(x_out)
    
    @rpc(flags={"async"})
    def check_valid_range(self, frequency, cateye):
        if cateye:
            if frequency > self.f_ce_max or frequency < self.f_ce_min:
                raise ValueError(f"Requested cateye frequency {frequency/1.e6:1.2f} out of safe range.")
        else:
            if frequency > self.f_nce_max or frequency < self.f_nce_min:
                raise ValueError(f"Requested non-cateye frequency {frequency/1.e6:1.2f} out of safe range.")
    
    