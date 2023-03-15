from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential

class mot():
    def __init__(self):
        pass

    @kernel
    def load_mot(self,t):
        with parallel:
            with sequential:
                self.zotino.write_dac(self.dac_ch_3Dmot_current_control,
                                        self.params.V_mot_current_V)
                self.zotino.load()
            self.dds.dds_push.on()
            self.dds.d2_3d_r.on()
            self.dds.d2_3d_c.on()
            self.dds.d1_3d_r.on()
            self.dds.d1_3d_c.on()
        delay(t)

    @kernel
    def kill_mot(self,t):
        with parallel:
            self.dds.dds_push.off()
            self.dds.d2_3d_r.off()
            self.dds.d2_3d_c.off()
            self.dds.d1_3d_r.off()
            self.dds.d1_3d_c.off()
        delay(t)

    @kernel
    def load_2D_mot(self,t):
        with parallel:
            self.dds.d2_2d_c.on()
            self.dds.d2_2d_r.on()
        delay(t)

    @kernel
    def magnet_and_mot_off(self):
        # magnets, 2D, 3D off
        with parallel:
            with sequential:
                self.zotino.write_dac(self.dac_ch_3Dmot_current_control,0.)
                self.zotino.load()
            self.dds.d2_2d_c.off()
            self.dds.d2_2d_r.off()
            self.dds.push.off()
            self.dds.d2_3d_c.off()
            self.dds.d2_3d_r.off()