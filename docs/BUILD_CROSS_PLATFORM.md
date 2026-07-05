# Building Aegis on Linux and macOS

The supported, maintainer-tested build is the Windows build via `BUILD_EXE.bat`,
which produces `dist/Aegis.exe`. This document describes how to build Aegis on
Linux and macOS using `build_executable.py` (or the `Makefile`).

These Linux and macOS paths are provided so you can build Aegis yourself on your
own machine. They have not been tested by the maintainer, who does not have
Linux or macOS hardware. Expect to make small local adjustments, mainly around
the `llama-cpp-python` and `torch` wheels for your platform. Where that is
likely, it is called out below.

## The one rule that surprises people: no cross-compiling

PyInstaller bundles the Python interpreter and native libraries for the machine
it runs on. It cannot build for another operating system. Concretely:

- A Linux build must be produced on Linux. The output is an ELF binary.
- A macOS build must be produced on macOS. The output is a Mach-O binary.
- A Windows build must be produced on Windows. The output is a `.exe`.

You cannot build a macOS app on Linux, or a Linux binary on Windows, and so on.
To produce all three you need one machine (or CI runner, or VM) per operating
system. A common approach is GitHub Actions with `windows-latest`,
`ubuntu-latest`, and `macos-latest` runners.

## Prerequisites (all platforms)

- Python 3.13 (the dependencies are pinned to CPython 3.13 wheels). On another
  Python version the pinned wheels may not exist and installation can fail or
  fall back to a source build.
- About 5-6 GB free disk for the model the app downloads on first run, plus
  build space.
- An internet connection for the first dependency install and first model
  download.

## Linux

```
python3 build_executable.py
```

or with make:

```
make build
```

This creates `venv`, installs dependencies (CPU `torch`, a prebuilt
`llama-cpp-python` wheel, then the pinned `requirements.txt`), and runs
PyInstaller against `assistant_gui.spec`. The result is `dist/Aegis` (an ELF
executable) with `config.yaml` copied beside it.

Notes specific to Linux:

- PyInstaller does not embed an icon into a Linux ELF binary. If you want a
  desktop icon, ship a `.desktop` launcher that references a `.png`; that is
  outside the scope of this build.
- If the prebuilt `llama-cpp-python==0.3.2` CPU wheel does not cover your
  distribution/glibc, see "When the llama-cpp-python wheel is missing" below.

## macOS

The macOS icon (`aegis.icns`) ships with the project in the root directory, and
the spec uses it automatically on macOS, so the build picks it up with no extra
steps.

```
python3 build_executable.py
```

or:

```
make build
```

The result is `dist/Aegis` (a Mach-O executable) with `config.yaml` beside it.

Notes specific to macOS:

- Gatekeeper quarantine: a binary built locally is unsigned. Before running it
  the first time you may need to clear the quarantine attribute:
  `xattr -dr com.apple.quarantine dist/Aegis`
- Apple Silicon (M-series): the CPU `llama-cpp-python` wheel works. For GPU
  acceleration use the Metal build via `--gpu` (see "GPU acceleration" below).
- Code signing and notarization (needed to distribute to other Macs without
  warnings) are out of scope for this script.

## GPU acceleration (opt-in, untested)

By default the Linux and macOS build installs a CPU-only `llama-cpp-python`, so
the program runs entirely on the CPU. All of Aegis's other behavior is the same
as on Windows: one model resident at a time, context sized automatically to the
machine, the auto-saving Web Access panel, the theme, and so on. Those are pure
Python and need no build changes; only GPU inference does.

To build with GPU acceleration, add `--gpu` (or set `AEGIS_GPU=1`):

```
python3 build_executable.py --gpu
# or
make build-gpu
```

This compiles `llama-cpp-python` from source with a GPU backend instead of
installing the CPU wheel:

- Linux: the Vulkan backend (`-DGGML_VULKAN=on`), the same cross-vendor backend
  the Windows build uses. It runs on AMD, NVIDIA, or Intel GPUs at runtime.
