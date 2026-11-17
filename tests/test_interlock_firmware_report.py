"""The interlock firmware v2 reports byte for byte what v1 printed, and the server parses it.

Copies the sketch's "What trips and what is reported" section (the limits, the
check and the report text: no hardware) into interlock_logic.h, then builds
tests/interlock_firmware/report_equivalence.cpp with clang++ against it and the
Arduino Opta core's Print.cpp (so numbers are formatted exactly as on the Opta).
That program runs ~20 000 cycles through v1's print code and v2's, and writes
sample v2 reports; this test then feeds those to the server's parser.

Skipped when clang++ or the Arduino Opta core is not installed.  Offline: no
serial port is opened.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from kexp.util.guis.interlock.interlock_service import InterlockService

_HERE = Path(__file__).resolve().parent
_EQUIVALENCE_CPP = _HERE / "interlock_firmware" / "report_equivalence.cpp"
_SKETCH = (_HERE.parent / "kexp" / "util" / "guis" / "interlock"
           / "interlock-arduino-code_v2" / "interlock-arduino-code_v2.ino")
_SECTION_START = "// ======== What trips and what is reported (no hardware) ========"
_SECTION_END = "// ======== End of what trips and what is reported ========"


def _logic_section() -> str:
    """The sketch's no-hardware section, exactly as written there."""
    text = _SKETCH.read_text(encoding="utf-8")
    assert text.count(_SECTION_START) == 1 and text.count(_SECTION_END) == 1, \
        "the sketch's section markers changed; update this test"
    return text.split(_SECTION_START)[1].split(_SECTION_END)[0]


def _opta_core_api_dir() -> Path | None:
    """The newest installed Arduino Opta core's api folder (Print.cpp), or None."""
    root = Path(os.environ.get("LOCALAPPDATA", "")) / "Arduino15" / "packages" / "arduino" \
        / "hardware" / "mbed_opta"
    found = sorted(root.glob("*/cores/arduino/api/Print.cpp"))
    return found[-1].parent if found else None


@pytest.fixture(scope="module")
def samples(tmp_path_factory) -> Path:
    """Build and run the equivalence program; return its folder of sample reports."""
    clang = shutil.which("clang++")
    api_dir = _opta_core_api_dir()
    if clang is None or api_dir is None:
        pytest.skip("needs clang++ and the Arduino Opta core (mbed_opta)")

    folder = tmp_path_factory.mktemp("interlock_firmware")
    (folder / "interlock_logic.h").write_text(_logic_section(), encoding="utf-8")
    exe = folder / "report_equivalence.exe"
    # -iquote, not -I: on Windows <string.h> would otherwise find the core's String.h.
    build = subprocess.run(
        [clang, "-std=c++17", "-O1", "-w",
         "-iquote", str(api_dir), "-iquote", str(folder),
         str(_EQUIVALENCE_CPP), str(api_dir / "Print.cpp"), "-o", str(exe)],
        capture_output=True, text=True, timeout=120,
    )
    assert build.returncode == 0, f"build failed:\n{build.stdout}\n{build.stderr}"

    run = subprocess.run([str(exe), str(folder)], capture_output=True, text=True, timeout=60)
    print(run.stdout)
    assert run.returncode == 0, f"v1 and v2 reports differ:\n{run.stdout}\n{run.stderr}"
    return folder


def test_v2_report_is_v1_text(samples):
    """The program exits 0 only if every cycle's text was identical; check it ran."""
    assert (samples / "samples.txt").exists()


def test_server_parses_v2_reports(samples):
    """Each sample report parses to the values the firmware was given."""
    parse = InterlockService._parse_plc_buffer   # uses no instance state
    lines = (samples / "samples.txt").read_text().splitlines()
    assert len(lines) == 40

    for line in lines:
        k, temp, f1, f2, f3, f4, tripped = line.split()
        report = (samples / f"sample_{k}.txt").read_bytes()
        sample = parse(None, report)

        assert sample is not None, f"sample {k} did not parse:\n{report!r}"
        # Printed with 5 decimals (temperature) and 2 (flows).
        assert sample.temperature_k == pytest.approx(float(temp), abs=1e-5 + 1e-6 * float(temp))
        flows = [float(f) for f in (f1, f2, f3, f4)]
        assert [sample.flow_v[m] for m in (1, 2, 3, 4)] == pytest.approx(flows, abs=0.0051)
        assert sample.plc_tripped == (tripped == "1")
