"""The Raman FP-cavity lock firmware (kexp/control/quarto/pid_frequency_stabilize_Raman_v2).

test_lock_core builds fp_lock_core_test.cpp against the sketch's fp_lock_core.h with the
host's clang++ and runs it: a simulated triangle scan checks the peak centroid, the
sweep gate, hold and re-lock, the rail clamp and anti-windup, micros() wrap and the
p1/i1/g1 meaning.
test_sketch_compiles compiles the whole sketch for the Quarto with arduino-cli (compile
only, nothing is uploaded). Each is skipped when its compiler is not installed.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
SKETCH = TESTS.parent / "kexp" / "control" / "quarto" / "pid_frequency_stabilize_Raman_v2"


def _arduino_cli():
    found = shutil.which("arduino-cli")
    if found:
        return found
    tail = Path("Arduino IDE") / "resources" / "app" / "lib" / "backend" / "resources" / "arduino-cli.exe"
    for root in (os.environ.get("ProgramFiles", ""), Path(os.environ.get("LOCALAPPDATA", "")) / "Programs"):
        bundled = Path(root) / tail
        if bundled.is_file():
            return str(bundled)
    return None


@pytest.mark.skipif(shutil.which("clang++") is None, reason="needs clang++")
def test_lock_core(tmp_path):
    exe = tmp_path / "fp_lock_core_test.exe"
    build = subprocess.run(["clang++", "-std=c++17", "-O2", "-Wall", "-I", str(SKETCH),
                            str(TESTS / "fp_lock_core_test.cpp"), "-o", str(exe)],
                           capture_output=True, text=True)
    assert build.returncode == 0, build.stderr
    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120)
    print(result.stdout)
    assert result.returncode == 0, result.stdout


@pytest.mark.skipif(_arduino_cli() is None, reason="needs arduino-cli (Arduino IDE 2)")
def test_sketch_compiles(tmp_path):
    result = subprocess.run([_arduino_cli(), "compile", "--fqbn", "qnimble:imxrt:quarto",
                             "--build-path", str(tmp_path / "build"), str(SKETCH)],
                            capture_output=True, text=True, timeout=600)
    if "platform not installed" in (result.stdout + result.stderr).lower():
        pytest.skip("qnimble:imxrt core not installed")
    assert result.returncode == 0, result.stdout + result.stderr
