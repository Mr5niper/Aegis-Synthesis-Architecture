# Building Aegis with GPU acceleration (Vulkan)

Aegis runs the language model through llama-cpp-python. That library is compiled
for a hardware backend at build time. To ship ONE executable that uses whatever
GPU is present (AMD, NVIDIA, or Intel) and falls back to CPU when there is none,
Aegis is built against the Vulkan backend.

## Why Vulkan

Vulkan is a cross-vendor GPU API. Its runtime ships inside the normal AMD /
NVIDIA / Intel graphics driver that end users already have. So a single
Vulkan-compiled exe:

- uses whatever GPU the machine has, chosen at runtime, with nothing for the
  user to install, and
- falls back to CPU automatically when there is no usable GPU.

That is exactly the "one all-inclusive exe" model: end users install nothing.
The Vulkan SDK and compiler are needed ONLY on the build machine, one time, to
produce the exe.

## What the build needs (on the BUILD machine only)

There is no reliable prebuilt Vulkan wheel for llama-cpp-python on this Python
version, so the default build compiles it from source. That needs three tools
installed on the machine that builds the exe (end users need none of this):

1. Vulkan SDK - https://vulkan.lunarg.com/sdk/home (Core install is enough).
   Its installer sets the VULKAN_SDK environment variable.
2. CMake - https://cmake.org/download/ (Windows x64 installer). During setup,
   choose "Add CMake to the system PATH".
3. Visual Studio Build Tools 2026 (or 2022) with the "Desktop development with
   C++" workload - https://visualstudio.microsoft.com/downloads/ (under
   "Tools for Visual Studio" -> "Build Tools for Visual Studio").

Reboot after installing so VULKAN_SDK and PATH are live.

## Building

Default build (Vulkan, the exe you ship):

```
BUILD_EXE.bat
```

The script checks the three prerequisites, then compiles llama-cpp-python
(pinned to the same version the app is tested against) from source with
`-DGGML_VULKAN=on`, and bundles the result into `dist\Aegis.exe`.

If the compiler is not found, run the build from the "x64 Native Tools Command
Prompt for VS 2022" (Start menu, installed with the Build Tools) so cl.exe is on
PATH, then run `BUILD_EXE.bat` from there.

### CPU-only fallback build

To build on a machine WITHOUT the Vulkan toolchain, or to produce a CPU-only
exe on purpose:

```
BUILD_EXE.bat cpu
```

This installs the prebuilt CPU wheel (no compiler/SDK needed). The resulting exe
never uses the GPU. It is a valid fallback, not the intended shipping build.

## The version is intentionally pinned

llama-cpp-python is pinned to the same version on BOTH the Vulkan and CPU paths.
That is the exact version the rest of Aegis is written and tested against
(streaming API, create_chat_completion, chunk shapes, cancellation). Only the
COMPILE differs for the Vulkan build; the version does not change, so nothing
else in the app has to change or risk breaking. Bumping the version is a
separate decision with its own testing, not part of enabling GPU.

## Confirming the GPU is actually used

When Aegis starts it prints a hardware line and per-model params, e.g.:

```
[hardware] CPU threads: 15 | RAM: 32.0 GB | GPU: amd | llama backend: vulkan (usable for offload)
[model:default] n_ctx=4096 n_threads=15 n_gpu_layers=-1
```

`n_gpu_layers=-1` means all layers were offloaded to the GPU. `n_gpu_layers=0`
means CPU-only: either no usable GPU, or the installed llama-cpp-python is a
CPU-only build. If you built the Vulkan exe but still see `n_gpu_layers=0` with a
GPU present, the Vulkan DLLs may not have been bundled - see below.

## Known issues

- Vulkan shader compilation can fail on Windows during the from-source build.
  This is an upstream llama.cpp issue, not an Aegis one. If it happens, make
  sure the Vulkan SDK Core is installed and you are building from the VS Native
  Tools prompt. As a stopgap you can ship the CPU build (`BUILD_EXE.bat cpu`).
- The PyInstaller spec bundles the llama_cpp DLLs via collect_dynamic_libs,
  which gathers everything in the installed llama_cpp/lib folder - including the
  Vulkan ggml backend DLL. If a GPU is present at runtime but offload does not
  happen, confirm the Vulkan DLL is inside the exe's bundled llama_cpp/lib.
