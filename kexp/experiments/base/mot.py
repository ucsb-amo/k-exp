from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential

class mot():
    def __init__(self):
        pass

    @kernel
    def load_mot(self,t,params):
        with parallel:
            with sequential:
                self.zotino.write_dac(self.dac_ch_3Dmot_current_control,
                                        params.V_mot_current_V)
                self.zotino.load()
            self.dds.get("dds_push").on()
            self.dds.get("d2_3d_r").on()
            self.dds.get("d2_3d_c").on()
            self.dds.get("d1_3d_r").on()
            self.dds.get("d1_3d_c").on()
        delay(t)

    @kernel
    def kill_mot(self,t):
        with parallel:
            self.dds.get("dds_push").off()
            self.dds.get("d2_3d_r").off()
            self.dds.get("d2_3d_c").off()
            self.dds.get("d1_3d_r").off()
            self.dds.get("d1_3d_c").off()
        delay(t)

    @kernel
    def load_2D_mot(self,t):
        with parallel:
            self.dds.get("d2_2d_c").on()
            self.dds.get("d2_2d_r").on()
        delay(t)

    @kernel
    def magnet_and_mot_off(self):
        # magnets, 2D, 3D off
        with parallel:
            with sequential:
                self.zotino.write_dac(self.dac_ch_3Dmot_current_control,0.)
                self.zotino.load()
            self.dds.get("d2_2d_c").off()
            self.dds.get("d2_2d_r").off()
            self.dds.get("push").off()
            self.dds.get("d2_3d_c").off()
            self.dds.get("d2_3d_r").off()