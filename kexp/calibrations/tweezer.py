import numpy as np
from artiq.experiment import TFloat, portable

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
        """        

        # calibration run 

        ## calibration ROI, andor
        # roix = [170,220]
        # roiy = [225,280]

        self.x_per_f_cateye =  -5.7e-12 # m/Hz
        self.x_per_f_non_cateye =  5.2e-12 # m/Hz

        self.x_and_f_cateye = (1.64e-05,7.13e+07)
        self.x_and_f_non_cateye = (2.31e-05,7.6e+07)

        # origin wrt ROI above
        self.x_mesh_center = 2.3069767441860467e-05
        # self.x_mesh_center = 0.
        
    @portable
    def x_to_f(self, position, cateye_bool):
        """Converts a tweezer position into the corresponding AOD frequency.

        Args:
            position (float): position (in m)
            cateye_bool (bool): whether or not the tweezer is cat-eyed.
        """
        if cateye_bool:
            f_per_x = 1/self.x_per_f_cateye
            x_sample = self.x_and_f_cateye[0]
            f_sample = self.x_and_f_cateye[1]
        else:
            f_per_x = 1/self.x_per_f_non_cateye
            x_sample = self.x_and_f_non_cateye[0]
            f_sample = self.x_and_f_non_cateye[1]
        x_sample = x_sample - self.x_mesh_center
        return f_per_x * (position - x_sample) + f_sample
        
    @portable
    def f_to_x(self, frequency, cateye_bool):
        """Converts an AOD frequency (in Hz) into the corresponding real-space
        position.

        Args:
            frequency (float): AOD frequency (in Hz)
            cateye_bool (bool): whether or not the tweezer is cat-eyed.
        """
        if cateye_bool:
            x_per_f = self.x_per_f_cateye
            x_sample = self.x_and_f_cateye[0]
            f_sample = self.x_and_f_cateye[1]
        else:
            x_per_f = self.x_per_f_non_cateye
            x_sample = self.x_and_f_non_cateye[0]
            f_sample = self.x_and_f_non_cateye[1]
        x_sample = x_sample - self.x_mesh_center
        return x_per_f * (frequency - f_sample) + x_sample