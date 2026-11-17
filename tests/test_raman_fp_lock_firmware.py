"""The Raman FP-cavity lock firmware (kexp/control/quarto/pid_frequency_stabilize_Raman_v2).

Compiles the sketch for the Quarto with arduino-cli (compile only, nothing is
uploaded). Skipped when arduino-cli or the qnimble core is not installed.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SKETCH = (Path(__file__).resolve().parent.parent
          / "kexp" / "control" / "quarto" / "pid_frequency_stabilize_Raman_v2")


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


@pytest.mark.skipif(_arduino_cli() is None, reason="needs arduino-cli (Arduino IDE 2)")
def test_sketch_compiles(tmp_path):
    result = subprocess.run([_arduino_cli(), "compile", "--fqbn", "qnimble:imxrt:quarto",
                             "--build-path", str(tmp_path / "build"), str(SKETCH)],
                            capture_output=True, text=True, timeout=600)
    if "platform not installed" in (result.stdout + result.stderr).lower():
        pytest.skip("qnimble:imxrt core not installed")
    assert result.returncode == 0, result.stdout + result.stderr
