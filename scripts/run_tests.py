"""Run all tests with pytest if installed, else stdlib unittest."""
import subprocess, sys
from pathlib import Path
root = Path(__file__).resolve().parent.parent
try:
    import pytest  # noqa
    cmd = [sys.executable, "-m", "pytest", "-q", "tests"]
except ImportError:
    cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v"]
print("Running:", " ".join(cmd))
sys.exit(subprocess.call(cmd, cwd=root))
