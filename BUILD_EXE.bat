@echo off
setlocal enabledelayedexpansion

:: ==========================================================================
:: Configuration
:: ==========================================================================
set "REQUIRED_PYTHON_VERSION=3.13.12"
set "PYTHON_DOWNLOAD_URL=https://www.python.org/downloads/release/python-31312/"
set "PY=py -3.13"

:: llama-cpp-python backend.
::
::   BUILD_EXE.bat          -> default: VULKAN. Compiles llama-cpp-python from
::                             source with the Vulkan backend so the ONE exe
::                             uses whatever GPU is present (AMD / NVIDIA /
::                             Intel) via the Vulkan runtime that ships in the
::                             GPU driver, and falls back to CPU when there is
::                             no GPU. Requires the Vulkan SDK + CMake + MSVC
::                             C++ build tools ON THIS BUILD MACHINE (one-time;
::                             end users install nothing).
::   BUILD_EXE.bat cpu      -> fallback: install the prebuilt CPU-only wheel
::                             (no compiler/SDK needed). Use this only to build
::                             on a machine WITHOUT the Vulkan toolchain. The
::                             resulting exe never uses the GPU.
set "LLAMA_BACKEND=%~1"
if "%LLAMA_BACKEND%"=="" set "LLAMA_BACKEND=vulkan"

:: Prebuilt-wheel index for the CPU fallback path only.
set "LLAMA_CPU_INDEX=https://abetlen.github.io/llama-cpp-python/whl/cpu"
:: PyTorch CPU wheel index.
set "TORCH_CPU_INDEX=https://download.pytorch.org/whl/cpu"
:: Pinned llama-cpp-python version. The abetlen CPU index only publishes a
:: prebuilt Windows cp313 (Python 3.13) wheel for 0.3.2. Leaving the version
:: unpinned makes pip pull a newer build that is NOT a proper cp313 CPU wheel,
:: which crashes at model load with Windows Error 0xC000001D (illegal
:: instruction). Pin 0.3.2 so the build is reproducible and actually runs.
set "LLAMA_VERSION=0.3.2"

:: ==========================================================================
:: Pre-flight Check: Verify Python Version (via py launcher, not PATH)
:: ==========================================================================
echo [INFO] Checking Python version...

:: The py launcher lives in C:\Windows and is reachable even when the
:: 'python' command on PATH is a different version.
%PY% --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Python 3.13 was not found via the py launcher.
    echo This build script requires Python %REQUIRED_PYTHON_VERSION%.
    echo Tried: %PY%
    echo.
    echo Please install the correct version from:
    echo %PYTHON_DOWNLOAD_URL%
    echo.
    echo [NOTE] During installation, enable the py launcher option.
    goto :error
)

:: Capture the resolved version (e.g. "Python 3.13.12")
for /f "tokens=2 delims= " %%v in ('%PY% --version 2^>^&1') do set "CURRENT_PYTHON_VERSION=%%v"

echo [INFO] Current Python version: !CURRENT_PYTHON_VERSION!
echo [INFO] Required Python version: %REQUIRED_PYTHON_VERSION%

if not "!CURRENT_PYTHON_VERSION!"=="%REQUIRED_PYTHON_VERSION%" (
    echo.
    echo [ERROR] Incorrect Python version detected.
    echo This build script requires Python %REQUIRED_PYTHON_VERSION%.
    echo The py launcher resolved version !CURRENT_PYTHON_VERSION! instead.
    echo.
    echo Please install the correct version from:
    echo %PYTHON_DOWNLOAD_URL%
    echo.
    goto :error
)

:: ==========================================================================
:: Build Script for Aegis Synthesis Architecture
:: ==========================================================================
:: Creates a virtual environment, installs dependencies (using prebuilt
:: wheels for torch and llama-cpp-python so NO C/C++ compiler is required),
:: and builds the Aegis executable using the project's PyInstaller spec.
::
:: NOTE: Aegis is a large ML app. The build can take several minutes and the
:: output folder is large.
:: ==========================================================================
echo [INFO] Python version matches.

