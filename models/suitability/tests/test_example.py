"""The portable example must run on the sample data with a clean environment (CPU, no network)."""
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EX = HERE.parent / "examples" / "run_example.py"


def test_run_example_on_sample_data(tmp_path):
    assert (HERE.parent / "sample_data" / "jo-maan" / "features.npy").stat().st_size < 10 * 1024 * 1024
    env = {k: v for k, v in os.environ.items() if k != "GREEN_NOVA_RUNTIME"}
    r = subprocess.run([sys.executable, str(EX), str(tmp_path / "out")], capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    assert "CLASS RESULTS" in r.stdout and "mean confidence" in r.stdout and "polygon m1-jo-maan-1" in r.stdout
    assert (tmp_path / "out" / "suitability.tif").exists() and (tmp_path / "out" / "polygons.geojson").exists()
    for token in ("C:\\", "C:/", "Users"):
        assert token not in (tmp_path / "out" / "run_metadata.json").read_text()
