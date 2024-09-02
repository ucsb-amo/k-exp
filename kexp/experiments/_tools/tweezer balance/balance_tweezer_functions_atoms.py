from kexp.control import BaslerUSB
from queue import Queue
import scipy as sp
from IPython.display import clear_output
import numpy as np
import matplotlib.pyplot as plt
import spcm
from spcm import units
from Lightshift_Scan_Expt_Builder import ExptBuilder




class TweezerBalancer():

    def __init__(self, box_size = [30,50], f_list = [76.e6, 80.e6], a_list = [0.1,0.1], 
                 percentage_error = [100.,100.], goal_error = 1., p_gain_constant = 2.e-8, img_detuning_list = np.linspace(0,10,10)*1.e6):
        self.BOX_SIZE = box_size
        self.F_LIST = f_list
        self.A_LIST = a_list
        self.N_TWEEZERS = len(self.A_LIST)
        self.PERCENTAGE_ERROR = percentage_error
        self.GOAL_ERROR = goal_error
        self.IMG_DETUNING_LIST = img_detuning_list
        self.P_GAIN_CONSTANT = p_gain_constant

    def run_expt(self):
        eBuilder = ExptBuilder()
        eBuilder.write_experiment_to_file(eBuilder.lightshift_expt(f_list = self.F_LIST, a_list = self.A_LIST, f_img_detuning_list = self.IMG_DETUNING_LIST))
        eBuilder.run_expt()