:: --------------------------------------------------------------------------
:: Vulkan toolchain pre-flight (only for the default vulkan backend). The CPU
:: fallback path needs none of this, so it is skipped when backend==cpu.
:: --------------------------------------------------------------------------
if /I "%LLAMA_BACKEND%"=="vulkan" (
    echo [INFO] Checking Vulkan build prerequisites...

    :: Vulkan SDK: the installer sets the VULKAN_SDK environment variable.
    if not defined VULKAN_SDK (
        echo.
        echo [ERROR] VULKAN_SDK is not set. The Vulkan SDK does not appear to be
        echo         installed, or you have not rebooted / opened a new shell since
        echo         installing it.
        echo         Install it from https://vulkan.lunarg.com/sdk/home and reboot,
        echo         or build the CPU-only exe instead:  BUILD_EXE.bat cpu
        goto :error
    )
    echo [INFO]   VULKAN_SDK = %VULKAN_SDK%

    :: CMake must be on PATH.
    cmake --version >nul 2>&1
    if errorlevel 1 (
        echo.
        echo [ERROR] cmake was not found on PATH. Install CMake from
        echo         https://cmake.org/download/ and choose 'Add CMake to the system
        echo         PATH' during setup, then reboot. Or build CPU-only: BUILD_EXE.bat cpu
        goto :error
    )

    :: A C/C++ compiler must be reachable. cl.exe ships with the MSVC 'Desktop
    :: development with C++' workload. It is normally only on PATH inside a
    :: 'Developer Command Prompt', so a bare 'cl' check can false-negative; we
    :: therefore only WARN if it is not directly visible, and let CMake locate
    :: the toolset itself (CMake finds MSVC via the registry/vswhere).
    where cl >nul 2>&1
    if errorlevel 1 (
        echo [WARN]  cl.exe not directly on PATH. This is normal outside a Developer
        echo         Command Prompt; CMake will try to locate MSVC automatically. If
        echo         the build fails to find a compiler, run this script from the
        echo         'x64 Native Tools Command Prompt for VS 2022', or install the
        echo         'Desktop development with C++' workload in the VS Build Tools.
    ) else (
        echo [INFO]   Found cl.exe on PATH.
    )
    echo [INFO] Vulkan prerequisites look OK.
)

echo [INFO] Starting build process...

:: 1. Create Virtual Environment
echo [STEP 1/7] Creating virtual environment in '.\venv'...

if not exist .\venv (
    %PY% -m venv .\venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        goto :error
    )
) else (
    echo [INFO] Virtual environment '.\venv' already exists. Skipping creation.
)

:: 2. Activate Virtual Environment
echo [STEP 2/7] Activating virtual environment...
call .\venv\Scripts\activate.bat

if not defined VIRTUAL_ENV (
    echo [ERROR] Failed to activate the virtual environment. Make sure '.\venv\Scripts\activate.bat' exists.
    goto :error
)

:: 3. Upgrade pip / setuptools / wheel
echo [STEP 3/7] Upgrading pip, setuptools, and wheel...
python -m pip install --upgrade pip wheel
python -m pip install "setuptools<82"
if errorlevel 1 (
    echo [ERROR] Failed to upgrade pip toolchain.
    goto :error
)

:: 4. Install PyTorch (CPU) from the official PyTorch wheel index.
echo [STEP 4/7] Installing PyTorch (CPU build)...
pip install --no-cache-dir torch --index-url %TORCH_CPU_INDEX%
if errorlevel 1 (
    echo [ERROR] Failed to install torch from the CPU wheel index.
    goto :error
)

:: 5. Install llama-cpp-python. Version is PINNED to %LLAMA_VERSION% on BOTH
::    paths on purpose: that is the exact version the rest of the app is written
::    and tested against (streaming API, create_chat_completion, chunk shapes,
::    cancellation machinery). Only the COMPILE differs for the GPU path; the
::    version does not change, so nothing else in the app has to change.
::    Dispatched via goto to avoid fragile nested parenthesized blocks in cmd.
if /I "%LLAMA_BACKEND%"=="cpu" goto :llama_cpu
goto :llama_vulkan