- macOS: the Metal backend (`-DGGML_METAL=on`). macOS has no Vulkan; Metal is
  the correct GPU path for Apple GPUs. Metal reports unified memory, which the
  context sizing reads the same way it reads VRAM.

Either way the same source patch as the Windows build is applied (a missing
`#include <chrono>` in two vendor files) and the unused llava vision example is
skipped. If the GPU compile fails for any reason, the script prints a warning
and falls back to the CPU wheel, so you still get a working program.

This GPU path is a best-effort mirror of the Windows build and has NOT been
tested by the maintainer on Linux or macOS. Expect to install prerequisites and
possibly adjust for your platform.

Prerequisites for `--gpu`:

- A C/C++ compiler and CMake on PATH.
  - Debian/Ubuntu: `sudo apt install build-essential cmake`
  - Fedora: `sudo dnf install gcc-c++ cmake`
  - macOS: Xcode command-line tools (`xcode-select --install`); CMake via
    `brew install cmake`.
- Linux only, for the Vulkan backend: the Vulkan SDK or your distro's Vulkan
  development packages and shader tools.
  - Debian/Ubuntu: `sudo apt install libvulkan-dev glslang-tools spirv-tools`
    (or install the LunarG Vulkan SDK for your distro).
  - Fedora: `sudo dnf install vulkan-loader-devel glslang spirv-tools`
  - The end user still needs nothing beyond their normal GPU driver; the SDK is
    only for building.
- macOS Metal needs no extra SDK beyond the Xcode command-line tools.

## When the llama-cpp-python wheel is missing

`build_executable.py` installs `llama-cpp-python==0.3.2` with `--only-binary`,
which refuses a source build. That version is pinned because it is the one with
a known-good prebuilt CPU wheel set. If no wheel exists for your platform,
Python version, or CPU architecture, the install stops with a clear message
instead of silently trying to compile. Your options:

1. Pick a `llama-cpp-python` version that publishes a wheel for your platform
   (check the CPU wheel index and PyPI), and set `LLAMA_VERSION` near the top of
   `build_executable.py` accordingly. Confirm the model still loads; some
   versions changed behavior.
2. Build `llama-cpp-python` from source. This needs a C/C++ compiler and CMake
   (`build-essential` and `cmake` on Debian/Ubuntu; Xcode command-line tools on
   macOS). Install it into the venv yourself, then run
   `python3 build_executable.py --build-only --no-venv` to skip the wheel-only
   dependency step and go straight to the PyInstaller build.

The same applies to `torch`: the CPU index covers the common platforms, but if
your platform is not served you may need a different torch install for your OS
and architecture.

## Command reference

`build_executable.py` flags:

- (no flags): create/reuse `venv`, install dependencies (CPU), build.
- `--no-venv`: use the current Python environment instead of creating `venv`.
- `--deps-only`: install dependencies, do not build.
- `--build-only`: build only, assuming dependencies are already installed.
- `--gpu`: compile `llama-cpp-python` with a GPU backend (Vulkan on Linux, Metal
  on macOS) instead of the CPU wheel. Untested; falls back to CPU on failure.
  `AEGIS_GPU=1` does the same.

`Makefile` targets: `install`, `install-gpu`, `build`, `build-gpu`,
`build-only`, `run-gui`, `run-headless`, `run-nexus`, `clean`, `clean-venv`.
Run `make help` for the list.

## What the build produces

- `dist/Aegis` (Linux/macOS) or `dist/Aegis.exe` (Windows): a single-file
  executable.
- `dist/config.yaml`: a copy of the configuration, read from beside the
  executable at runtime. Edit this to change settings.
- `./models` and `./data`: created next to the executable at runtime. The model
  is downloaded into `./models` on first launch if no `.gguf` is present.

Models and user data are never bundled into the executable; they live next to
it so they persist across rebuilds and updates.
