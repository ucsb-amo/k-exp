"""Reference images of the cooling sequence, taken every shot.

``Base.__init__(diagnostic_images=True)`` (the default) builds ``self.diag``,
a DiagnosticImages, from ``kexp.config.camera_id.diagnostic_cameras``: one
triggered camera stream per DiagnosticCamera, and each DiagnosticImage bound
to its camera with its frame index.

The hooks below are the moments of the sequence a frame can be taken at.
The cooling sequence calls each one there (``self.diag.tweezer_evap()``);
an experiment with its own inline sequence calls them itself. A hook fires
every image configured ``at`` it, each ``t`` from the cursor; the cursor
stays where it was, and nothing is taken with diagnostics off or during the
warm-up shots (``Base.pre_scan`` clears ``active`` around them: no frame is
triggered, fetched or stored for a shot that saves nothing). One image can
also be fired on its own: ``self.diag.img_mot.trigger()``.

    mot_push_on(t)       mot(): the push comes on after the 2D-MOT-only window
    mot_beams_on(t)      mot(): 3D beams on, the load starts
    mot_load_end(t)      mot(): the load ends
    cmot_end()           end of cmot_d1() (GM starts here)
    gm_beams_on(t)       gm(): D1 beams on
    lightsheet_load()    end of the lightsheet ramp-up
    lightsheet_evap()    end of lightsheet evap 1
    tweezer_load()       end of the tweezer ramp-up
    tweezer_evap()       end of the last tweezer evap

A hook's argument ``t_stage`` is the length of the stage it starts (frames
after it) or ends (frames before it): a frame that would fall outside it is
skipped. 0: no limit.

New frame: a DiagnosticImage in its camera's ``images`` (camera_id). New
camera: a DiagnosticCamera entry there. New moment: a hook below (a kernel
method whose body is ``self._fire_<name>(t_stage)``) and its call in the
sequence. Nothing else changes -- no ExptParams, no
kernel code here, nothing in the diagnostic viewer.

Each frame is saved under its key with a ``<key>_meta`` record per shot
(waxa.data.camera_frames) and a ``camera_stream_<key>`` provenance record;
the run file's root attribute ``diagnostic_images`` records every image's
camera, hook, offset, frame index and own settings as the run took them.
"""

import copy
import inspect

from artiq.experiment import kernel
from artiq.language.core import kernel_from_string

from waxx.control.cameras.camera_stream_client import (
    InactiveCameraStream, TriggeredCameraStreamClient)

from kexp.config.camera_id import diagnostic_cameras
from kexp.control.cameras.camera_stream import camera_streams

# camera entry key -> frame keys
DIAGNOSTIC_FRAMES = {e.camera.key: list(e.frames) for e in diagnostic_cameras.entries()}


def _kernel_source(fn):
    """The source of a kernel function, None for anything else."""
    f = getattr(getattr(fn, 'artiq_embedded', None), 'function', None)
    if isinstance(f, str):
        return f
    return inspect.getsource(f) if callable(f) else None


def _own_class(obj, name):
    """Give ``obj`` a class of its own. ARTIQ types a host object's
    attributes per class, and each camera holds a stream of its own type
    (triggered, placeholder, inactive) -- so each camera, and each image
    (which holds its camera), needs its own class for the kernel to compile."""
    obj.__class__ = type(f"{type(obj).__name__}_{name}", (type(obj),), {})
    return obj