:llama_cpu
echo [STEP 5/7] Installing llama-cpp-python==%LLAMA_VERSION% (prebuilt CPU wheel)...
pip install --no-cache-dir "llama-cpp-python==%LLAMA_VERSION%" --only-binary :all: --extra-index-url %LLAMA_CPU_INDEX%
if errorlevel 1 (
    echo [ERROR] Failed to install the prebuilt llama-cpp-python==%LLAMA_VERSION% wheel.
    echo         The abetlen CPU index must have a cp313 win_amd64 wheel for this version.
    goto :error
)
goto :llama_done

:llama_vulkan
echo [STEP 5/7] Compiling llama-cpp-python==%LLAMA_VERSION% from source with Vulkan...
echo          (This is the slow step and needs the Vulkan SDK + CMake + MSVC C++ tools.)
:: --------------------------------------------------------------------------
:: This 0.3.2-era llama.cpp fails to compile against the newer Windows SDK
:: (26100) + MSVC 17.13+ because two of its C++ files (common/common.cpp and
:: common/log.cpp) use std::chrono without #include <chrono>; older SDKs
:: pulled it in transitively, the new one does not. See llama.cpp issue
:: #11834. A global force-include (/FIchrono) does not work here because this
:: codebase compiles .c and .cpp in the same targets, so the C++-only <chrono>
:: header leaks onto C files and trips STL1003. The robust, repeatable fix is
:: to add the missing #include to just those two C++ files, then build.
::
:: Because pip downloads fresh source each run, we do it in explicit steps:
::   1. download the pinned sdist, 2. unpack it, 3. append #include <chrono>
::   to the two files (idempotent), 4. pip install that patched local dir.
:: -DLLAVA_BUILD=OFF additionally skips the llava/clip vision example, which
:: this app does not use and which is the other thing that failed to build.
::
:: Everything runs inside a work dir under the build tree; %TEMP% is avoided
:: so paths stay short and predictable. The dir is cleaned first each run.
set "LCP_WORK=%CD%\_lcpb"
set "LCP_SDIST=%LCP_WORK%\llama_cpp_python-%LLAMA_VERSION%.tar.gz"
set "LCP_SRC=%LCP_WORK%\llama_cpp_python-%LLAMA_VERSION%"

if exist "%LCP_WORK%" rmdir /S /Q "%LCP_WORK%"
mkdir "%LCP_WORK%"

:: 5a. Download the exact pinned sdist from PyPI (curl ships with Windows 10+).
echo [INFO]   Downloading llama-cpp-python==%LLAMA_VERSION% source distribution...
curl -sL -o "%LCP_SDIST%" https://files.pythonhosted.org/packages/source/l/llama-cpp-python/llama_cpp_python-%LLAMA_VERSION%.tar.gz
if errorlevel 1 (
    echo [ERROR] Failed to download the llama-cpp-python source distribution.
    goto :error
)

:: 5b. Unpack it (tar ships with Windows 10+). Exclude vendor/.../spm-headers:
::     those 7 entries are SYMLINKS (used only for Swift Package Manager builds,
::     never on Windows) and Windows tar cannot create them, failing the whole
::     extract with "Invalid argument". The real headers they point to are
::     separate normal files in the archive, so skipping the symlink dir loses
::     nothing the Vulkan/Windows build needs.
echo [INFO]   Extracting source...
tar -xzf "%LCP_SDIST%" -C "%LCP_WORK%" --exclude="*/spm-headers/*" --exclude="*/spm-headers"
if errorlevel 1 (
    echo [ERROR] Failed to extract the llama-cpp-python source distribution.
    goto :error
)

:: 5c. Patch the two C++ files that are missing #include <chrono>. This calls
::     a small Python helper (scripts\patch_chrono.py) using the venv Python
::     that is already active here. Doing it in Python rather than a PowerShell
::     loop avoids spinning up PowerShell/.NET, reads and writes each file once,
::     and is idempotent (it skips a file that already has the include).
echo [INFO]   Patching common.cpp and log.cpp with #include ^<chrono^> ...
python "%~dp0scripts\patch_chrono.py" "%LCP_SRC%"
if errorlevel 1 (
    echo [ERROR] Failed to patch the C++ source files with the chrono include.
    goto :error
)

