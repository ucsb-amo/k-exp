from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential
from kexp.config.dds_id import dds_frame
from kexp.config.expt_params import ExptParams

class cooling():
    def __init__(self):
        self.dds = dds_frame()
        self.params = ExptParams()
        # just to get syntax highlighting

    ## AOM group control

    @kernel
    def switch_d2_2d(self,state):
        with parallel:
            if state == 1:
                self.dds.d2_2d_c.on()
                self.dds.d2_2d_r.on()
            elif state == 0:
                self.dds.d2_2d_c.off()
                self.dds.d2_2d_r.off()

    @kernel
    def switch_d2_3d(self,state):
        with parallel:
            if state == 1:
                self.dds.d2_3d_c.on()
                self.dds.d2_3d_r.on()
            elif state == 0:
                self.dds.d2_3d_c.off()
                self.dds.d2_3d_r.off()

    @kernel
    def switch_d1_3d(self,state):
        with parallel:
            if state == 1:
                self.dds.d1_3d_c.on()
                self.dds.d1_3d_r.on()
            elif state == 0:
                self.dds.d1_3d_c.off()
                self.dds.d1_3d_r.off()

    ## Magnet functions

    @kernel
    def switch_mot_magnet(self, state = 0):
        if state == 1:
            V = self.params.V_mot_current
        else:
            V = 0.
        with sequential:
            self.zotino.write_dac(self.dac_ch_3Dmot_current_control,V)
            self.zotino.load()