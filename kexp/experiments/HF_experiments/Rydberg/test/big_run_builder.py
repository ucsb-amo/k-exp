import numpy as np
from subprocess import PIPE, run
import matplotlib.pyplot as plt
import os
import textwrap

class ExptBuilder():
    def __init__(self):
        # self.__code_path__ = os.environ.get('code')
        # self.__temp_exp_path__ = os.path.join(self.__code_path__, "k-exp", "kexp", "experiments", "ml_expt.py")

        self.expt_path = r"C:\Users\jarjarbinks\code\k-exp\kexp\experiments\HF_experiments\Rydberg\test\big_run_test.py"

    def run_expt(self):
        run_expt_command = r"%kpy% & ar " + self.expt_path
        result = run(run_expt_command, stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
        print(result.returncode, result.stdout, result.stderr)
        return result.returncode
    
eBuilder = ExptBuilder()

for f in range(3):
    eBuilder.run_expt()