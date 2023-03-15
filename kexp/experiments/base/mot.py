from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential
from kexp.util.artiq.expt_params import ExptParams

@kernel
def load_mot(expt,t,params):
    with parallel:
        with sequential:
            expt.zotino.write_dac(expt.dac_ch_3Dmot_current_control,
                                    params.V_mot_current_V)
            expt.zotino.load()
        expt.dds.get("dds_push").on()
        expt.dds.get("d2_3d_r").on()
        expt.dds.get("d2_3d_c").on()
        expt.dds.get("d1_3d_r").on()
        expt.dds.get("d1_3d_c").on()
    delay(t)

@kernel
def kill_mot(expt,t):
    with parallel:
        expt.dds.get("dds_push").off()
        expt.dds.get("d2_3d_r").off()
        expt.dds.get("d2_3d_c").off()
        expt.dds.get("d1_3d_r").off()
        expt.dds.get("d1_3d_c").off()
    delay(t)

@kernel
def load_2D_mot(expt,t):
    with parallel:
        expt.dds.get("d2_2d_c").on()
        expt.dds.get("d2_2d_r").on()
    delay(t)

@kernel
def magnet_and_mot_off(expt):
    # magnets, 2D, 3D off
    with parallel:
        with sequential:
            expt.zotino.write_dac(expt.dac_ch_3Dmot_current_control,0.)
            expt.zotino.load()
        expt.dds.get("d2_2d_c").off()
        expt.dds.get("d2_2d_r").off()
        expt.dds.get("push").off()
        expt.dds.get("d2_3d_c").off()
        expt.dds.get("d2_3d_r").off()