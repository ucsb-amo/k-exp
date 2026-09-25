"""RydbergBeamBase._read_lock: each reading is independent, never raises,
and a failed reading is stored as 0. (never the previous shot's value).

Duck-typed siglent / wavemeter stand-ins; nothing touches hardware.
"""

import pytest

from kexp.control.rydberg_lasers import RydbergBeamBase


class FakeSiglent:
    def __init__(self):
        self.frequency = 422.7e6
        self.fail = False

    def _stash_defaults(self):
        pass

    def get_frequency(self):
        if self.fail:
            raise ConnectionError("siglent link down")
        return self.frequency


class FakeWavemeter:
    key = "ry_test"

    def __init__(self):
        self.frequency = 305.8e12
        self.fail = False
        self.lock_status_calls = []
        self.get_frequency_calls = 0

    def lock_status(self, frequency_shift=0., robust=True):
        if self.fail:
            raise TimeoutError("wavemeter link down")
        self.lock_status_calls.append(frequency_shift)
        return self.frequency

    def get_frequency(self):
        self.get_frequency_calls += 1
        if self.fail:
            raise TimeoutError("wavemeter link down")
        return self.frequency


class Container:
    def __init__(self):
        self.values = []

    def put_data(self, v):
        self.values.append(v)


@pytest.fixture
def beam():
    sig, fzw = FakeSiglent(), FakeWavemeter()
    b = RydbergBeamBase(siglent_ch=sig, dac_pid=None, ttl_pid_clear=None,
                        eo_shift_direction=-1, wavemeter=fzw,
                        lock_data_container=Container(),
                        siglent_freq_data_container=Container(),
                        cavity_ao_frequency=0., cavity_ao_order=0)
    return b, sig, fzw


def test_both_up(beam):
    b, sig, fzw = beam
    assert b._read_lock(True) == [305.8e12, 422.7e6]
    assert fzw.lock_status_calls == [-422.7e6]     # eo_shift_direction * f_siglent


def test_siglent_down_still_records_wavemeter_without_verdict(beam, capsys):
    b, sig, fzw = beam
    sig.fail = True
    assert b._read_lock(True) == [305.8e12, 0.]
    assert fzw.lock_status_calls == []             # no target -> no lock verdict
    assert fzw.get_frequency_calls == 1
    assert "siglent read failed" in capsys.readouterr().out


def test_wavemeter_down_still_records_siglent(beam, capsys):
    b, sig, fzw = beam
    fzw.fail = True
    assert b._read_lock(True) == [0., 422.7e6]
    assert "wavemeter read failed" in capsys.readouterr().out


def test_both_down_never_raises(beam, capsys):
    b, sig, fzw = beam
    sig.fail = fzw.fail = True
    assert b._read_lock(False) == [0., 0.]
    out = capsys.readouterr().out
    assert "siglent read failed" in out and "wavemeter read failed" in out
