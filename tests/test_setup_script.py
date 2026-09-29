"""setup.sh refuses to reuse a .venv built on a Python older than the 3.11 floor."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None, reason="setup.sh is a bash script"
)


def test_setup_refuses_a_venv_on_python_older_than_3_11(tmp_path):
    shutil.copy(ROOT / "setup.sh", tmp_path / "setup.sh")
    # A .venv left behind by an older setup.sh that accepted Python 3.10.
    fake_python = tmp_path / ".venv" / "bin" / "python"
    fake_python.parent.mkdir(parents=True)
    fake_python.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        '  --version) echo "Python 3.10.12" ;;\n'
        "  -c) exit 1 ;;\n"  # fails the >= 3.11 check
        '  *) echo "pip must not run" >&2; exit 42 ;;\n'
        "esac\n"
    )
    fake_python.chmod(0o755)
    # Put the interpreter running this test first on PATH so setup.sh finds a 3.11+ python3.
    env = dict(os.environ, PATH=os.pathsep.join([str(Path(sys.executable).parent), os.environ["PATH"]]))

    proc = subprocess.run(
        ["bash", str(tmp_path / "setup.sh")], cwd=tmp_path, env=env,
        capture_output=True, text=True, timeout=60,
    )

    assert proc.returncode == 1
    assert "Python 3.10.12" in proc.stderr
    assert "rm -rf .venv" in proc.stderr
    assert "pip must not run" not in proc.stderr
