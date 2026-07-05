#!/usr/bin/env python3
# build_executable.py
#
# Cross-platform build script for Aegis Synthesis Architecture.
#
# This is the Linux/macOS counterpart to BUILD_EXE.bat (which remains the
# supported, tested path on Windows). It performs the same logical steps the
# Windows batch file does, but in portable Python so it can run on Linux and
# macOS as well:
#
#   1. Verify the Python version.
#   2. Create / reuse a virtual environment (venv).
#   3. Upgrade pip / wheel and pin setuptools<82.
#   4. Install PyTorch (CPU) from the appropriate wheel index.
#   5. Install llama-cpp-python from a prebuilt wheel (no C/C++ compiler).
#   6. Install the remaining pinned dependencies from requirements.txt.
#   7. Build the executable with PyInstaller using assistant_gui.spec.
#   8. Copy config.yaml next to the built executable.
#
# IMPORTANT - PyInstaller does NOT cross-compile. Running this on Linux makes
# a Linux binary, on macOS a macOS binary, on Windows a Windows .exe. To make
# a build for a given OS you must run this script ON that OS (or a CI runner /
# VM for it). There is no way to build a macOS app from Linux or vice versa.
#
# IMPORTANT - The dependency wheel situation differs per platform, and only the
# Windows path has been tested by the maintainer. The Linux and macOS install
# steps below are provided so others can build on their own machines, but they
# may need local adjustment (see BUILD_CROSS_PLATFORM.md). In particular:
#   - llama-cpp-python prebuilt-wheel availability differs by OS, Python
#     version, and CPU architecture. The pinned version here matches the
#     Windows cp313 CPU wheel; on Linux/macOS a different version or a source
#     build (which needs a C/C++ compiler + CMake) may be required.
#   - On Apple Silicon you may prefer a Metal-enabled llama-cpp-python build
#     instead of the CPU wheel.
#
# Usage:
#   python3 build_executable.py            # full build (venv + deps + bundle)
#   python3 build_executable.py --no-venv  # use the current environment as-is
#   python3 build_executable.py --deps-only
#   python3 build_executable.py --build-only

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# --- configuration --------------------------------------------------------
# Keep these in sync with BUILD_EXE.bat so all platforms build the same way.
REQUIRED_PYTHON = (3, 13)            # major, minor expected by the pinned deps
LLAMA_VERSION = "0.3.2"             # pinned; matches the cp313 CPU wheel set
TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"
# llama-cpp-python prebuilt CPU wheels (maintained by the upstream author).
LLAMA_CPU_INDEX = "https://abetlen.github.io/llama-cpp-python/whl/cpu"
# Source distribution of the pinned llama-cpp-python, used for the opt-in GPU
# build (compiled from source with a GPU backend). Same version as the CPU path.
LLAMA_SDIST_URL = (
    "https://files.pythonhosted.org/packages/source/l/llama-cpp-python/"
    "llama_cpp_python-%s.tar.gz" % LLAMA_VERSION
)

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / "venv"
SPEC = "assistant_gui.spec"


def info(msg):  print("[INFO] %s" % msg)
def step(msg):  print("\n[STEP] %s" % msg)
def warn(msg):  print("[WARNING] %s" % msg)
def fail(msg):
    print("\n[ERROR] %s" % msg)
    sys.exit(1)


def venv_python(venv_dir: Path) -> Path:
    # Windows puts the interpreter in Scripts\, POSIX in bin/.
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def run(cmd, **kw):
    info("$ " + " ".join(str(c) for c in cmd))
    result = subprocess.run(cmd, **kw)
    if result.returncode != 0:
        fail("command failed (exit %d): %s" % (result.returncode, " ".join(str(c) for c in cmd)))
    return result


def check_python_version():
    step("Checking Python version")
    cur = sys.version_info
    info("Running under Python %d.%d.%d on %s" % (cur.major, cur.minor, cur.micro, platform.system()))
    if (cur.major, cur.minor) != REQUIRED_PYTHON:
        warn("This project pins dependencies to Python %d.%d wheels." % REQUIRED_PYTHON)
        warn("You are on Python %d.%d. Installs may fall back to source builds or fail." % (cur.major, cur.minor))
        warn("Continue only if you know the wheels exist for your Python version.")


def create_venv():
    step("Creating virtual environment in venv")
    if VENV_DIR.exists():
        info("venv already exists; reusing it.")
        return
    run([sys.executable, "-m", "venv", str(VENV_DIR)])


def pip_install(py: Path, args, extra_env=None):
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    run([str(py), "-m", "pip", "install"] + args, env=env)


def _default_gpu_backend() -> str:
    """Pick the GPU backend that matches this OS.

    Linux and Windows use Vulkan (cross-vendor: AMD/NVIDIA/Intel). macOS has no
    Vulkan; Apple GPUs use Metal, which is the correct llama.cpp GPU backend
    there. Returns the CMake flag fragment for the backend, or "" if unknown.
    """
    if sys.platform == "darwin":
        return "-DGGML_METAL=on"
    # Linux and Windows
    return "-DGGML_VULKAN=on"


