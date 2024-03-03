from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp.config.dds_id import dds_frame
from kexp.config.ttl_id import ttl_frame
from kexp.config.expt_params import ExptParams
from kexp.config.camera_params import CameraParams
from kexp.control.misc.painted_lightsheet import lightsheet
from kexp.control import BaslerUSB, AndorEMCCD, DummyCamera
from kexp.util.data import RunInfo
from kexp.base.sub.devices import Devices
import pypylon.pylon as py
import numpy as np
from kexp.util.artiq.async_print import aprint
import logging

dv = -10.e9

class Image():
    def __init__(self):
        self.dds = dds_frame()
        self.ttl = ttl_frame()
        self.params = ExptParams()
        self.camera_params = CameraParams()
        self.run_info = RunInfo()
        self.camera = DummyCamera()
        self.lightsheet = lightsheet()
        self.scan_xvars = []

    ### Imaging sequences ###

    @kernel
    def pulse_imaging_light(self,t):
        self.dds.imaging.on()
        # self.dds.d2_3d_r.on()
        delay(t)
        self.dds.imaging.off()
        # self.dds.d2_3d_r.off()

    @kernel
    def flash_repump(self,t=dv,detune=dv,amp=dv):
        if t == dv:
            t = self.params.t_repump_flash_imaging
        if detune == dv:
            detune = self.params.detune_d2_r_imaging
        if amp == dv:
            amp = self.params.amp_d2_r_imaging

        self.dds.d2_3d_r.set_dds_gamma(delta=detune,amplitude=amp)
        self.dds.d2_3d_r.on()
        delay(t)
        self.dds.d2_3d_r.off()

    @kernel
    def pulse_resonant_mot_beams(self,t):
        """
        Sets D2 3D MOT beams to resonance and turns them on for time t.

        Args:
            t (float): Time (in seconds) to hold the resonant MOT beams on.
        """        
        with parallel:
            self.dds.d2_3d_c.set_dds_gamma(0.)
            self.dds.d2_3d_r.set_dds_gamma(0.)
        with parallel:
            self.dds.d2_3d_c.on()
            self.dds.d2_3d_r.on()
        delay(t)
        with parallel:
            self.dds.d2_3d_c.off()
            self.dds.d2_3d_r.off()

    @kernel
    def pulse_D1_beams(self,t):
        """
        Sets D1 GM beams to resonance and turns them on for time t.

        Args:
            t (float): Time (in seconds) to hold the resonant MOT beams on.
        """        
        with parallel:
            self.dds.d1_3d_c.set_dds_gamma(0.)
            self.dds.d1_3d_r.set_dds_gamma(0.)
        with parallel:
            self.dds.d1_3d_c.on()
            self.dds.d1_3d_r.on()
        delay(t)
        with parallel:
            self.dds.d1_3d_c.off()
            self.dds.d1_3d_r.off()

    @kernel
    def abs_image(self):

        self.trigger_camera()
        self.pulse_imaging_light(self.params.t_imaging_pulse * s)

        delay(self.camera_params.t_light_only_image_delay * s)
        self.trigger_camera()
        self.pulse_imaging_light(self.params.t_imaging_pulse * s)

        self.dds.imaging.off()
        delay(self.camera_params.t_dark_image_delay * s)
        self.trigger_camera()

    @kernel
    def fl_image(self, t=-1., with_light=True):
        
        if t==-1:
           t = self.camera_params.exposure_time

        self.dds.imaging.set_dds(amplitude=self.params.amp_imaging_fluor)
        self.dds.second_imaging.set_dds(amplitude=.01)
        self.dds.d2_3d_r.set_dds(0.,amplitude=.06)

        self.trigger_camera()
        if with_light:
            self.pulse_imaging_light(t * s)
            # self.dds.second_imaging.on()
            # delay(t)
            # self.dds.second_imaging.off()
            # self.pulse_resonant_mot_beams(t * s)
            # self.pulse_D1_beams(t * s)
            pass

        # self.lightsheet.off()
        # self.dds.tweezer.off()

        delay(self.params.t_light_only_image_delay * s)

        self.lightsheet.on()
        delay(10.e-3*s)
        self.lightsheet.off()

        self.trigger_camera()
        if with_light:
            self.pulse_imaging_light(t * s)
            # self.dds.second_imaging.on()
            # delay(t)
            # self.dds.second_imaging.off()
            # self.pulse_resonant_mot_beams(t * s)
            # self.pulse_D1_beams(t * s)
            pass

    @kernel
    def trigger_camera(self):
        '''
        Written to pretrigger camera such that the camera exposure begins at the
        timeline cursor position where this is called. Returns the timeline
        cursor to this position after pretrigger.
        '''
        delay(-self.camera_params.exposure_delay * s)
        self.ttl.camera.pulse(self.camera_params.t_camera_trigger * s)
        t_adv = self.camera_params.exposure_delay - self.camera_params.t_camera_trigger
        delay(t_adv * s)

    ###

    @kernel(flags={"fast-math"})
    def set_imaging_detuning(self, detuning = dv, amp = dv):
        '''
        Sets the detuning of the beat-locked imaging laser (in Hz).

        Imaging detuning is controlled by two things -- the Vescent offset lock
        and a 100 MHz double pass (+1 order).

        The offset lock has a multiplier, N, that determines the offset lock
        frequency relative to the lock point of the D2 laser locked at the
        crossover feature for the D2 transition. Offset = N * reference freqeuency.
        
        The reference frequency is provided by a DDS channel (dds_frame.beatlock_ref).
        '''

        # determine this manually -- minimum offset frequency where the offset lock is happy
        if amp == dv:
            amp = self.camera_params.amp_imaging
        if detuning == dv:
            detuning = self.params.frequency_detuned_imaging

        self.dds.imaging.set_dds(frequency=self.params.frequency_ao_imaging,amplitude=amp)

        f_minimum_offset_frequency = 150.e6

        f_hyperfine_splitting_4s_MHz = 461.7 * 1.e6
        f_shift_resonance = f_hyperfine_splitting_4s_MHz / 2

        f_ao_shift = self.dds.imaging.frequency * 2

        f_offset = f_ao_shift - detuning + f_shift_resonance

        if f_offset < f_minimum_offset_frequency:
            try: 
                self.camera.Close()
            except: pass
            raise ValueError("The beat lock is unhappy at a lock point below the minimum offset.")
            
        offset_lock_multiplier_N = 8
        f_beatlock_ref = f_offset / offset_lock_multiplier_N
        
        if f_beatlock_ref < 0.:
            try: 
                self.camera.Close()
            except: pass
            raise ValueError("You tried to set the DDS to a negative frequency!")
        self.dds.beatlock_ref.set_dds(frequency=f_beatlock_ref)
        self.dds.beatlock_ref.on()

    ###

    def get_N_img(self):
        """
        Computes the number of images to be taken during the sequence from the
        length of the specified xvars, stores in self.params.N_img. For
        absorption imaging, 3 images per shot. For fluorescence imaging, 2
        images per shot.
        """                
        N_img = 1
        msg = ""

        for xvar in self.scan_xvars:
            N_img = N_img * xvar.Nvals
            msg += f" {xvar.Nvals} values of {xvar.key}."
        self.params.N_shots_with_repeats = N_img

        msg += f" {N_img} total shots."

        ### I have no idea what this is for. ###
        if isinstance(self.params.N_repeats,list):
            if len(self.params.N_repeats) == 1:
                N_repeats = self.params.N_repeats[0]
            else:
                N_repeats = 1
        else:
            N_repeats = 1
        self.params.N_shots = int(N_img / N_repeats)
        ###

        if self.run_info.absorption_image:
            images_per_shot = 3
        else:
            images_per_shot = 2

        N_img = images_per_shot * N_img # 3 images per value of independent variable (xvar)

        msg += f" {N_img} total images expected."
        print(msg)
        return N_img