# Building Aegis with GPU acceleration (Vulkan)

Aegis runs the language model through llama-cpp-python. That library is compiled
for a hardware backend at build time. To ship ONE executable that uses whatever
GPU is present (AMD, NVIDIA, or Intel) and falls back to CPU when there is none,
Aegis is built against the Vulkan backend.

## Why Vulkan

Vulkan is a cross-vendor GPU API. Its runtime ships inside the normal AMD,
NVIDIA, or Intel graphics driver that end users already have. So a single
Vulkan-compiled exe:

- uses whatever GPU the machine has, chosen at runtime, with nothing for the
  user to install, and
- falls back to CPU automatically when there is no usable GPU.

That is exactly the "one all-inclusive exe" model: end users install nothing.
The Vulkan SDK and compiler are needed ONLY on the build machine, one time, to
produce the exe.

## What the build needs (on the BUILD machine only)

There is no reliable prebuilt Vulkan wheel for llama-cpp-python on this Python
version, so the default build compiles it from source. That needs the tools
below installed on the machine that builds the exe. End users need none of it.

The versions listed are the known-good set this build was verified with. Other
versions may work, but if a build fails, match these first before anything else.

1. Vulkan SDK 1.4.350.0 - https://vulkan.lunarg.com/sdk/home
   The Core install is enough (the default installer unchecks the optional
   components, which is fine). Its installer sets the VULKAN_SDK environment
   variable.
2. CMake 4.3.4 - https://cmake.org/download/ (Windows x64 installer). During
   setup choose "Add CMake to the system PATH". Use a stable release, not a
   release candidate.
3. Visual Studio 2022 Build Tools with the "Desktop development with C++"
   workload. Direct installer: https://aka.ms/vs/17/release/vs_BuildTools.exe
   This provides MSVC v143 (compiler 19.44) and the Windows 11 SDK
   (10.0.26100). Use the 2022 Build Tools specifically. The Microsoft downloads
   page now leads with the 2026 edition; the aka.ms/vs/17 link above is the
   reliable way to get 2022.

Reboot after installing so VULKAN_SDK and PATH are live.

### Verified toolchain

This is the exact combination the shipping Vulkan build was produced and
confirmed working with, on Windows, Python 3.13.12:

- Vulkan SDK 1.4.350.0
- CMake 4.3.4
- Visual Studio 2022 Build Tools, MSVC v143 (19.44)
- Windows SDK 10.0.26100
- Python 3.13.12

## Building

Default build (Vulkan, the exe you ship):

```
BUILD_EXE.bat
```

The script checks the prerequisites, downloads the pinned llama-cpp-python
source, applies a small source patch (see "Source patch" below), compiles it
from source with the Vulkan backend, and bundles the result into
`dist\Aegis.exe`.

If the compiler is not found, run the build from the "x64 Native Tools Command
Prompt for VS 2022" (Start menu, installed with the Build Tools) so cl.exe is on
PATH, then run `BUILD_EXE.bat` from there. In normal use this is not required;
CMake locates MSVC on its own, and the script only warns about cl.exe rather
than failing.

### CPU-only fallback build

To build on a machine WITHOUT the Vulkan toolchain, or to produce a CPU-only
exe on purpose:

```
BUILD_EXE.bat cpu
```

This installs the prebuilt CPU wheel (no compiler or SDK needed). The resulting
exe never uses the GPU. It is a valid fallback, not the intended shipping build.

## Source patch (why the Vulkan build downloads and patches source)

The pinned llama-cpp-python version predates a change in the Windows 11 SDK
(10.0.26100) and MSVC 17.13+. Two of its C++ files (vendor common.cpp and
log.cpp) use std::chrono without including <chrono>; older SDKs pulled that in
transitively, the current one does not, so the compile fails with
"'system_clock' is not a member of 'std::chrono'". This is llama.cpp issue
11834.