def install_llama_gpu_from_source(py: Path):
    """Compile and install llama-cpp-python with a GPU backend from source.

    This mirrors the Windows Vulkan path in BUILD_EXE.bat: download the pinned
    source, add a missing #include <chrono> to two vendor C++ files (needed on
    newer toolchains; llama.cpp issue 11834), and build with the GPU backend and
    without the unused llava vision example.

    Backend: Vulkan on Linux, Metal on macOS. This is UNTESTED by the maintainer
    on both platforms and needs a working C/C++ toolchain plus, on Linux, the
    Vulkan SDK/headers. On any failure the caller falls back to the CPU wheel.

    Requires: a C/C++ compiler and CMake on PATH. On Linux also the Vulkan SDK
    or distro packages (libvulkan-dev, glslang/shaderc). See
    BUILD_CROSS_PLATFORM.md for the per-distro package names.
    """
    import tarfile
    import urllib.request

    backend_flag = _default_gpu_backend()
    backend_name = "Metal" if sys.platform == "darwin" else "Vulkan"
    step("Installing llama-cpp-python==%s from source (%s GPU backend)" % (LLAMA_VERSION, backend_name))
    info("This is the slow part and is UNTESTED on this platform; CPU fallback applies if it fails.")

    work = ROOT / "_lcpb"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    sdist = work / ("llama_cpp_python-%s.tar.gz" % LLAMA_VERSION)

    info("Downloading source: %s" % LLAMA_SDIST_URL)
    urllib.request.urlretrieve(LLAMA_SDIST_URL, sdist)

    # Unpack, skipping the vendor spm-headers symlinks (Swift Package Manager
    # only; they can break extraction on some systems and are unused here).
    def _safe(members):
        for m in members:
            if "/spm-headers/" in m.name or m.name.endswith("/spm-headers"):
                continue
            yield m
    with tarfile.open(sdist, "r:gz") as tf:
        tf.extractall(work, members=_safe(tf.getmembers()))

    srcs = [p for p in work.iterdir() if p.is_dir() and p.name.startswith("llama_cpp_python-")]
    if not srcs:
        raise RuntimeError("could not find unpacked llama-cpp-python source")
    src = srcs[0]

    # Add #include <chrono> to the two vendor files that assume it transitively.
    for rel in ("vendor/llama.cpp/common/common.cpp", "vendor/llama.cpp/common/log.cpp"):
        f = src / rel
        if f.exists():
            text = f.read_text(encoding="utf-8", errors="ignore")
            if "#include <chrono>" not in text:
                f.write_text("#include <chrono>\n" + text, encoding="utf-8")
                info("patched %s" % rel)

    # Build the patched local source with the GPU backend and no llava.
    env = dict(os.environ)
    env["CMAKE_ARGS"] = "%s -DLLAVA_BUILD=OFF" % backend_flag
    info("CMAKE_ARGS=%s" % env["CMAKE_ARGS"])
    run([str(py), "-m", "pip", "install", "--no-cache-dir",
         "--no-binary", "llama-cpp-python", str(src)], env=env)

    shutil.rmtree(work, ignore_errors=True)


def install_dependencies(py: Path, gpu: bool = False):
    step("Upgrading pip / wheel and pinning setuptools")
    pip_install(py, ["--upgrade", "pip", "wheel"])
    pip_install(py, ["setuptools<82"])

    step("Installing PyTorch (CPU build)")
    # The CPU index serves wheels for all three desktop OSes. On Apple Silicon
    # the default PyPI torch wheel is already arm64; the CPU index is still fine.
    pip_install(py, ["--no-cache-dir", "torch", "--index-url", TORCH_CPU_INDEX])

    if gpu:
        # Opt-in GPU build: compile llama-cpp-python from source with Vulkan
        # (Linux) or Metal (macOS). Untested; on ANY failure fall back to the
        # prebuilt CPU wheel so the build still produces a working program.
        try:
            install_llama_gpu_from_source(py)
        except Exception as e:
            warn("GPU build of llama-cpp-python failed: %s" % e)
            warn("Falling back to the prebuilt CPU wheel. The program will run,")
            warn("on the CPU only. See BUILD_CROSS_PLATFORM.md to fix the GPU build.")
            _install_llama_cpu(py)
    else:
        _install_llama_cpu(py)

    step("Installing remaining dependencies from requirements.txt")
    # --only-binary :all: forbids ANY source build of C-extension packages, so a
    # missing wheel fails fast instead of invoking a compiler. pygetwindow and
    # pyrect are pure-Python sdists with no wheel, so they are allowed to build
    # from sdist (a plain copy, no compiler) via --no-binary.
    pip_install(py, [
        "--no-cache-dir", "--only-binary", ":all:",
        "--no-binary", "pygetwindow,pyrect",
        "-r", "requirements.txt",
    ])


