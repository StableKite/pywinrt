"""Compile the nine StableKite WinRT 3.2.1 wheels on Windows x86-64.

Use a checkout derived from wheels/v3.2.1.x, with its generated 3.2.1 SDK.
This is a compilation check; it neither imports WinRT nor publishes wheels.
"""

import argparse
from email.parser import BytesParser
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import struct
import subprocess
import sys
import sysconfig
import zipfile

PACKAGES = (
    "winrt-runtime",
    "winrt-Windows.Foundation",
    "winrt-Windows.Foundation.Collections",
    "winrt-Windows.Devices.Radios",
    "winrt-Windows.Devices.Enumeration",
    "winrt-Windows.Devices.Bluetooth",
    "winrt-Windows.Devices.Bluetooth.Advertisement",
    "winrt-Windows.Devices.Bluetooth.GenericAttributeProfile",
    "winrt-Windows.Storage.Streams",
)
VERSION = "3.2.1"
TAG = "cp314-cp314t-win_amd64"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def check_interpreter():
    require(os.name == "nt", "Windows is required")
    require(platform.python_implementation() == "CPython", "CPython is required")
    require(sys.version_info[:2] == (3, 14), "CPython 3.14 is required")
    require(sysconfig.get_config_var("Py_GIL_DISABLED") == 1, "CPython 3.14t is required")
    require(struct.calcsize("P") == 8, "64-bit Python is required")
    require(sysconfig.get_platform() == "win-amd64", "Windows x86-64 Python is required")
    require("/DPy_GIL_DISABLED=1" in os.environ.get("CL", "").split(), "MSVC free-threaded macro is missing")
    packages = {}
    for name in ("pip", "setuptools", "wheel", "build", "uv"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            pass
    receipt = {
        "implementation": sys.implementation.name,
        "version": sys.version,
        "version_info": list(sys.version_info[:3]),
        "executable": sys.executable,
        "system": platform.system(),
        "machine": platform.machine(),
        "pointer_bits": struct.calcsize("P") * 8,
        "gil_disabled": sysconfig.get_config_var("Py_GIL_DISABLED"),
        "soabi": sysconfig.get_config_var("SOABI"),
        "compiler": platform.python_compiler(),
        "CL": os.environ.get("CL", ""),
        "build_packages": packages,
    }
    print("STABLEKITE_BUILD_INTERPRETER:" + json.dumps(receipt), flush=True)


def verify_wheel(path, package):
    require(path.name.endswith("-" + TAG + ".whl"), "Unexpected wheel tag: " + path.name)
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), "Duplicate wheel members")
        metadata = [name for name in names if name.endswith(".dist-info/METADATA")]
        wheel_info = [name for name in names if name.endswith(".dist-info/WHEEL")]
        require(len(metadata) == len(wheel_info) == 1, "Ambiguous wheel metadata")
        info = BytesParser().parsebytes(archive.read(metadata[0]))
        normalize = lambda name: re.sub(r"[-_.]+", "-", name).lower()
        require(normalize(info["Name"]) == normalize(package), "Wrong wheel distribution")
        require(info["Version"] == VERSION, "Wrong wheel release")
        wheel = BytesParser().parsebytes(archive.read(wheel_info[0]))
        require(wheel.get_all("Tag") == [TAG], "Wrong wheel metadata tag")
        require(wheel["Root-Is-Purelib"] == "false", "Expected a native wheel")
        require(any(name.endswith(".pyd") for name in names), "Native extension is missing")
    return {"package": package, "file": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size, "tag": TAG}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parent.parent, help="Checkout containing the regenerated WinRT 3.2.1 projection and SDK.")
    parser.add_argument("--output-dir", type=Path, default=Path("wheelhouse/stablekite-cp314t"))
    parser.add_argument("--package", action="append", choices=PACKAGES, help="Build only this package; repeat to select several. The default is all nine.")
    parser.add_argument("--check-interpreter", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.check_interpreter:
        check_interpreter()
        return

    require(os.name == "nt", "Windows is required")
    require(importlib.metadata.version("cibuildwheel") == "3.2.1", "Install cibuildwheel[uv]==3.2.1")
    root = args.source_root.resolve()
    sdk = root / "projection/winrt-sdk"
    require((sdk / "pywinrt-version.txt").read_text().strip() == VERSION, "Use the regenerated 3.2.1 SDK, not the 0.0.0 development SDK")
    require('#define PYWINRT_VERSION "3.2.1"' in (sdk / "src/winrt_sdk/pywinrt/pywinrt_version.h").read_text(), "SDK header version mismatch")
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    selected = tuple(dict.fromkeys(args.package or PACKAGES))
    results = []
    for package in selected:
        relative = "projection/winrt-runtime" if package == "winrt-runtime" else "projection/winrt/" + package
        project = root / relative
        require((project / "pywinrt-version.txt").read_text().strip() == VERSION, "Projection version mismatch: " + package)
        environment = {key: value for key, value in os.environ.items() if not key.startswith("CIBW_") and key not in ("PYTHONHOME", "PYTHONPATH", "PYTHON_GIL", "CL", "_CL_")}
        environment.update({
            "CL": "/DPy_GIL_DISABLED=1",
            "CIBW_BUILD": "cp314t-win_amd64",
            "CIBW_ARCHS": "AMD64",
            "CIBW_ENABLE": "cpython-freethreading",
            "CIBW_TEST_SKIP": "*",
            "CIBW_ENVIRONMENT_WINDOWS": 'PYTHONPATH="' + (sdk / "src").as_posix() + '" CL="/DPy_GIL_DISABLED=1"',
            "CIBW_BEFORE_BUILD_WINDOWS": 'uv pip install setuptools==84.0.0 wheel==0.45.1 && python "' + Path(__file__).resolve().as_posix() + '" --check-interpreter',
        })
        if package == "winrt-runtime":
            environment["CIBW_REPAIR_WHEEL_COMMAND_WINDOWS"] = 'python "' + (root / "scripts/add_msvcp140_dll.py").as_posix() + '" "{wheel}" "{dest_dir}"'
        command = [sys.executable, "-m", "cibuildwheel", ".", "--only", "cp314t-win_amd64"]
        identifiers = subprocess.check_output(command + ["--print-build-identifiers"], cwd=project, env=environment, text=True).split()
        require(identifiers == ["cp314t-win_amd64"], "Wrong build selector: " + repr(identifiers))
        destination = output / package
        subprocess.check_call(command + ["--output-dir", str(destination)], cwd=project, env=environment)
        wheels = list(destination.glob("*.whl"))
        require(len(wheels) == 1, "Expected exactly one wheel for " + package)
        results.append(verify_wheel(wheels[0], package))
    (output / "compile-report.json").write_text(json.dumps({"status": "PASS", "scope": "compile-only", "runtime_qualification": "NOT_RUN", "source_commit": source, "sdk_version": VERSION, "selected_packages": selected, "full_nine_package_set": set(selected) == set(PACKAGES), "wheels": results}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