class DiagnosticImages:

    def __init__(self, expt, enabled=True, config=diagnostic_cameras):
        self.enabled = bool(enabled)
        self.active = self.enabled      # kernel switch: Base.pre_scan clears it for the warm-up shots
        specs = [c for c in config.entries() if c.images]
        self._check(specs)
        if self.enabled:
            # all cameras set up at once (camera_streams), registered in entry order
            built = camera_streams(expt, [
                dict(camera=spec.camera, key=spec.frames,
                     mode='triggered', on_error='dummy',
                     exposure_time=spec.exposure_time, gain=spec.gain,
                     roi=spec.roi,
                     frame_settings=spec.frame_settings or None,
                     no_roi_downsample=config.no_roi_downsample)
                for spec in specs])
        else:
            built = [InactiveCameraStream(expt, spec.frames, reason="diagnostics off")
                     for spec in specs]

        # the run's own copies of the specs, bound to their streams
        self.streams, self.cameras, self.images = {}, {}, {}
        for spec, stream in zip(specs, built):
            cam = _own_class(copy.copy(spec), spec.key)
            cam.stream = stream
            cam.diag = self
            cam.images = []
            for j, img_spec in enumerate(spec.images):
                img = _own_class(copy.copy(img_spec), img_spec.key)
                img.camera = cam
                img.j = j
                cam.images.append(img)
                self.images[img.key] = img
                setattr(self, img.key, img)
            self.streams[spec.key] = stream
            self.cameras[spec.key] = cam
        self._build_hooks()

        if self.enabled:
            up = [k for k, cs in self.streams.items()
                  if isinstance(cs, TriggeredCameraStreamClient)]
            down = [k for k in self.streams if k not in up]
            print("[diag cams] connected: " + (", ".join(up) or "none")
                  + (f" | NOT connected: {', '.join(down)}" if down else ""))

    @classmethod
    def hooks(cls):
        """The hook names, in the order they are defined: the kernel methods
        whose body fires ``self._fire_<name>`` (theirs and no other's)."""
        out = []
        for klass in reversed(cls.__mro__):
            for name, fn in vars(klass).items():
                src = _kernel_source(fn)
                if not src or "self._fire_" not in src or name in out:
                    continue
                if f"self._fire_{name}(t_stage)" not in src:
                    raise TypeError(f"{klass.__name__}.{name} must call self._fire_{name}(t_stage)")
                out.append(name)
        return out

    def _check(self, specs):
        """Refuse a config the hooks cannot fire, before any camera is set up."""
        hooks = self.hooks()
        taken = set(dir(type(self))) | {'enabled', 'active', 'streams', 'cameras', 'images'}
        seen = {}
        for spec in specs:
            for img in spec.images:
                where = f"diagnostic_cameras.{spec.key}: {img.key!r}"
                if img.at not in hooks:
                    raise ValueError(f"{where} at={img.at!r}: no such hook (one of {hooks})")
                if img.key in seen:
                    raise ValueError(f"{where} is also a frame of {seen[img.key]!r}")
                if img.key in taken:
                    raise ValueError(f"{where}: the key is taken by DiagnosticImages.{img.key}")
                seen[img.key] = spec.key

    def _build_hooks(self):
        """Each hook's ``_fire_<hook>`` becomes a kernel triggering the images
        at it, on a class of this object's own (the images differ from run to
        run). Generated code has no default arguments (ARTIQ drops them from
        kernel_from_string), hence the hook method in front of it."""
        cls = type(f"{type(self).__name__}_{id(self):x}", (type(self),), {})
        for name in self.hooks():
            keys = [k for k, img in self.images.items() if img.at == name]
            setattr(cls, f"_fire_{name}", kernel_from_string(
                ["self", "t_stage"],
                "\n".join(f"self.{k}.trigger(t_stage)" for k in keys) or "pass"))
        self.__class__ = cls

    def record(self):
        """Every image as this run takes it (the run file's root attribute
        ``diagnostic_images``)."""
        return {"enabled": self.enabled,
                "images": {k: {"camera": img.camera.key,
                               "camera_id": str(getattr(img.camera.camera, 'key', '')),
                               "frame": img.j, "at": img.at, "t": img.t,
                               **img.settings()}
                           for k, img in self.images.items()}}

    # ---- hooks: where in the sequence frames can be taken -----------------
    # Each calls its _fire_<hook>, made per run by _build_hooks from the
    # images configured at it. Keep the order of the sequence; the docstring
    # says where the sequence calls it.

    @kernel
    def mot_push_on(self, t_stage=0.):
        """mot(): where the push comes on after the 2D-MOT-only window (push
        off, 2D beams on; t_stage = the window). Only with diagnostics on."""
        self._fire_mot_push_on(t_stage)

    @kernel
    def mot_beams_on(self, t_stage=0.):
        """mot(): the 3D beams come on and the load starts (t_stage = load)."""
        self._fire_mot_beams_on(t_stage)

    @kernel
    def mot_load_end(self, t_stage=0.):
        """mot(): the end of the load (t_stage = load)."""
        self._fire_mot_load_end(t_stage)

    @kernel
    def cmot_end(self, t_stage=0.):
        """End of cmot_d1(): GM starts here."""
        self._fire_cmot_end(t_stage)

    @kernel
    def gm_beams_on(self, t_stage=0.):
        """gm(): the D1 beams come on (t_stage = GM)."""
        self._fire_gm_beams_on(t_stage)

    @kernel
    def lightsheet_load(self, t_stage=0.):
        """End of the lightsheet ramp-up (magtrap_and_load_lightsheet)."""
        self._fire_lightsheet_load(t_stage)

    @kernel
    def lightsheet_evap(self, t_stage=0.):
        """End of lightsheet evap 1 (prepare_hf/lf_tweezers)."""
        self._fire_lightsheet_evap(t_stage)

    @kernel
    def tweezer_load(self, t_stage=0.):
        """End of the tweezer ramp-up (prepare_hf/lf_tweezers)."""
        self._fire_tweezer_load(t_stage)

    @kernel
    def tweezer_evap(self, t_stage=0.):
        """End of the last tweezer evap (prepare_hf/lf_tweezers; an
        experiment with its own evap 3 calls it after that)."""
        self._fire_tweezer_evap(t_stage)

    def finish(self):
        """Drain and close every stream (end_wax does this itself)."""
        for cs in self.streams.values():
            try:
                cs.finish()
            except Exception:
                pass
