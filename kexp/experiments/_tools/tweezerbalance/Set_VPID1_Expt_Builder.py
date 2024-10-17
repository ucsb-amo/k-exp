from subprocess import PIPE, run
import os
import textwrap

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
    
    def set_dac_expt(self,v_pid_dac_value):
        script = textwrap.dedent(f"""
        from artiq.experiment import *
        class unsaturate_tweezers(EnvExperiment):
                                
            def build(self):
                self.core = self.get_device("core")
                self.dac = self.get_device("zotino0")
                self.dac_ch_paintamp = 16
                self.dac_ch_pid1 = 12
                self.dds_pid1 = self.get_device("urukul0_ch3")
                self.dds_pid2 = self.get_device("urukul1_ch0")
                self.dds_pid1_cpld = self.get_device("urukul0_cpld")
                self.dds_pid2_cpld = self.get_device("urukul1_cpld")
                self.ttl_aod_rf_sw = self.get_device("ttl13")
                self.ttl_pid1_int_hold_zero = self.get_device("ttl11")

            @kernel
            def init_tweezer_dds(self):
                self.dds_pid1_cpld.init()
                self.dds_pid2_cpld.init()
                self.core.break_realtime()

                self.dds_pid1.init()
                self.dds_pid2.init()
                self.core.break_realtime()

                self.dds_pid1.set(frequency=80.e6,amplitude=0.45)
                self.dds_pid2.set(frequency=80.e6,amplitude=0.45)
                self.core.break_realtime()

            @kernel
            def tweezer_on(self):
                self.dac.write_dac(self.dac_ch_paintamp,-7.)
                self.dds_pid1.sw.on()
                self.dds_pid2.sw.on()
                self.ttl_aod_rf_sw.on()
                self.ttl_pid1_int_hold_zero.pulse(1.e-6)

            @kernel
            def tweezer_set_power(self,v):
                self.dac.write_dac(self.dac_ch_pid1,v)
                self.dac.load()
            
            @kernel
            def run(self):
                self.core.reset()
                self.init_tweezer_dds()
                self.tweezer_on()
                self.tweezer_set_power({v_pid_dac_value:1.3f})
        """)
        return script