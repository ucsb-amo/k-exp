##This class takes in experiment paremeter variables and what MLoop thinks they should be, and then generates, and then sends an experiment 
##

import mloop
#Imports for M-LOOP
import mloop.interfaces as mli
import mloop.controllers as mlc
import mloop.visualizations as mlv
#Other imports
import numpy as np
import time
from subprocess import PIPE, run
import matplotlib.pyplot as plt
import matplotlib as mpl
import os




class ExptBuilder():
    def __init__(self):
        self.__code_path__ = os.environ.get('code')
        self.__temp_exp_path__ = os.path.join(self.__code_path__, "k-exp", "kexp", "experiments", "ml_expt.py")

    def run_expt(self):
        expt_path = self.__temp_exp_path__
        run_expt_command = r"%kpy% & artiq_run " + expt_path
        result = run(run_expt_command, stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
        print(result.returncode, result.stdout, result.stderr)
        os.remove(self.__temp_exp_path__)
        return result.returncode
    
    def write_experiment_to_file(self, program):
        with open(self.__temp_exp_path__, 'w') as file:
            file.write(program)

    def execute_test(self, varname, var):
            program = self.test_expt(varname,var)
            self.write_experiment_to_file(program)
            #returncode = self.run_expt()
            return True

    # func. for generating exp, here GM TOF is copied in
    def test_expt(self, varname, var):
        script = textwrap.dedent(f"""
            from artiq.experiment import *
            from artiq.experiment import delay
            from kexp import Base
            import numpy as np                     
            class tof(EnvExperiment, Base):
                def build(self):
                    Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

                    self.p.imaging_state = 2.

                    #self.xvar('t_tof',np.linspace(230.,700.,10)*1.e-6)

                    self.p.t_tof = 450*1.e-6

                    self.xvar('{varname}', [{var}]*3)

                    self.p.t_mot_load = .5
                    

                    self.finish_build(shuffle=True)

                @kernel
                def scan_kernel(self):

                    self.dds.init_cooling()

                    self.switch_d2_2d(1)
                    self.mot(self.p.t_mot_load)
                    self.dds.push.off()
                    # self.cmot_d1(self.p.t_d1cmot)
                    # self.set_shims(v_zshim_current=self.p.v_zshim_current_gm,
                    #                 v_yshim_current=self.p.v_yshim_current_gm,
                    #                   v_xshim_current=self.p.v_xshim_current_gm)

                    # self.gm(self.p.t_gm)
                    # self.gm_ramp(self.p.t_gmramp)

                    self.release()

                    delay(self.p.t_tof)
                    self.flash_repump()
                    self.abs_image()
                
                @kernel
                def run(self):
                    self.init_kernel()
                    self.load_2D_mot(self.p.t_2D_mot_load_delay)
                    self.scan()
                    self.mot_observe()

                def analyze(self):
                    import os
                    expt_filepath = os.path.abspath(__file__)
                    self.end(expt_filepath)

        """)
        return script

    # def execute_test(self, channel, duration):
    #         program = self.pulse_ttl_expt(channel, duration)
    #         self.write_experiment_to_file(program)
    #         returncode = self.run_expt()
    #         return returncode





#This sits on top of MLoop and configure how it interacts with the experiment builder


#jared absorbed two photon

class CustomInterface(mli.Interface):
    
    #Initialization of the interface, including this method is optional
    def __init__(self):
        #You must include the super command to call the parent class, Interface, constructor 
        super(CustomInterface,self).__init__()
        eBuilder = ExptBuilder()
        #jared
        #jared P
        #jared Potassium
        #jared Phase plate
        #jared Photon
        #jared P
        #jared
        
    #You must include the get_next_cost_dict method in your class
    #this method is called whenever M-LOOP wants to run an experiment
    def get_next_cost_dict(self,params_dict):
        
        eBuilder =  ExptBuilder()
        #Get parameters from the provided dictionary
        params = params_dict['params']
        #eBuilder.execute_test('detune_gm',params[0])
        eb.write_experiment_to_file(eb.test_expt('detune_gm',params))
        eb.run_expt()

        time.sleep(20e-3)
        # cost = externalCostFunction.calcCost(params[0])\
        cost = getCost()
        print(cost)
        # print(externalCostFunction.calcCost(-2))



        #I'm not sure how uncertainty will be handled, I think it may be easier to just use the built in noise function of MLoop
        uncer = 0

        #The bad value says if the experiment run failed. Bad should be set to true sometimes, obviously when a full run fails, but also I think some
        #quantification of noise could be useful to prevent things like atom count noise with extremely weak imaging light as talked about in the 26th K notes
        #
        bad = False

        #time delay between each run, tb removed when actual experiments run
        # time.sleep(1)
        
        #The cost, uncertainty and bad boolean must all be returned as a dictionary
        #You can include other variables you want to record as well if you want
        cost_dict = {'cost':cost, 'uncer':uncer, 'bad':bad}
        return cost_dict