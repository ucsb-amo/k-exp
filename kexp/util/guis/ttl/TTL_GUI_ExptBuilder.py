import os
import textwrap
from subprocess import PIPE, run

NUM_TTL = 16
START_TTL = 8



class TTLGUIExptBuilder():
    def __init__(self):
        self.__code_path__ = os.environ.get('code')
        self.__temp_exp_path__ = os.path.join(self.__code_path__, "k-exp", "kexp", "experiments", "ttl_gui_expt.py")

    def run_expt(self):
        expt_path = self.__temp_exp_path__
        run_expt_command = r"%kpy% & ar " + expt_path
        result = run(run_expt_command, stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
        print(result.returncode, result.stdout, result.stderr)
        os.remove(self.__temp_exp_path__)
        return result.returncode

    def make_ttl_on_expt(self, channel):
        script = textwrap.dedent(f"""
            from artiq.experiment import *
            class SetTTLOn(EnvExperiment):
                def build(self):
                    # Specify the TTL device you want to control
                    self.core = self.get_device("core")
                    self.ttl = self.get_device("ttl"+str({channel}))
                    
                

                @kernel
                def run(self):
                    self.core.break_realtime()

                    # Program the TTL channel and turn on
                    self.ttl.on()

        
        """)
        return script

    def write_experiment_to_file(self, program):
        with open(self.__temp_exp_path__, 'w') as file:
            file.write(program)

    def execute_set_ttl_on(self, channel):
        program = self.make_ttl_on_expt(channel)
        self.write_experiment_to_file(program)
        returncode = self.run_expt()
        return returncode
    
# func. for turning CH off
    def make_ttl_off_expt(self, channel):
        script = textwrap.dedent(f"""
            from artiq.experiment import *
            class SetTTLOff(EnvExperiment):
                def build(self):
                    # Specify the TTL device you want to control
                    self.core = self.get_device("core")
                    self.ttl = self.get_device("ttl"+str({channel}))
                    
                
                @kernel
                def run(self):
                    self.core.break_realtime()

                    # Program the TTL channel and turn off
                    self.ttl.off()

        """)
        return script

    def execute_set_ttl_off(self, channel):
        program = self.make_ttl_off_expt(channel)
        self.write_experiment_to_file(program)
        returncode = self.run_expt()
        return returncode
    
    def execute_all_ttl_off(self, TTL_IDX_LIST):

        script = textwrap.dedent(f"""
            from artiq.experiment import *
            class SetTTLOff(EnvExperiment):
                def build(self):
                    # Specify the TTL device you want to control
                    self.core = self.get_device("core")
                    self.beans = []
                    for ch in {TTL_IDX_LIST}:
                        self.beans.append(self.get_device("ttl"+str(ch)))
                
                @kernel
                def run(self):
                    self.core.reset()

                    # Program the TTL channel and turn off
                    # Loop through self.ttl elements (which are TTLOuts)
                    for ttl in self.beans:
                        ttl.off()
                        delay(8*ns)
        """)
        self.write_experiment_to_file(script)
        returncode = self.run_expt()
        return returncode
        
         

   
    
    # func. for pulse(duration)
    def pulse_ttl_expt(self, channel, duration):
        script = textwrap.dedent(f"""
            from artiq.experiment import *
            class SetTTLPulse(EnvExperiment):
                def build(self):
                    # Specify the TTL device you want to control
                    self.core = self.get_device("core")
                    self.ttl = self.get_device("ttl"+str({channel}))

                    # Set the desired duration of pulse for each channel
                    self.duration = {duration}
                    
                
                @kernel
                def run(self):
                    self.core.break_realtime()



                    # Program the TTL channel and pulse
                    self.ttl.pulse(self.duration)

        """)
        return script

    def execute_pulse_ttl(self, channel, duration):
            program = self.pulse_ttl_expt(channel, duration)
            self.write_experiment_to_file(program)
            returncode = self.run_expt()
            return returncode

        