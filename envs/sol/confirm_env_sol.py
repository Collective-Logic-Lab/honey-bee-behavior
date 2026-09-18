"""Check the active Sol environment; use temporary files and no research data."""

import importlib
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def check(label, action):
    try:
        detail = action()
    except Exception as exc:
        print(f"FAIL {label}: {exc}", flush=True)
        return False
    print(f"PASS {label}: {detail}", flush=True)
    return True


def check_python():
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError(f"expected Python 3.12, found {platform.python_version()}")
    return platform.python_version()


def import_package(name):
    module = importlib.import_module(name)
    return getattr(module, "__version__", "imported")


def run_command(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    output = (result.stdout + result.stderr).strip()
    if result.returncode:
        raise RuntimeError(output or f"exit status {result.returncode}")
    return output.splitlines()[0] if output else "completed"


def check_binary(name, version_flag="-version"):
    executable = shutil.which(name)
    if executable is None:
        raise RuntimeError("not found on PATH; activate the shared environment")
    return f"{executable} ({run_command([executable, version_flag])})"


def check_hdf(directory):
    import pandas as pd

    expected = pd.DataFrame({"bee_id": [1, 2], "x": [0.25, 0.75]})
    path = directory / "tracks.h5"
    expected.to_hdf(path, key="tracks", format="table")
    pd.testing.assert_frame_equal(expected, pd.read_hdf(path, key="tracks"))
    return "wrote and read a small pandas/PyTables table"


def check_plot(directory):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    figure = Figure()
    canvas = FigureCanvasAgg(figure)
    figure.subplots().plot([0, 1], [0, 1])
    path = directory / "plot.png"
    canvas.print_png(path)
    if path.stat().st_size == 0:
        raise RuntimeError("empty PNG")
    return "rendered a PNG without a display"


def main():
    print(f"Python executable: {sys.executable}")
    print(f"Environment: {sys.prefix}")
    print(f"Platform: {platform.platform()}\n")
    failures = 0
    with tempfile.TemporaryDirectory(prefix="confirm-env-sol-") as temporary:
        directory = Path(temporary)
        os.environ.setdefault("MPLCONFIGDIR", str(directory / "matplotlib"))
        failures += not check("Python version", check_python)
        for name in (
            "numpy", "pandas", "scipy", "matplotlib", "seaborn", "sklearn",
            "tables", "tqdm", "IPython", "ipykernel", "ipywidgets", "ipympl",
            "jupyterlab", "cv2", "PIL", "certifi", "filelock", "portable_ffmpeg", "hive_video",
            "hive_video.resequence.cli",
        ):
            failures += not check(name, lambda name=name: import_package(name))
        failures += not check(
            "Package dependencies", lambda: run_command([sys.executable, "-m", "pip", "check"])
        )
        failures += not check("HDF5 round trip", lambda: check_hdf(directory))
        failures += not check("Headless plotting", lambda: check_plot(directory))
        for name in ("ffmpeg", "ffprobe"):
            failures += not check(name, lambda name=name: check_binary(name))
        failures += not check("gh", lambda: check_binary("gh", "--version"))

    if failures:
        print(f"\n{failures} check(s) failed. Check the active environment and messages above.")
        return 1
    print("\nEnvironment checks passed. Real data and analysis validation are still needed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
