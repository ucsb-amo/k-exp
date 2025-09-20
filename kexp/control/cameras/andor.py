from pylablib.devices import Andor
from pylablib.devices.interface.camera import trim_frames
import numpy as np
import time

from queue import Queue
from PyQt6.QtCore import QThread, pyqtSignal

from pylablib.devices.Andor.atmcd32d_lib import wlib as lib
from pylablib.core.utils import general as general_utils
from pylablib.core.devio import interface

from kexp.config.timeouts import (CAMERA_GRAB_TIMEOUT_ANDOR as TIMEOUT)

def nothing():
    return False

class AndorEMCCD(Andor.AndorSDK2Camera):
    def __init__(self,
                ExposureTime=0.,
                gain = 30,
                hs_speed:int=0,
                vs_speed:int=1,
                vs_amp:int=3,
                preamp = 2):
        # overwrite a broken method in the parent class
        self._initial_setup_temperature = self._initial_setup_temperature_fixed
        # init the parent class
        super().__init__(temperature=-60,fan_mode="full")
        # run startup setting methods
        # self.activate_cameralink()
        # self.enable_frame_transfer_mode(enable=True)
        self.set_emccd_advanced()
        self.set_EMCCD_gain(gain=gain)
        self.set_exposure(ExposureTime)
        self.set_trigger_mode("ext")
        self.setup_shutter(mode="open")
        self.set_vsspeed(vs_speed)
        self.set_vsamplitude(vs_amp)
        self.set_hsspeed(typ=0,hs_speed=hs_speed)
        self.set_acquisition_mode("single")
        self.set_read_mode("image")
        self.set_cooler_mode(mode=1)
        self.set_amp_mode(preamp=preamp)
        self.activate_cameralink(1)
        
        # self.set_fast_trigger_mode(mode=1)

        self._internal_output_queue = Queue()

    def Close(self):
        self.setup_shutter(mode="closed")
        self.close()

    def Open(self):
        self.setup_shutter(mode="open")
        self.open()

    def start_grab(self, N_img, output_queue:Queue=None,
                    missing_frame="skip",
                    return_info=True, buff_size=None,
                    check_interrupt_method=nothing):
        """
        Snap `nframes` images (with preset image read mode parameters)
        Modified from pylablib.devices.interface.camera.
        
        `buff_size` determines buffer size (if ``None``, use the default size).
        Timeout is specified for a single-frame acquisition, not for the whole acquisition time.
        `missing_frame` determines what to do with frames which have been lost:
        can be ``"none"`` (replacing them with ``None``), ``"zero"`` (replacing them with zero-filled frame),
        or ``"skip"`` (skipping them, while still keeping total returned frames number to `n`).
        If ``return_info==True``, return tuple ``(frames, infos)``, where ``infos`` is a list of frame info tuples (camera-dependent);
        if some frames are missing and ``missing_frame!="skip"``, the corresponding frame info is ``None``.
        """
        if output_queue == None:
            output_queue = self._internal_output_queue

        if self.get_frame_format()=="array":
            try:
                self.set_frame_format("chunks")
                result=self.grab(nframes=N_img,frame_timeout=TIMEOUT,missing_frame=missing_frame,return_info=return_info,buff_size=buff_size)
                return tuple(np.concatenate(r,axis=0) for r in result) if return_info else np.concatenate(result,axis=0)
            finally:
                self.set_frame_format("array")
        acq_params=self._get_grab_acquisition_parameters(N_img,buff_size)
        frames,info,nacq=[],[],0
        self.start_acquisition(**acq_params)
        try:
            while nacq<N_img:
                if check_interrupt_method():
                    print('Interrupt submitted, waiting for grab loop termination...')
                    break
                self.wait_for_frame(timeout=TIMEOUT,check_interrupt_method=check_interrupt_method)
                print(f'gotem (img {nacq+1}/{N_img})') # added this line to give print statements
                if return_info:
                    new_frames,new_info,rng=self.read_multiple_images(missing_frame=missing_frame,return_info=True,return_rng=True)
                    info+=new_info
                else:
                    new_frames,rng=self.read_multiple_images(missing_frame=missing_frame,return_rng=True)
                for frame in new_frames:
                        if isinstance(frame,np.ndarray):
                            img_timestamp = time.time()
                            # img_timestamp = 0.
                            output_queue.put((frame,img_timestamp,nacq))
                frames+=new_frames
                nacq+=rng[1]-rng[0]
            frames,info=trim_frames(frames,N_img,(info if return_info else None),chunks=self.get_frame_format()=="chunks")
            return (frames,info) if return_info else frames
        finally:
            self.stop_acquisition()

    def _initial_setup_temperature_fixed(self):
        if self._start_temperature=="off":
            trng=self.get_temperature_range()
            self.set_temperature(trng[1] if trng else 0,enable_cooler=False)
        else:
            if self._start_temperature is None:
                trng=self.get_temperature_range()
                if trng:
                    self._start_temperature=trng[0]+int((trng[1]-trng[0])*0.2)
                else:
                    self._start_temperature=0
            self.set_temperature(self._start_temperature,enable_cooler=True)

    def stop_grab(self):
        try:
            self.stop_acquisition()
        except:
            pass

    @interface.use_parameters(since="frame_wait_mode")
    def wait_for_frame(self, since="lastread", nframes=1, timeout=20., error_on_stopped=False,
                       check_interrupt_method=nothing):
        """
        Wait for one or several new camera frames. (overloaded to accept interrupt)

        `since` specifies the reference point for waiting to acquire `nframes` frames;
        can be "lastread"`` (from the last read frame), ``"lastwait"`` (wait for the last successful :meth:`wait_for_frame` call),
        ``"now"`` (from the start of the current call), or ``"start"`` (from the acquisition start, i.e., wait until `nframes` frames have been acquired).
        `timeout` can be either a number, ``None`` (infinite timeout), or a tuple ``(timeout, frame_timeout)``,
        in which case the call times out if the total time exceeds ``timeout``, or a single frame wait exceeds ``frame_timeout``.
        If the call times out, raise ``TimeoutError``.
        If ``error_on_stopped==True`` and the acquisition is not running, raise ``Error``;
        otherwise, simply return ``False`` without waiting.
        """
        wait_started=False
        if isinstance(timeout,tuple):
            timeout,frame_timeout=timeout
        else:
            frame_timeout=None
        ctd=general_utils.Countdown(timeout)
        frame_ctd=general_utils.Countdown(frame_timeout)
        if not self.acquisition_in_progress():
            if error_on_stopped:
                raise self.Error("waiting for a frame while acquisition is stopped")
            else:
                return False
        last_acquired_frames=None
        while True:
            if check_interrupt_method():
                break
            acquired_frames=self._get_acquired_frames()
            if acquired_frames is None:
                if error_on_stopped:
                    raise self.Error("waiting for a frame while acquisition is stopped")
                else:
                    return False
            if acquired_frames!=last_acquired_frames:
                frame_ctd.reset()
            last_acquired_frames=acquired_frames
            if not wait_started:
                self._frame_counter.wait_start(acquired_frames)
                wait_started=True
            if self._frame_counter.is_wait_done(acquired_frames,since=since,nframes=nframes):
                break
            to,fto=ctd.time_left(),frame_ctd.time_left()
            if fto is not None:
                to=fto if to is None else min(to,fto)
            if to is not None and to<=0:
                raise self.TimeoutError
            self._wait_for_next_frame(timeout=to,idx=acquired_frames)
        self._frame_counter.wait_done()
        return True
    
    def activate_cameralink(self,state=1):
        """This function allows the user to enable or disable the Camera Link
        functionality for the camera. Enabling this functionality will start to
        stream all acquired data through the camera link interface.

        Args:
            state (int, optional): Enables/Disables Camera Link mode. 1 - Enable
            Camera Link 0 - Disable Camera Link. Defaults to 1.
        """        
        lib.SetCameraLinkMode(state)

    def set_emccd_advanced(self):
        """
        This function turns on and off access to higher EM gain levels within
        the SDK. Typically, optimal signal to noise ratio and dynamic range is
        achieved between x1 to x300 EM Gain. Higher gains of > x300 are
        recommended for single photon counting only. Before using higher levels,
        you should ensure that light levels do not exceed the regime of tens of
        photons per pixel, otherwise accelerated ageing of the sensor can occur.
        """        
        lib.SetEMAdvanced(1)

    def set_fast_trigger_mode(self, mode:int = 1):
        """
        This function will enable fast external triggering. When fast external
        triggering is enabled the system will NOT wait until a “Keep Clean”
        cycle has been completed before accepting the next trigger. This setting
        will only have an effect if the trigger mode has been set to External
        via SetTriggerMode.

        Args:
            mode (int, optional): 0 disabled. 1 enabled. Defaults to 1.
        """        
        lib.SetFastExtTrigger(mode)

    def set_cooler_mode(self, mode:int = 1):
        """This function determines whether the cooler is switched off when the
        camera is shut down.

        Args:
            mode (int, optional): 1 – Temperature is maintained on ShutDown. 0 –
            Returns to ambient temperature on ShutDown. Defaults to 1.
        """        
        lib.SetCoolerMode(mode)

    def set_vsamplitude(self, vs_amp:int = 0):
        """
        If you choose a high readout speed (a low readout time), then you should
        also consider increasing the amplitude of the Vertical Clock Voltage.
        There are five levels of amplitude available for you to choose from:
            • Normal
            • +1
            • +2
            • +3
            • +4
        Exercise caution when increasing the amplitude of the vertical clock voltage,
        since higher clocking voltages may result in increased clock-induced charge
        (noise) in your signal. In general, only the very highest vertical clocking
        speeds are likely to benefit from an increased vertical clock voltage amplitude.

        Args:
            vs_amp (int, optional): See docstring for amplitude settings.
            Defaults to 0.
        """        
        lib.SetVSAmplitude(vs_amp)

    def set_hsspeed(self, typ:int=0, hs_speed:int = 0):
        """
        This function will set the speed at which the pixels are shifted into
        the output node during the readout phase of an acquisition. Typically
        your camera will be capable of operating at several horizontal shift
        speeds. To get the actual speed that an index corresponds to use the
        GetHSSpeed function.

        Args:
            hs_speed (int, optional): the horizontal speed to be used Valid
            values 0 to GetNumberHSSpeeds()-1. Defaults to 0. 
            int type: the type of output amplifier on an EMCCD.
                0 – Standard EMCCD gain register (default).
                1 – Conventional CCD register.
        """        
        lib.SetHSSpeed(typ, hs_speed)

    def set_isolated_crop_mode_type(self, mode:int=1):
        """This function determines the method by which data is transferred in
        isolated crop mode. The default method is High Speed where multiple
        frames may be stored in the storage area of the sensor before they
        are read out. In Low Latency mode, each cropped frame is read out as
        it happens.

        Args:
            mode (int): 0 – High Speed. 1 – Low Latency. Defaults to 1.
        """        
        lib.SetIsolatedCropModeType(mode)