:: 5d. Build+install the PATCHED local source. -DGGML_VULKAN=on enables the
::     Vulkan backend; -DLLAVA_BUILD=OFF skips the unused vision example.
::     No /FIchrono. Installing from the local dir uses the patched files.
set "CMAKE_ARGS=-DGGML_VULKAN=on -DLLAVA_BUILD=OFF"
echo [INFO]   Compiling patched source (Vulkan, no llava). This is the slow part...
pip install --no-cache-dir --no-binary llama-cpp-python "%LCP_SRC%"
if errorlevel 1 (
    echo.
    echo [ERROR] The Vulkan build of llama-cpp-python failed to compile.
    echo         Common causes:
    echo           - Vulkan SDK / CMake / MSVC C++ tools not fully installed.
    echo           - Run from the "x64 Native Tools Command Prompt for VS 2022"
    echo             so the compiler is on PATH.
    echo         To build a working CPU-only exe instead, run:  BUILD_EXE.bat cpu
    goto :error
)

:: 5e. Clean up the work dir on success (leave it on failure for debugging).
rmdir /S /Q "%LCP_WORK%"
goto :llama_done

:llama_done

:: 6. Install the remaining dependencies from requirements.txt.
::    torch and llama-cpp-python are already satisfied above; pip will skip
::    them. --only-binary :all: forbids ANY source build: a package with no
::    cp313 wheel fails fast ("no matching distribution") instead of invoking
::    a C compiler (which is what caused the scikit-learn/numpy stdalign.h fail).
::    EXCEPTION: pygetwindow and pyrect are pure-Python and ship ONLY as
::    sdists (no wheel exists, any version). --no-binary pygetwindow,pyrect
::    lets just those two install from sdist (a plain .py copy, no compiler),
::    while every C-extension package still must be a prebuilt wheel.
echo [STEP 6/7] Installing remaining dependencies from requirements.txt...
pip install --no-cache-dir --only-binary :all: --no-binary pygetwindow,pyrect -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies from requirements.txt.
    goto :error
)

:: Ensure every src subpackage has an __init__.py so PyInstaller (and
:: Python) treat them as real packages. Missing on a fresh clone otherwise.
echo [INFO] Ensuring src package __init__.py files exist...
for %%P in (agent core internet learning memory mesh proactive secure services tools ui utils) do (
    if not exist "src\%%P\__init__.py" type nul > "src\%%P\__init__.py"
)
if not exist "src\__init__.py" type nul > "src\__init__.py"

:: Ensure runtime folders exist so the spec's datas=() collection succeeds
:: on a fresh checkout (the repo tracks these as empty via .gitkeep).
if not exist .\models mkdir .\models
if not exist .\data   mkdir .\data

:: The spec references aegis.ico for the executable icon. PyInstaller fails
:: with a confusing error if it is missing, so check for it up front.
if not exist aegis.ico (
    echo [ERROR] aegis.ico not found in the project root.
    echo         The build needs an icon file named aegis.ico next to assistant_gui.spec.
    goto :error
)

:: 7. Build with PyInstaller using the project spec.
echo [STEP 7/7] Building executable with PyInstaller (this may take a while)...
pyinstaller --clean --noconfirm assistant_gui.spec
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    goto :error
)

:: Place a user-editable config.yaml next to the built exe in .\dist so the
:: app loads it from beside the executable (see load_config in src/core/config.py).
echo [INFO] Copying config.yaml next to the executable in .\dist ...
copy /Y config.yaml dist\config.yaml >nul
if errorlevel 1 (
    echo [ERROR] Failed to copy config.yaml into .\dist.
    goto :error
)

echo.
echo [SUCCESS] Build completed successfully (llama backend: %LLAMA_BACKEND%).
echo The application can be found in the '.\dist' directory (run Aegis.exe).
echo.
echo [NOTE] On first launch Aegis downloads the model (~2GB) into '.\models'
echo        unless you placed a .gguf there before building.
goto :end

:error
echo.
echo [FAILURE] The build process failed. Please check the errors above.
echo.
pause
exit /b 1

:end
echo.
pause
endlocal