A global forced include does not work here because the codebase compiles C and
C++ files in the same targets, so a C++-only header forced onto a .c file trips
STL1003. The build therefore does the Vulkan install in explicit steps so the
fix is reproducible: download the pinned source, extract it, add
`#include <chrono>` to just those two C++ files (idempotent), then install that
patched local directory. It also passes `-DLLAVA_BUILD=OFF` to skip the llava
vision example, which this text assistant does not use and which does not build
cleanly on this toolchain.

The tar extraction skips the vendor spm-headers folder. Those entries are
symlinks used only for Swift Package Manager builds; Windows tar cannot create
them and aborts the whole extract with "Invalid argument". The real headers
they point to are separate normal files in the archive, so skipping the symlink
folder loses nothing on Windows.

None of this changes the app or the pinned version. Only the compile of that one
package differs, so nothing else in Aegis has to change.

## The version is intentionally pinned

llama-cpp-python is pinned to the same version on BOTH the Vulkan and CPU paths.
That is the exact version the rest of Aegis is written and tested against
(streaming API, create_chat_completion, chunk shapes, cancellation). Only the
COMPILE differs for the Vulkan build; the version does not change, so nothing
else in the app has to change or risk breaking. Bumping the version is a
separate decision with its own testing, not part of enabling GPU.

## Confirming the GPU is actually used

When Aegis starts it prints a hardware line, a context-sizing line, and
per-model params. On an AMD card it looks like:

```
ggml_vulkan: Found 1 Vulkan devices:
ggml_vulkan: 0 = AMD Radeon RX 7700 XT (AMD proprietary driver) | uma: 0 | fp16: 1 | warp size: 64
[hardware] CPU threads: 31 | RAM: 127.9 GB | GPU: amd, ~12.0 GB VRAM | llama backend: vulkan (usable for offload)
[ctx] GPU sizing by VRAM: 12.0 GB / 1 model(s) = 12.0 GB each -> ceiling 16384 => n_ctx=16384
[model:default] planned n_ctx=16384 n_threads=31 n_gpu_layers=-1 (loads on first use)
```

`n_gpu_layers=-1` means all layers were offloaded to the GPU. `n_gpu_layers=0`
means CPU-only: either no usable GPU, or the installed llama-cpp-python is a
CPU-only build. If you built the Vulkan exe but still see `n_gpu_layers=0` with a
GPU present, the Vulkan DLLs may not have been bundled; see "Known issues".

The `[ctx]` line shows how the context window was chosen and whether a safe
fallback was used. See "Context sizing" below.

## Context sizing

Context length is chosen at startup to fit the machine, not hardcoded. The
config ctx_size acts as a floor; the value is scaled up on capable machines and
never set above what the model was trained for.

- On a GPU build the KV cache lives in VRAM, so the ceiling is set from VRAM.
  If VRAM cannot be read (the AMD/Intel registry probe returns nothing), the
  build uses a safe fixed ceiling rather than guessing from system RAM, which
  would over-size and fail to allocate on the card.
- On a CPU build the KV cache lives in system RAM, so the ceiling is set from
  RAM.

Only one model is resident at a time (see below), so the active model is sized
against the whole card.

## One model resident at a time

Aegis loads only the ACTIVE model into memory. Switching models in the UI
unloads the current one and loads the new one on next use. This gives the active
model the whole GPU, so it can run a larger context than if several models
shared the card. The cost is a few seconds to load when you deliberately switch
models. Conversation history carries across a switch, so the new model continues
where the old one left off; it just reprocesses the recent conversation on its
first turn.

## Known issues

- If the from-source Vulkan build fails, first confirm the toolchain matches the
  verified versions above (particularly VS 2022 Build Tools, not 2026, and the
  Windows SDK 10.0.26100). Build from the VS Native Tools prompt if the compiler
  is not found. As a stopgap you can ship the CPU build (`BUILD_EXE.bat cpu`).
- The PyInstaller spec bundles the llama_cpp DLLs via collect_dynamic_libs,
  which gathers everything in the installed llama_cpp/lib folder, including the
  Vulkan ggml backend DLL. If a GPU is present at runtime but offload does not
  happen, confirm the Vulkan DLL is inside the exe's bundled llama_cpp/lib.
