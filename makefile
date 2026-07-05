# Makefile for Aegis Synthesis Architecture (Linux / macOS helper)
#
# This is a convenience wrapper for Unix-like systems. The supported, tested
# build path on Windows is BUILD_EXE.bat. On Linux/macOS the build is driven by
# build_executable.py, which mirrors the same dependency strategy.
#
# PyInstaller does NOT cross-compile: `make build` produces a binary for the OS
# it is run on. See BUILD_CROSS_PLATFORM.md for the full explanation and for the
# per-platform dependency caveats (especially llama-cpp-python wheels).
#
# The virtual environment lives in venv (matching build_executable.py and
# BUILD_EXE.bat). On POSIX the interpreter is venv/bin/python.

VENV = venv
PY = $(VENV)/bin/python
SYS_PYTHON ?= python3

.PHONY: help venv install install-gpu deps build build-gpu build-only run-gui run-headless run-nexus clean clean-venv

help:
	@echo "Aegis build targets:"
	@echo "  make install        Create venv and install all dependencies (CPU)"
	@echo "  make install-gpu    Same, but compile llama-cpp-python with a GPU backend"
	@echo "  make build          Full build (deps + PyInstaller), CPU llama-cpp-python"
	@echo "  make build-gpu      Full build with a GPU backend (Vulkan on Linux, Metal on macOS)"
	@echo "  make build-only     Build only, assuming deps are already installed"
	@echo "  make run-gui        Run the GUI from source"
	@echo "  make run-headless   Run the headless CLI from source"
	@echo "  make run-nexus      Run the Nexus FastAPI server from source"
	@echo "  make clean          Remove build/ dist/ and __pycache__"
	@echo "  make clean-venv     Remove the venv virtual environment"
	@echo ""
	@echo "The GPU targets compile llama-cpp-python from source and need a C/C++"
	@echo "toolchain + CMake (and the Vulkan SDK on Linux). They are UNTESTED and"
	@echo "fall back to the CPU wheel on failure. See BUILD_CROSS_PLATFORM.md."
	@echo "PyInstaller builds for the current OS only; it cannot cross-compile."
	@echo "On Windows use BUILD_EXE.bat instead."

venv:
	$(SYS_PYTHON) -m venv $(VENV)

# Install dependencies using the same strategy as the Windows build (CPU torch,
# pinned prebuilt llama-cpp-python wheel, wheel-only requirements).
install: venv
	$(PY) build_executable.py --deps-only --no-venv

# Same as install, but compile llama-cpp-python with a GPU backend (Vulkan on
# Linux, Metal on macOS). Untested; falls back to the CPU wheel on failure.
install-gpu: venv
	$(PY) build_executable.py --deps-only --no-venv --gpu

deps: install

# Full build: build_executable.py creates/uses venv, installs deps, and runs
# PyInstaller against assistant_gui.spec. We invoke it with the system Python so
# it can create the venv itself.
build:
	$(SYS_PYTHON) build_executable.py

# Full build with a GPU backend (see install-gpu).
build-gpu:
	$(SYS_PYTHON) build_executable.py --gpu

# Build only (dependencies assumed present in venv).
build-only:
	$(PY) build_executable.py --build-only --no-venv

run-gui:
	$(PY) -m src.main_gui

run-headless:
	$(PY) -m src.main_headless

run-nexus:
	$(PY) -m uvicorn src.nexus_server:app --host 0.0.0.0 --port 7861

clean:
	rm -rf build dist
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

clean-venv:
	rm -rf $(VENV)
