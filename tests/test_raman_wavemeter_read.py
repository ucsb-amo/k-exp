"""Control._read_raman_wavemeter: the host side of the per-shot Raman laser
frequency read (data.frequency_detuned_raman / frequency_raman_detuning_std).

Offline: the reader is a stub, nothing goes on the network.
"""
from types import SimpleNamespace

import pytest

from kexp.base.control import Control
from kexp.config.expt_params import ExptParams


def _host(reply=None, exc=None):
    calls = []

    def get_average(n, max_age_s):
        calls.append((n, max_age_s))
        if exc is not None:
            raise exc
        return reply

    obj = SimpleNamespace(p=ExptParams(),
                          raman_wavemeter=SimpleNamespace(get_average=get_average))
    return obj, calls


def _read(obj):
    return Control._read_raman_wavemeter(obj)


def test_params_defaults():
    p = ExptParams()
    assert p.frequency_raman_wavemeter_reference == 389.28617e12
    assert p.N_raman_wavemeter_avg == 20
    assert p.t_raman_wavemeter_max_age > 0.


def test_detuning_is_mean_minus_reference():
    obj, calls = _host({"ok": True, "n_used": 20, "mean_hz": 389.33236e12, "std_hz": 5.9e6})
    f = _read(obj)
    assert f[0] == pytest.approx(389.33236e12 - 389.28617e12, abs=1.)
    assert f[1] == 5.9e6
    assert calls == [(20, obj.p.t_raman_wavemeter_max_age)]


def test_partial_average_is_used():
    obj, _ = _host({"ok": True, "n_used": 3, "mean_hz": 389.3e12, "std_hz": 1e6})
    assert _read(obj)[0] == pytest.approx(389.3e12 - 389.28617e12, abs=1.)


@pytest.mark.parametrize("reply", [
    None,                                                     # no server / latched
    {"ok": False, "n_used": 0, "error": "no readings"},       # nothing fresh
    {"ok": True, "n_used": 0, "mean_hz": None, "std_hz": None},
])
def test_no_reading_records_zero(reply):
    obj, _ = _host(reply)
    assert _read(obj) == [0., 0.]


def test_reader_exception_records_zero():
    obj, _ = _host(exc=RuntimeError("boom"))
    assert _read(obj) == [0., 0.]


def test_containers_registered():
    from kexp.config.data_vault import DataVault
    import inspect
    src = inspect.getsource(DataVault.__init__)
    assert "self.frequency_detuned_raman = " in src
    assert "self.frequency_raman_detuning_std = " in src
