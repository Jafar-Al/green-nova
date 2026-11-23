"""Runs the portable CPU example end to end (checkpoints + runtime_data + sample geometry + Model 1 polygon ids)."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_portable_example_runs_cpu_only():
    r = subprocess.run([sys.executable, str(ROOT / "models" / "restoration" / "examples" / "run_example.py")], capture_output=True, text=True, timeout=300,
                       env={**__import__("os").environ, "CUDA_VISIBLE_DEVICES": "", "PYTHONPATH": str(ROOT)})
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
    assert "EXAMPLE OK" in r.stdout
    assert "sha256 ok" in r.stdout
