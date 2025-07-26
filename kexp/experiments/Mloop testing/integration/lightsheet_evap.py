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
import textwrap

from kexp.util.data.load_atomdata import load_atomdata
from kexp.analysis.plotting_1d import *

#Cost Calculator!
def getAtomNumber():

        #Load the data given a run id.
        ad = load_atomdata(0,33815)
        # peakDensity = findPeakOD(ad.od[0])
        # print(peakDensity)
        return np.max(ad.atom_number)

#Cost function is just the negative of the atom number
def getCost():
    atomnumber = getAtomNumber()
    return -1*atomnumber


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
    
    def generate_assignment_lines(self, varnames, values):
        """Generates strings which can be formatted into an experiment string to
        assign the ExptParams parameter with key varnames[i] to values[i]

        Args:
            varnames (list(str)): A list of ExptParam keys.
            values (list(float)): A list of values, one per key in varnames.

        Returns:
            string: a string containing the assignment statements.
        """
        lines = ""
        for i in range(len(varnames)):
             lines += f"""
                    self.p.{varnames[i]} = {float(values[i])}"""
        return lines


  
    # func. for generating exp, here GM TOF is copied in
    def test_expt(self, varname, var):

        N_REPEATS = 1
    
        assignment_lines = self.generate_assignment_lines(varname,var)

        script = textwrap.dedent(f"""
            from artiq.experiment import *
            from artiq.experiment import delay
            from kexp import Base
            import numpy as np
            from kexp.calibrations import high_field_imaging_detuning
            from kexp import Base, img_types, cameras

            from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

            T32 = 1<<32

            class mag_trap(EnvExperiment, Base):

                def prepare(self):
                    Base.__init__(self,setup_camera=True,save_data=True,camera_select='andor',
                                imaging_type=img_types.ABSORPTION)

                    self.p.t_tof = 1300.e-6
                    {assignment_lines}

                    # self.xvar('amp_imaging',np.linspace(.05,.2,10))

                    # self.xvar('t_drop',np.linspace(5.e-6,30.e-6,10))
                    self.p.t_drop = 20.e-6

                    # self.xvar('t_int_hold_off_dealy',np.linspace(5.e-6,200.e-6,5))
                    self.p.t_int_hold_off_dealy = 15.e-6

                    # self.xvar('t_blow_pulse',np.linspace(0.e-6,10.e-6,6))
                    self.p.t_blow_pulse = 16.e-6

                    self.p.t_blow_delay = 4.e-6

                    # self.xvar('hf_imaging_detuning', np.arange(100.,550.,8.)*1.e6)
                    
                    # self.xvar('hf_imaging_detuning', np.linspace(-370.e6,-560.e6,18))
                    # self.p.hf_imaging_detuning = 327.e6 
                    # self.p.hf_imaging_detuning = 395.e6

                    self.p.blow_out_detuning = 330.e6
                
                    # self.camera_params.exposure_time = 25.e-6
                    # self.params.t_imaging_pulse = self.camera_params.exposure_time
                    # self.camera_params.em_gain = 1.
                    # self.xvar('amp_imaging',np.linspace(.08,.3,10))
                    self.p.amp_imaging = .16


                    self.p.N_repeats = 1
                    self.p.t_mot_load = 1.

                    self.finish_prepare(shuffle=True)

                @kernel
                def scan_kernel(self):
                    # self.set_imaging_detuning(frequency_detuned=self.p.hf_imaging_detuning)
                    self.set_high_field_imaging(i_outer=self.p.i_hf_lightsheet_evap2_current)
                    self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

                    # self.switch_d2_2d(1)
                    self.mot(self.p.t_mot_load)
                    self.dds.push.off()
                    self.cmot_d1(self.p.t_d1cmot * s)
                    
                    self.gm(self.p.t_gm * s)
                    self.gm_ramp(self.p.t_gmramp)
            
                    self.magtrap_and_load_lightsheet(do_magtrap_rampup=False)

                    self.dac.yshim_current_control.linear_ramp(self.p.t_yshim_rampdown,self.p.v_yshim_current_magtrap,0.,n=500)

                    # feshbach field on, ramp up to field 1
                    self.outer_coil.on()
                    self.outer_coil.set_voltage()
                    
                    self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                                        i_start=0.,
                                        i_end=self.p.i_hf_lightsheet_evap1_current)
                    
                    # self.set_shims(v_zshim_current=0.,
                    #                 v_yshim_current=0.,
                    #                 v_xshim_current=0.)
                    
                    #lightsheet evap 1
                    self.lightsheet.ramp(t=self.p.t_hf_lightsheet_rampdown,
                                        v_start=self.p.v_pd_lightsheet_rampup_end,
                                        v_end=self.p.v_pd_hf_lightsheet_rampdown_end)
                    
                    self.ttl.pd_scope_trig.pulse(1.e-6)

                    self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                                        i_start=self.p.i_hf_lightsheet_evap1_current,
                                        i_end=self.p.i_hf_lightsheet_evap2_current)
                    
                    # #lightsheet evap 2
                    self.lightsheet.ramp(t=self.p.t_hf_lightsheet_rampdown2,
                                        v_start=self.p.v_pd_hf_lightsheet_rampdown_end,
                                        v_end=self.p.v_pd_hf_lightsheet_rampdown2_end)

                    #delay(self.p.t_lightsheet_hold)
                    
                    self.lightsheet.off()

                    delay(self.p.t_tof)
                    # self.flash_repump()

                    self.abs_image()

                    self.outer_coil.off()

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
    def __init__(self,var_names):
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
        self.var_names = var_names

        
    #You must include the get_next_cost_dict method in your class
    #this method is called whenever M-LOOP wants to run an experiment
    def get_next_cost_dict(self,params_dict):
        
        eBuilder =  ExptBuilder()
        #Get parameters from the provided dictionary
        params = params_dict['params']
        #eBuilder.execute_test('detune_gm',params[0])
        eBuilder.write_experiment_to_file(eBuilder.test_expt(self.var_names,params))
        eBuilder.run_expt()

        time.sleep(200e-3)
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
