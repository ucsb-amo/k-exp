from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp.config.dds_id import dds_frame
from kexp.config.ttl_id import ttl_frame
from kexp.config.expt_params import ExptParams
from kexp.config.camera_id import CameraParams
from kexp.control.misc.painted_lightsheet import lightsheet
from kexp.control import BaslerUSB, AndorEMCCD, DummyCamera
from kexp.util.data.run_info import RunInfo
from kexp.util.data.counter import counter
import pypylon.pylon as py
import numpy as np
from kexp.util.artiq.async_print import aprint
import logging
from kexp.calibrations import (high_field_imaging_detuning,
                                low_field_imaging_detuning,
                                low_field_pid_imaging_detuning,
                                I_LF_HF_THRESHOLD)
from kexp.config.camera_id import img_types as img, cameras
from artiq.coredevice.sampler import Sampler

dv = -10.e9

class Image():
    def __init__(self):
        self.dds = dds_frame()
        self.ttl = ttl_frame()
        self.params = ExptParams()
        self.camera_params = CameraParams()
        self.setup_camera = True
        self.run_info = RunInfo()
        self.camera = DummyCamera()
        self.lightsheet = lightsheet()
        self.scan_xvars = []
        self._counter = counter()

    ### Imaging sequences ###

    @kernel
    def set_imaging_shutters(self):
        """Opens the imaging shutter for the relevant beam, and closes the
        shutters for the other imaging beam paths.

        Note that for Andor, fluorescence imaging is currently set up to use the
        xy imaging beam. This should be switched to the z-imaging beam when it
        is installed.
        """        
        if self.camera_params.key == cameras.andor.key:
            if self.run_info.imaging_type == img.FLUORESCENCE:
                self.ttl.imaging_shutter_x.off()
                self.ttl.imaging_shutter_xy.on()
            else:
                self.ttl.imaging_shutter_x.on()
                self.ttl.imaging_shutter_xy.off()
        else:
            self.ttl.imaging_shutter_x.off()
            self.ttl.imaging_shutter_xy.on()

    @kernel
    def close_imaging_shutters(self):
        """Closes all imaging shutters.
        """        
        self.ttl.imaging_shutter_x.off()
        self.ttl.imaging_shutter_xy.off()

    @kernel
    def light_image(self, t=dv):
        """Takes an image (PWA or PWOA). Leaves the timeline cursor at the end
        of the camera exposure time (camera_params.exposure_time).

        Args:
            t (float, optional): The imaging light pulse time. Defaults to
            ExptParams.t_imaging pulse.
        """        
        if t == dv:
            t = self.params.t_imaging_pulse
        self.trigger_camera()
        self.pulse_imaging_light(t)
        delay(self.camera_params.exposure_time - t)
        self._counter.light_img_idx = self._counter.light_img_idx + 1

    @kernel
    def light_image0(self, t=dv):
        """Takes an image (PWA or PWOA). Leaves the timeline cursor at the end
        of the camera exposure time (camera_params.exposure_time).

        Args:
            t (float, optional): The imaging light pulse time. Defaults to
            ExptParams.t_imaging pulse.
        """        
        if t == dv:
            t = self.params.t_imaging_pulse
        self.trigger_camera()
        self.pulse_imaging_light(t)
        # self.sampler.sample()
        delay(self.camera_params.exposure_time - t)
        self._counter.light_img_idx = self._counter.light_img_idx + 1
        # delay(1.e-3)

    @kernel
    def dark_image(self):
        self.kill_imaging_light()
        self.trigger_camera()
        delay(self.camera_params.exposure_time)

        self.reset_imaging_beam_settings()

    @kernel
    def pulse_imaging_light(self,t=dv,
                           detune_c=dv,
                           detune_r=dv,
                           amp_c=dv,
                           amp_r=dv,
                           andor_fluor_with_d2_3d_beams = False):
        """Pulses the relevant imaging light for time t. Which beam(s) is pulsed depends on RunInfo.imaging_type.

        - For Andor, pulses the normal imaging beam DDS for both absorption and
        fluorescence (unless andor_fluor_with_d2_3d_beams == True, then uses D2
        3D MOT beams.
        - For the 2D Basler, pulses the 2D MOT beams.
        - For the xy basler (and other cameras), pulses the 3D MOT beams.

        Args:
            - t (float, optional): The imaging pulse time. Defaults to ExptParams.t_imaging_pulse.
            detune_c (float, optional): The cooler detuning for fluorescence
            imaging with MOT beams (3D or 2D).
            - detune_r (float, optional): The repump detuning for fluorescence
            imaging with MOT beams (3D or 2D).
            - amp_c (float, optional): The cooler amplitude for fluorescence
            imaging with MOT beams (3D or 2D).
            - amp_r (float, optional): The repump amplitude for fluorescence
            imaging with MOT beams (3D or 2D).
            - andor_fluor_with_d2_3d_beams (bool, optional): Whether or not to use
            the 3D MOT beams for Andor fluorescence imaging. If False, uses the
            normal x-imaging fiber, which should be installed on the z-imaging
            path to avoid the light directly hitting the Andor sensor.
        """        
        if t == dv:
            t = self.params.t_imaging_pulse
        
        if self.camera_params.key == cameras.basler_2dmot.key:
            if detune_c == dv:
                detune_c = self.params.detune_d2_2d_c_imaging
            if detune_r == dv:
                detune_r = self.params.detune_d2_2d_r_imaging
            if amp_c == dv:
                amp_c = self.params.amp_d2_2d_c_imaging
            if amp_r == dv:
                amp_r = self.params.amp_d2_2d_r_imaging
        else:
            if detune_c == dv:
                detune_c = self.params.detune_d2_c_imaging
            if detune_r == dv:
                detune_r = self.params.detune_d2_r_imaging
            if amp_c == dv:
                amp_c = self.params.amp_d2_c_imaging
            if amp_r == dv:
                amp_r = self.params.amp_d2_r_imaging

        if self.run_info.imaging_type == img.ABSORPTION or self.run_info.imaging_type == img.DISPERSIVE:
            self.pulse_img_beam(t)
            
        elif self.run_info.imaging_type == img.FLUORESCENCE:
            if self.camera_params.key == cameras.andor.key:
                if andor_fluor_with_d2_3d_beams:
                    self.pulse_resonant_mot_beams(t)
                else:
                    self.pulse_img_beam(t)
            elif self.camera_params.key == cameras.basler_2dmot.key:
                self.pulse_2d_mot_beams(t)
            else:
                self.pulse_resonant_mot_beams(t)

    @kernel
    def pulse_img_beam(self,t):
        """Pulses the imaging beam.

        Args:
            t (float): The time of the imaging pulse.
        """        
        self.dds.imaging.on()
        # self.ttl.img_beam_sw.on()
        delay(t)
        # self.ttl.img_beam_sw.off()
        self.dds.imaging.off()

    @kernel
    def pulse_2d_mot_beams(self,t,
                           detune_c=dv,
                           detune_r=dv,
                           amp_c=dv,
                           amp_r=dv):
        """
        Sets D2 2D MOT beams to resonance (or the specified detuning) and turns
        them on for time t.

        Args:
            t (float): Time (in seconds) to hold the 2D MOT beams on.
        """
        if detune_c == dv:
            detune_c = self.params.detune_d2_2d_c_imaging
        if detune_r == dv:
            detune_r = self.params.detune_d2_2d_r_imaging
        if amp_c == dv:
            amp_c = self.params.amp_d2_2d_c_imaging
        if amp_r == dv:
            amp_r = self.params.amp_d2_2d_r_imaging
        
        self.dds.d2_2dh_c.set_dds_gamma(detune_c, amplitude=amp_c)
        self.dds.d2_2dh_r.set_dds_gamma(detune_r, amplitude=amp_r)
        self.dds.d2_2dv_c.set_dds_gamma(detune_c, amplitude=amp_c)
        self.dds.d2_2dv_r.set_dds_gamma(detune_r, amplitude=amp_r)
        with parallel:
            self.dds.d2_2dh_c.on()
            self.dds.d2_2dh_r.on()
            self.dds.d2_2dv_c.on()
            self.dds.d2_2dv_r.on()
        delay(t)
        with parallel:
            self.dds.d2_2dh_c.off()
            self.dds.d2_2dh_r.off()
            self.dds.d2_2dv_c.off()
            self.dds.d2_2dv_r.off()

    @kernel
    def pulse_resonant_mot_beams(self,t,
                                 detune_c=dv,
                                 detune_r=dv,
                                 amp_c=dv,
                                 amp_r=dv):
        """
        Sets D2 3D MOT beams to resonance (or the specified detuning) and turns
        them on for time t.

        Args:
            t (float): Time (in seconds) to hold the MOT beams on.
        """
        if detune_c == dv:
            detune_c = self.params.detune_d2_c_imaging
        if detune_r == dv:
            detune_r = self.params.detune_d2_r_imaging
        if amp_c == dv:
            amp_c = self.params.amp_d2_c_imaging
        if amp_r == dv:
            amp_r = self.params.amp_d2_r_imaging

        self.dds.d2_3d_c.set_dds_gamma(detune_c, amplitude=amp_c)
        self.dds.d2_3d_r.set_dds_gamma(detune_r, amplitude=amp_r)
        with parallel:
            self.dds.d2_3d_c.on()
            self.dds.d2_3d_r.on()
        delay(t)
        with parallel:
            self.dds.d2_3d_c.off()
            self.dds.d2_3d_r.off()

    @kernel
    def pulse_D1_beams(self,t,
                        detune_c=dv,
                        detune_r=dv,
                        v_pd_c=dv,
                        v_pd_r=dv):
        """
        Sets D1 GM beams to resonance (or the specified detuning) and turns them
        on for time t.

        Args:
            t (float): Time (in seconds) to hold the resonant MOT beams on.
        """
        if v_pd_c == dv:
            v_pd_c = self.params.v_pd_d1_c_gm
        if v_pd_r == dv:
            v_pd_r = self.params.v_pd_d1_r_gm

        self.dds.d1_3d_c.set_dds_gamma(detune_c, v_pd=v_pd_c)
        self.dds.d1_3d_r.set_dds_gamma(detune_r, v_pd=v_pd_r)
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
        """Takes a light image (PWA), delays, another light image (PWOA), delay,
        then a dark image.
        """        
        # self.dds.imaging.set_dds(amplitude=self.camera_params.amp_imaging)
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.ttl.pd_scope_trig3.pulse(1.e-6)
        # atoms image (pwa)
        self.light_image0()

        # self.lightsheet.off()

        # light-only image (pwoa)
        delay(self.camera_params.t_light_only_image_delay * s)
        self.light_image()

        self.close_imaging_shutters()

        # dark image
        delay(self.camera_params.t_dark_image_delay * s)
        self.dark_image()

    @kernel
    def abs_image_in_trap(self):
        """Abs image, but takes the light image with the tweezer light on.
        """        

        # atoms image (pwa)
        self.light_image()

        self.tweezer.off()
        self.lightsheet.off()

        # light-only image (pwoa)
        delay(self.camera_params.t_light_only_image_delay * s)
        self.light_image()

        self.close_imaging_shutters()

        # dark image
        delay(self.camera_params.t_dark_image_delay)
        self.dark_image()

    @kernel
    def kill_imaging_light(self):    
        """Turns off the RF switches and sets amplitudes to zero for DDS
        channels controlling light that would otherwise pollute the dark image.
        """        
        if self.run_info.imaging_type == img.ABSORPTION or self.run_info.imaging_type == img.DISPERSIVE:
            self.ttl.img_beam_sw.off()
            self.dds.imaging.set_dds(amplitude=0.)
        elif self.run_info.imaging_type == img.FLUORESCENCE:
            # fully turn off the 3d MOT beams (incl. set amp=0.)
            with parallel:
                self.dds.d2_3d_c.off()
                self.dds.d2_3d_r.off()
            self.dds.d2_3d_c.set_dds(amplitude=0.)
            self.dds.d2_3d_r.set_dds(amplitude=0.)
            # if imaging on 2D MOT camera, also fully kill 2D MOT beams
            if self.camera_params.key == cameras.basler_2dmot.key:
                with parallel:
                    self.dds.d2_2dh_c.off()
                    self.dds.d2_2dh_r.off()
                    self.dds.d2_2dv_c.off()
                    self.dds.d2_2dv_c.off()
                self.dds.d2_2dh_c.set_dds(amplitude=0.)
                self.dds.d2_2dh_r.set_dds(amplitude=0.)
                self.dds.d2_2dv_c.set_dds(amplitude=0.)
                self.dds.d2_2dv_c.set_dds(amplitude=0.)

    @kernel
    def reset_imaging_beam_settings(self):
        """Sets the amplitudes (but does not turn on) whichever beams were just
        turned off for the dark image. Which beams are referenced depends on
        the imaging type.
        """        
        if self.run_info.imaging_type == img.ABSORPTION or self.run_info.imaging_type == img.DISPERSIVE:
            self.dds.imaging.set_dds(amplitude=self.camera_params.amp_imaging)
        elif self.run_info.imaging_type == img.FLUORESCENCE:
            if self.camera_params.key == cameras.basler_2dmot.key:
                self.dds.d2_2dh_c.set_dds(amplitude=self.params.amp_d2_2d_c_imaging)
                self.dds.d2_2dh_r.set_dds(amplitude=self.params.amp_d2_2d_r_imaging)
                self.dds.d2_2dv_c.set_dds(amplitude=self.params.amp_d2_2d_c_imaging)
                self.dds.d2_2dv_r.set_dds(amplitude=self.params.amp_d2_2d_r_imaging)
            else:
                self.dds.d2_3d_c.set_dds(amplitude=self.params.amp_d2_c_imaging)
                self.dds.d2_3d_r.set_dds(amplitude=self.params.amp_d2_r_imaging)

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
        self._counter.img_idx = self._counter.img_idx + 1
        delay(t_adv * s)


    @kernel
    def cleanup_image_count(self):
        N_pwa_target = self.params.N_pwa_per_shot
        light_img_idx = self._counter.light_img_idx
        img_idx = self._counter.img_idx

        if self.setup_camera:
            if light_img_idx == N_pwa_target \
                and img_idx == N_pwa_target:

                delay(self.camera_params.t_light_only_image_delay)
                self.light_image()
                
                self.close_imaging_shutters()
                delay(self.camera_params.t_dark_image_delay)
                self.dark_image()

            elif light_img_idx == N_pwa_target + 1 \
                and img_idx == N_pwa_target + 2:
                pass

            else:
                raise ValueError("Incorrect number of PWA acquired during the shot.")
        
        self._counter.light_img_idx = 0
        self._counter.img_idx = 0
    ###

    @portable(flags={"fast-math"})
    def imaging_detuning_to_beat_ref(self, frequency_detuned=dv) -> TFloat:
        """Converts a desired imaging detuning to the required beat lock reference.

        Makes reference to the beat lock sign, which DDS channel drives the AO
        to frequency shift the imaging light, and the reference multiplier
        setting on the beat lock controller.

        Args:
            frequency_detuned (float, optional): The desired imaging detuning
            from the brightest D2 resonance in Hz. Whether the detuning is
            relative to F=2 -> 4P3/2 or F=1 -> 4P3/2 depends on the parameter
            ExptParams.imaging_state (if == 1: F=1, if == 2: F=2)

        Returns:
            TFloat: the required beat lock reference frequency in Hz.
        """        
        if frequency_detuned == dv:
            if self.params.imaging_state == 1.:
                frequency_detuned = self.params.frequency_detuned_imaging_F1
            elif self.params.imaging_state == 2.:
                frequency_detuned = self.params.frequency_detuned_imaging

        # +1 for lock greater frequency than reference (Gain switch "+"), vice versa ("-")
        beat_sign = self.params.beatlock_sign

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
    def set_high_field_imaging(self, i_outer, pid_bool=False, amp_imaging = dv):
        """Sets the high field imaging detuning according to the current in the
        outer coil (as measured on a transducer). Also sets the imaging DDS
        amplitude.

        Args:
            i_outer (float): The outer coil current (transducer) in A at which
            the imaging will take place.
            pid_bool (float): Whether or not the PID is enabled during imaging.
            Defaults to False.
            amp_imaging (float, optional): Imaging DDS amplitude. Defaults to
            camera_params.amp_imaging.
        """        
        if i_outer > I_LF_HF_THRESHOLD:
            detuning = high_field_imaging_detuning(i_transducer=i_outer)
        elif not pid_bool:
            detuning = low_field_imaging_detuning(i_transducer=i_outer)
        else:
            detuning = low_field_pid_imaging_detuning(i_pid=i_outer)
        
        self.set_imaging_detuning(detuning, amp=amp_imaging)

    def get_N_img(self):
        """
        Computes the number of images to be taken during the sequence from the
        length of the specified xvars, stores in self.params.N_img. For
        absorption imaging, 3 images per shot. For fluorescence imaging,
        variable pwa images (ExptParams.N_pwa_per_shot, default = 1), then 1
        each pwoa and dark images.
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

        if self.run_info.imaging_type == img.ABSORPTION:
            images_per_shot = 3
        else:
            images_per_shot = self.params.N_pwa_per_shot + 2

        N_img = images_per_shot * N_img # 3 images per value of independent variable (xvar)

        msg += f" {N_img} total images expected."
        print(msg)
        return N_img