from artiq.experiment import *
from artiq.experiment import delay
from artiq.language.core import now_mu
from kexp import Base
import numpy as np

T_MOVE = 0.1
X_MOVE = 10.e-6

def cubic_move(t,t_move,x_move):
        A = -2*x_move/t_move**3                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               
        B = 3*x_move/t_move**2
        return A*t**3 + B*t**2

class tweezer_move_test(EnvExperiment, Base):
    def prepare(self):
        Base.__init__(self,setup_camera=False)

        self.trap1 = self.tweezer.add_tweezer(0.,0.1,cateye=False)
        self.tweezer.add_tweezer_list(position_list=[0.,-1.e-6,1.e-6],
                                      amplitude_list=[0.1,0.1,0.1],
                                      cateye_list=[True,False,True])
        # self.tweezer.add_tweezer_list()
        # self.tweezer.add_tweezer_list()
        
        # self.slopes = self.trap1.compute_slopes(T_MOVE,cubic_move,
        #                                    T_MOVE,X_MOVE)

        self.finish_prepare(shuffle=False)

    @kernel
    def run(self):
        self.init_kernel(init_dds=False,dds_set=False,dds_off=False)

        self.core.wait_until_mu(now_mu())
        self.tweezer.set_static_tweezers()
        delay(100.e-3)

        # self.trap1.cubic_move(T_MOVE,X_MOVE)
        
        print(self.tweezer.traps[1].position)
        self.core.break_realtime()
        # self.tweezer.traps[1].cubic_move(T_MOVE,X_MOVE)
        self.tweezer.traps[1].sine_move(0.25e-3,10.e-6,1.e3)
        self.core.break_realtime()
        print(self.tweezer.traps[1].position)

        # self.tweezer.move(tweezer_idx=0,
        #                    t_move=T_MOVE,
        #                 slopes=self.tweezer.traps[0].compute_cubic_move(T_MOVE,X_MOVE) )

        # self.tweezer.traps[0].cubic_move(T_MOVE,X_MOVE)
        # self.tweezer.cubic_move(0,T_MOVE,X_MOVE)

        # self.trap1.move(T_MOVE,self.slopes)

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)