def _install_llama_cpu(py: Path):
    step("Installing llama-cpp-python==%s (prebuilt CPU wheel, no compiler)" % LLAMA_VERSION)
    # --only-binary forbids a from-source build. If no wheel exists for this
    # OS/Python/arch, this fails fast with a clear message rather than trying
    # to invoke a C compiler. See BUILD_CROSS_PLATFORM.md for alternatives.
    try:
        pip_install(py, [
            "--no-cache-dir", "llama-cpp-python==%s" % LLAMA_VERSION,
            "--only-binary", ":all:", "--extra-index-url", LLAMA_CPU_INDEX,
        ])
    except SystemExit:
        warn("No prebuilt llama-cpp-python==%s wheel for this platform/Python/arch." % LLAMA_VERSION)
        warn("Options: pick a version that has a wheel for your platform, or build")
        warn("llama-cpp-python from source (needs a C/C++ compiler + CMake).")
        warn("See BUILD_CROSS_PLATFORM.md.")
        raise


def ensure_packages_and_folders():
    step("Ensuring src package __init__.py files and runtime folders exist")
    subpkgs = ["agent", "core", "internet", "learning", "memory", "mesh",
               "proactive", "secure", "services", "tools", "ui", "utils"]
    src = ROOT / "src"
    for name in subpkgs:
        d = src / name
        if d.is_dir():
            init = d / "__init__.py"
            if not init.exists():
                init.write_text("")
    top_init = src / "__init__.py"
    if not top_init.exists():
        top_init.write_text("")
    for folder in ("models", "data"):
        (ROOT / folder).mkdir(exist_ok=True)


def check_icon():
    # Mirror the spec's platform-icon logic so we can warn early. A missing
    # icon is not fatal (the spec falls back to no icon), unlike the Windows
    # batch file which treats it as an error.
    if sys.platform.startswith("win"):
        icon = ROOT / "aegis.ico"
    elif sys.platform == "darwin":
        icon = ROOT / "aegis.icns"
    else:
        icon = None  # Linux: no embedded icon
    if icon is not None and not icon.exists():
        warn("%s not found; the build will proceed without a custom icon." % icon.name)


def build(py: Path):
    step("Building with PyInstaller (%s)" % SPEC)
    if not (ROOT / SPEC).exists():
        fail("%s not found in %s" % (SPEC, ROOT))
    check_icon()
    run([str(py), "-m", "PyInstaller", "--clean", "--noconfirm", SPEC])


def copy_config():
    step("Copying config.yaml next to the built executable")
    dist = ROOT / "dist"
    cfg = ROOT / "config.yaml"
    if not cfg.exists():
        warn("config.yaml not found; skipping copy.")
        return
    dist.mkdir(exist_ok=True)
    shutil.copy2(cfg, dist / "config.yaml")
    info("Copied config.yaml to ./dist/config.yaml")


def main():
    ap = argparse.ArgumentParser(description="Build the Aegis executable (Linux/macOS/Windows).")
    ap.add_argument("--no-venv", action="store_true",
                    help="Use the current Python environment instead of creating venv.")
    ap.add_argument("--deps-only", action="store_true", help="Install dependencies, do not build.")
    ap.add_argument("--build-only", action="store_true",
                    help="Build only; assumes dependencies are already installed.")
    ap.add_argument("--gpu", action="store_true",
                    help="Opt-in: compile llama-cpp-python with a GPU backend "
                         "(Vulkan on Linux, Metal on macOS) instead of the CPU "
                         "wheel. Needs a C/C++ toolchain + CMake (and the Vulkan "
                         "SDK on Linux). UNTESTED; falls back to CPU on failure.")
    args = ap.parse_args()

    # Allow AEGIS_GPU=1 as an alternative to the flag.
    gpu = args.gpu or os.environ.get("AEGIS_GPU", "").strip() not in ("", "0")

    os.chdir(ROOT)
    check_python_version()

    if args.no_venv:
        py = Path(sys.executable)
        info("Using current environment: %s" % py)
    else:
        create_venv()
        py = venv_python(VENV_DIR)
        if not py.exists():
            fail("venv python not found at %s" % py)

    if not args.build_only:
        install_dependencies(py, gpu=gpu)
        ensure_packages_and_folders()

    if args.deps_only:
        info("Dependencies installed. Skipping build (--deps-only).")
        return

    if args.build_only:
        ensure_packages_and_folders()

    build(py)
    copy_config()

    print("\n[SUCCESS] Build complete. The executable is in ./dist")
    if sys.platform == "darwin":
        print("[NOTE] On macOS you may need to clear the quarantine attribute before")
        print("       running: xattr -dr com.apple.quarantine dist/Aegis")
    print("[NOTE] On first launch Aegis downloads the model into ./models next to")
    print("       the executable unless you placed a .gguf there beforehand.")


if __name__ == "__main__":
    main()
