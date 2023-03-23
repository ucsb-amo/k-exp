from kexp.analysis.image_processing.compute_ODs import *
from kexp.analysis.image_processing.compute_gaussian_cloud_params import fit_gaussian_sum_OD

class atomdata():
    '''
    Use to store and do basic analysis on data for every experiment.

    Any attribute which does not start with '_' will be saved to the dataset in _save_data().

    This class also handles saving parameters from expt.params to the dataset.
    '''
    def __init__(self, expt, crop_type='mot'):
        self._expt = expt

        self._images = expt.images
        self._img_timestamps = expt.image_timestamps

        self.img_atoms_tstamp = []
        self.img_light_tstamp = []
        self.img_dark_tstamp = []
        self.img_atoms = []
        self.img_light = []
        self.img_dark = []
        self.od_raw = []
        self.od = []
        self.sum_od_x = []
        self.sum_od_y = []
        self.cloudfit_x = []
        self.cloudfit_y = []

        self.sd_x = [fit.sigma for fit in self.cloudfit_x]
        self.sd_y = [fit.sigma for fit in self.cloudfit_y]
        self.center_x = [fit.x_center for fit in self.cloudfit_x]
        self.center_y = [fit.y_center for fit in self.cloudfit_y]
        self.amp_x = [fit.amplitude for fit in self.cloudfit_x]
        self.amp_y = [fit.amplitude for fit in self.cloudfit_y]

        self._split_images()

        self._analyze_absorption_images(crop_type)

    def _analyze_absorption_images(self,crop_type='mot'):
        '''
        Saves the images, image timestamps (in ns), computes ODs, and saves them to
        the dataset of the current experiment (expt)

        Parameters
        ----------
        expt: EnvExperiment
            The experiment object, called to save datasets.

        crop_type: str
            Picks what crop settings to use for the ODs. Default: 'mot'. Allowed
            options: 'mot'.
        '''

        self.od_raw, self.od, self.sum_od_x, self.sum_od_y = compute_ODs(self.img_atoms,self.img_light,self.img_dark,crop_type)
        self.cloudfit_x = fit_gaussian_sum_OD(self.sum_od_x)
        self.cloudfit_y = fit_gaussian_sum_OD(self.sum_od_y)
    
    def save_data(self):
        '''
        Any attribute which does not start with '_' will be saved to the dataset in _save_data().

        This function also handles saving parameters from expt.params to the dataset.
        '''
        print("Saving data...")
        try:
            param_keys = list(vars(self))
            important_param_keys = [p for p in param_keys if not p.startswith("_")]
            for key in important_param_keys:
                value = vars(self)[key]
                self._expt.set_dataset(key, value)
        except Exception as e: 
            print(e)
        print("Done saving data!")

        print("Saving parameters...")
        self._expt.params.params_to_dataset(self)
        print("Done saving parameters!")

    def _split_images(self):
        
        atom_img_idx = 0
        light_img_idx = 1
        dark_img_idx = 2
        
        self.img_atoms = self._images[atom_img_idx::3]
        self.img_light = self._images[light_img_idx::3]
        self.img_dark = self._images[dark_img_idx::3]

        self.img_atoms_tstamp = self._img_timestamps[atom_img_idx::3]
        self.img_light_tstamp = self._img_timestamps[light_img_idx::3]
        self.img_dark_tstamp = self._img_timestamps[dark_img_idx::3]