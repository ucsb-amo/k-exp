from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp.config.dds_id import dds_frame
from kexp.config.ttl_id import ttl_frame
from kexp.config.expt_params import ExptParams
from kexp.config.camera_params import CameraParams
from kexp.control.misc.painted_lightsheet import lightsheet
from kexp.control import BaslerUSB, AndorEMCCD, DummyCamera
from kexp.util.data.run_info import RunInfo
from kexp.base.sub.devices import Devices
import pypylon.pylon as py
import numpy as np
from kexp.util.artiq.async_print import aprint
import logging
from kexp.calibrations import high_field_imaging_detuning

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
    def set_imaging_shutters(self):
        if self.camera_params.camera_select == 'andor':
            self.ttl.imaging_shutter_x.on()
            self.ttl.imaging_shutter_xy.off()
        else:
            self.ttl.imaging_shutter_x.off()
            self.ttl.imaging_shutter_xy.on()

    @kernel
    def pulse_imaging_light(self,t):
        self.dds.imaging.on()
        # self.dds.d2_3d_r.on()
        delay(t)
        self.dds.imaging.off()
        # self.dds.d2_3d_r.off()

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
    def dispersive_image(self,repeats=1,repeat_delay=100.e-3):
        for n in range(repeats):
            self.trigger_camera()
            self.pulse_imaging_light(self.params.t_imaging_pulse * s)
            delay(repeat_delay)

    @kernel
    def abs_image(self):

        # atoms image (pwa)
        self.trigger_camera()
        self.pulse_imaging_light(self.params.t_imaging_pulse * s)
        delay(self.camera_params.exposure_time - self.params.t_imaging_pulse)

        # light-only image (pwoa)
        delay(self.camera_params.t_light_only_image_delay * s)
        self.trigger_camera()
        self.pulse_imaging_light(self.params.t_imaging_pulse * s)
        delay(self.camera_params.exposure_time - self.params.t_imaging_pulse)

        self.ttl.imaging_shutter_x.off()
        self.ttl.imaging_shutter_xy.off()

        # dark image
        delay(self.camera_params.t_dark_image_delay * s)
        self.dds.imaging.off()
        self.dds.imaging.set_dds(amplitude=0.)
        self.trigger_camera()
        delay(self.camera_params.exposure_time)
        self.dds.imaging.set_dds(amplitude=self.camera_params.amp_imaging)

    @kernel
    def abs_image_in_trap(self):

        # atoms image (pwa)
        self.trigger_camera()
        self.pulse_imaging_light(self.params.t_imaging_pulse * s)
        delay(self.camera_params.exposure_time - self.params.t_imaging_pulse)

        self.tweezer.off()

        # light-only image (pwoa)
        delay(self.camera_params.t_light_only_image_delay * s)
        self.trigger_camera()
        self.pulse_imaging_light(self.params.t_imaging_pulse * s)
        delay(self.camera_params.exposure_time - self.params.t_imaging_pulse)

        # dark image
        delay(self.camera_params.t_dark_image_delay * s)
        self.dds.imaging.off()
        self.dds.imaging.set_dds(amplitude=0.)
        self.trigger_camera()
        delay(self.camera_params.exposure_time)
        self.dds.imaging.set_dds(amplitude=self.camera_params.amp_imaging)

    @kernel
    def light_image(self):
        self.trigger_camera()
        self.pulse_imaging_light(self.params.t_imaging_pulse)
        delay(self.camera_params.exposure_time - self.params.t_imaging_pulse)

    @kernel
    def dark_image(self):
        self.dds.imaging.off()
        self.dds.imaging.set_dds(amplitude=0.)
        self.trigger_camera()
        delay(self.camera_params.exposure_time)
        self.dds.imaging.set_dds(amplitude=self.camera_params.amp_imaging)

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

    @portable(flags={"fast-math"})
    def imaging_detuning_to_beat_ref(self, frequency_detuned=dv) -> TFloat:
        if frequency_detuned == dv:
            if self.params.imaging_state == 1.:
                frequency_detuned = self.params.frequency_detuned_imaging_F1
            elif self.params.imaging_state == 2.:
                frequency_detuned = self.params.frequency_detuned_imaging

        # +1 for lock greater frequency than reference (Gain switch "+"), vice versa ("-")
        beat_sign = -1 

        f_hyperfine_splitting_4s_MHz = 461.7 * 1.e6
        f_shift_resonance = f_hyperfine_splitting_4s_MHz / 2

        f_ao_shift = self.dds.imaging.frequency * self.dds.imaging.aom_order * 2

        #f_offset = beat_sign * ( detuning - (f_shift_resonance + f_ao_shift) )
        f_offset = beat_sign * (frequency_detuned - f_ao_shift - f_shift_resonance)

        f_beatlock_ref = f_offset / self.params.N_offset_lock_reference_multiplier

        if f_offset < self.params.frequency_minimum_offset_beatlock:
            aprint("The requested detuning results in an offset less than the minimum beat note frequency for the lock.")
        if f_beatlock_ref < 0.:
            aprint("The requested detuning would require a negative reference frequency. You'll need to flip the beat lock sign to reach this detuning.")
        if f_beatlock_ref > 400.e6:
            aprint("Invalid beatlock reference frequency for requested detuning (>400 MHz). Must be less than 400 MHz for ARTIQ DDS. Consider changing the beat lock reference multiplier.")

        return f_beatlock_ref

    @kernel(flags={"fast-math"})
    def set_imaging_detuning(self, frequency_detuned = dv, amp = dv):
        '''
        Sets the detuning of the beat-locked imaging laser (in Hz).

        Imaging detuning is controlled by two things -- the Vescent offset lock
        and a double pass (-1 order).

        The offset lock has a multiplier, N, that determines the offset lock
        frequency relative to the lock point of the D2 laser locked at the
        crossover feature for the D2 transition. Offset = N * reference freqeuency.
        
        The reference frequency is provided by a DDS channel (dds_frame.beatlock_ref).
        '''

        # determine this manually -- minimum offset frequency where the offset lock is happy
        if amp == dv:
            amp = self.camera_params.amp_imaging
        if frequency_detuned == dv:
            if self.params.imaging_state == 1.:
                frequency_detuned = self.params.frequency_detuned_imaging_F1
            elif self.params.imaging_state == 2.:
                frequency_detuned = self.params.frequency_detuned_imaging
            
        f_beatlock_ref = self.imaging_detuning_to_beat_ref(frequency_detuned=frequency_detuned)

        self.dds.imaging.set_dds(frequency=self.params.frequency_ao_imaging,amplitude=amp)

        f_minimum_offset_frequency = self.params.frequency_minimum_offset_beatlock
        f_offset = f_beatlock_ref * self.params.N_offset_lock_reference_multiplier
        if f_offset < f_minimum_offset_frequency:
            try: 
                self.camera.Close()
            except: pass
            raise ValueError("The beat lock is unhappy at a lock point below the minimum offset.")
        
        if f_beatlock_ref < 0.:
            try: 
                self.camera.Close()
            except: pass
            raise ValueError("You tried to set the DDS to a negative frequency!")
        
        self.dds.beatlock_ref.set_dds(frequency=f_beatlock_ref)
        self.dds.beatlock_ref.on()

    @kernel(flags={"fast-math"})
    def set_high_field_imaging(self, i_outer, imaging_amp = dv):

        detuning = high_field_imaging_detuning(i_outer=i_outer)
        
        self.set_imaging_detuning(detuning, amp=imaging_amp)

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
            N_img = N_img * xvar.values.shape[0]
            msg += f" {xvar.values.shape[0]} values of {xvar.key}."
        self.params.N_shots_with_repeats = N_img

        msg += f" {N_img} total shots."

        ### I have no idea what this is for. ###
        if isinstance(self.params.N_repeats,list):
            if len(self.params.N_repeats) == 1:
                N_repeats = self.params.N_repeats[0]
            else:
                N_repeats = np.prod(self.params.N_repeats)
        else:
            N_repeats = 1
        self.params.N_shots = int(N_img / N_repeats)
        ###

        if self.run_info.absorption_image:
            images_per_shot = 3
        else:
            images_per_shot = self.params.N_pwa_per_shot + 2

        N_img = images_per_shot * N_img # 3 images per value of independent variable (xvar)

        msg += f" {N_img} total images expected."
        print(msg)
        return N_img