from waxx.control.misc.moglabs import MOGDevice
from waxx.control.misc.moglabs_wavemeter import WavemeterClient as WavemeterWaxx, WavemeterController, DummyWavemeterController, DummyWavemeterClient
from kexp.config.ip import WAVEMETER_MOGLABS_IP
from kexp.config.expt_params import ExptParams

LOCK_TOLERANCE = 60.e6

class Wavemeter(WavemeterWaxx):
    def __init__(self,
                 ch,target_freq,
                 wavemeter_device: WavemeterController,
                 locked_tolerance=LOCK_TOLERANCE):
        super().__init__(ch,target_freq,wavemeter_device,locked_tolerance)


class LazyWavemeter():
    """One FZW channel, connected at the run's claim.

    The MOGLabs FZW takes ONE TCP client at a time, so the frame never
    connects while it is built (a warm-launched run is built while another
    run holds the machine): ``fzw_frame.connect()`` (kexp Base.claim_hardware)
    does, and makes each channel a ``Wavemeter`` -- or a
    ``DummyWavemeterClient`` when the wavemeter cannot be reached, as before.
    Every attribute not set here goes to that client; a use before the claim
    connects first. Host-only: kernels reach it only through RPCs
    (RydbergBeam._read_lock), so which client it holds is never compiled in.
    """

    def __init__(self, frame, ch, target_freq):
        self._frame = frame
        self.ch = ch
        self.target_freq = target_freq
        self.key = ""
        self._impl = None

    @property
    def client(self):
        if self._impl is None:
            self._frame.connect()
        return self._impl

    def __getattr__(self, name):
        # only for attributes not found the normal way; never connects for a
        # probe (the ARTIQ compiler's, hasattr) or before the queue's GO
        if name.startswith("_") or name in ("kernel_invariants", "artiq_embedded"):
            raise AttributeError(name)
        from waxx.util.device_state import queue_gate
        if not queue_gate.go_passed():
            raise AttributeError(f"wavemeter {self.key or self.ch}.{name}: the wavemeter "
                                 f"is connected at the run's claim, after the queue's GO")
        return getattr(self.client, name)


class fzw_frame():
    def __init__(self, params=ExptParams(), connect=False):

        p = params

        self._fzw = None
        self._connected = False

        self.ry_405 = self.add_wavemeter(2, target_frequency=p.frequency_target_405_lock)
        self.ry_980 = self.add_wavemeter(5, target_frequency=p.frequency_target_980_lock)

        self.write_keys()

        if connect:
            self.connect()

    def write_keys(self):
        for key in self.__dict__.keys():
            if isinstance(self.__dict__[key], (Wavemeter, LazyWavemeter)):
                self.__dict__[key].key = key

    def add_wavemeter(self, ch, target_frequency) -> LazyWavemeter:
        return LazyWavemeter(self, ch, target_frequency)

    def _channels(self):
        return [v for v in self.__dict__.values() if isinstance(v, LazyWavemeter)]

    def connect(self):
        """The run's claim: open the FZW (an exclusive TCP connection) and
        give every channel its client. Once per frame; a failure falls back
        to the dummy clients (lock status not checked), as it always has."""
        if self._connected:
            return
        self._connected = True
        try:
            self._fzw = WavemeterController(WAVEMETER_MOGLABS_IP)
        except:
            print('Failed to connect to wavemeter -- please close wavemeter software if it is open. Lock status will not be checked.')
            self._fzw = DummyWavemeterController()
        for lazy in self._channels():
            if isinstance(self._fzw, WavemeterController):
                impl = Wavemeter(ch=lazy.ch, target_freq=lazy.target_freq,
                                 wavemeter_device=self._fzw)
                impl.key = lazy.key
            else:
                impl = DummyWavemeterClient()
            lazy._impl = impl
