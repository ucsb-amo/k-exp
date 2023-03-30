from kexp.analysis.image_processing.compute_ODs import *
from kexp.analysis.image_processing.compute_gaussian_cloud_params import fit_gaussian_sum_OD
from kexp.util.data.data_vault import DataSaver

class atomdata():
    '''
    Use to store and do basic analysis on data for every experiment.

    Any attribute which does not start with '_' will be saved to the dataset in _save_data().

    This class also handles saving parameters from expt.params to the dataset.
    '''
    def __init__(self, expt=[], crop_type='mot'):
        
        self._expt = expt
        self.images = expt.images
        self.img_timestamps = expt.image_timestamps
        self._split_images()

        self._ds = DataSaver()
        self.run_id = self._ds._get_rid()

        self.params = self._expt.params

        self.od_raw = []
        self.od = []
        self.sum_od_x = []
        self.sum_od_y = []
        self.cloudfit_x = []
        self.cloudfit_y = []

        self._analyze_absorption_images(crop_type)

        try:
            self.fit_sd_x = [fit.sigma for fit in self.cloudfit_x]
            self.fit_sd_y = [fit.sigma for fit in self.cloudfit_y]
            self.fit_center_x = [fit.x_center for fit in self.cloudfit_x]
            self.fit_center_y = [fit.x_center for fit in self.cloudfit_y]
            self.fit_amp_x = [fit.amplitude for fit in self.cloudfit_x]
            self.fit_amp_y = [fit.amplitude for fit in self.cloudfit_y]
            self.fit_offset_x = [fit.y_offset for fit in self.cloudfit_x]
            self.fit_offset_y = [fit.y_offset for fit in self.cloudfit_y]
        except:
            print("Unable to extract fit parameters. The gaussian fit must have failed")

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

    def _split_images(self):
        
        atom_img_idx = 0
        light_img_idx = 1
        dark_img_idx = 2
        
        self.img_atoms = self.images[atom_img_idx::3]
        self.img_light = self.images[light_img_idx::3]
        self.img_dark = self.images[dark_img_idx::3]

        self.img_atoms_tstamp = self.img_timestamps[atom_img_idx::3]
        self.img_light_tstamp = self.img_timestamps[light_img_idx::3]
        self.img_dark_tstamp = self.img_timestamps[dark_img_idx::3]

    def save_data(self):
        self._ds.save_data(self)

    