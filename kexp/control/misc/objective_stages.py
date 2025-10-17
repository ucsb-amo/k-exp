import sys
import os
import time

import numpy as np

CONTROLLER_HOSTNAME = "192.168.1.80"
N_OBJECTIVES = 2
OBJECTIVE_NAMES = ["n","s"]
AXES_LISTS = [[1,2,3],[4,5,6]]
AXES_NAME_LIST = [["x","y",'z'],["x","y",'z']]

class motor_axis():
    def __init__(self,controller_addr,motor_idx,stage_obj):
        from pylablib.devices import Newport
        stage_obj:Newport.Picomotor8742
        self.addr = controller_addr
        self.motor_idx = motor_idx
        self.stage = stage_obj
        self.position = 0

    def move(self,N_steps):
        self.wait_until_done_moving()
        self.stage.move_by(self.motor_idx,N_steps,addr=self.addr)
        self.wait_until_done_moving()
        self.position += N_steps
    
    def wait_until_done_moving(self):
        self.stage.wait_move(addr=self.addr)

    def reset_position(self):
        self.position = 0

class controller():

    def __init__(self):
        from pylablib.devices import Newport
        self.stage = Newport.Picomotor8742(CONTROLLER_HOSTNAME,multiaddr=True,scan=False)
        self.setup_axes()

    def setup_axes(self):
        
        # note the axes here indicate the axes about which the motor drives rotation of the stage when driven with positive steps
        n_obj = dict()
        n_obj['+y'] = motor_axis(1,1,stage_obj=self.stage)
        n_obj['+z'] = motor_axis(1,2,stage_obj=self.stage)
        n_obj['-z'] = motor_axis(1,3,stage_obj=self.stage)
        n_obj['-x'] = motor_axis(2,1,stage_obj=self.stage)
        n_obj['+x'] = motor_axis(2,2,stage_obj=self.stage)

        s_obj = dict()
        s_obj['+x'] = motor_axis(2,4,stage_obj=self.stage)
        s_obj['-x'] = motor_axis(3,1,stage_obj=self.stage)
        s_obj['-y'] = motor_axis(3,2,stage_obj=self.stage)
        s_obj['+z'] = motor_axis(3,3,stage_obj=self.stage)
        s_obj['-z'] = motor_axis(3,4,stage_obj=self.stage)
        
        self.axes = dict()
        self.axes['n'] = n_obj
        self.axes['s'] = s_obj

    def translate(self,N_steps,obj:str,axis:str):
        if obj == 'n':
            objective = self.axes['n']
            ysign = 1
        elif obj == 's':
            objective = self.axes['s']
            ysign = -1

        # if '+' in axis:
        #     sign = 1
        # elif '-' in axis:
        #     sign = -1

        axes_to_move = []
        # in order to translate in x, drive the motors which control rotation about z
        if 'x' in axis:
            axes_to_move.append(objective['+z'])
            axes_to_move.append(objective['-z'])

        elif 'y' in axis:
            if obj == 'n':
                axes_to_move.append(objective['+y'])
            elif obj == 's':
                axes_to_move.append(objective['-y'])
            N_steps = ysign * N_steps

        # in order to translate in z, drive the motors which control rotation about x
        elif 'z' in axis:
            axes_to_move.append(objective['+x'])
            axes_to_move.append(objective['-x'])

        for this_axis in axes_to_move:
            this_axis: motor_axis
            this_axis.move(N_steps)
            print(this_axis.addr,this_axis.motor_idx,N_steps,this_axis.position)

    def move(self,N_steps,obj:str,axis:str):
        if obj == 'n':
            objective = self.axes['n']
            ysign = 1
        elif obj == 's':
            objective = self.axes['s']
            ysign = -1

        # if '+' in axis:
        #     sign = 1
        # elif '-' in axis:
        #     sign = -1

        axes_to_move = []
        if 'x' in axis:
            if '+' in axis:
                axes_to_move.append(objective['+x'])
            elif '-' in axis:
                axes_to_move.append(objective['-x'])
        elif 'y' in axis:
            if obj == 'n':
                axes_to_move.append(objective['+y'])
            elif obj == 's':
                axes_to_move.append(objective['-y'])
            N_steps = ysign * N_steps
        elif 'z' in axis:
            if '+' in axis:
                axes_to_move.append(objective['+z'])
            elif '-' in axis:
                axes_to_move.append(objective['-z'])

        for this_axis in axes_to_move:
            this_axis: motor_axis
            this_axis.move(N_steps)
            
    
    def translate_together_x(self,N_steps):
        self.translate(N_steps=N_steps,obj='n',axis='x')
        self.translate(N_steps=N_steps,obj='s',axis='x')

    def translate_together_y(self,N_steps):
        self.translate(N_steps=-N_steps,obj='n',axis='y')
        self.translate(N_steps=-N_steps,obj='s',axis='y')

    def translate_together_z(self,N_steps):
        self.translate(N_steps=-N_steps,obj='n',axis='z')
        self.translate(N_steps=-N_steps,obj='s',axis='z')