@echo off
setlocal enabledelayedexpansion

:: ==========================================================================
:: Configuration
:: ==========================================================================
set "REQUIRED_PYTHON_VERSION=3.13.12"
set "PYTHON_DOWNLOAD_URL=https://www.python.org/downloads/release/python-31312/"
set "PY=py -3.13"

:: Prebuilt-wheel index for llama-cpp-python (CPU). Avoids needing a C/C++
:: compiler (MSVC + CMake) to build the package from source.
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
echo [INFO] Python version matches. Starting build process...

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

:: 5. Install llama-cpp-python: PINNED prebuilt CPU wheel.
::    --only-binary :all: forbids a from-source build (no MSVC/CMake needed).
::    Version pinned to %LLAMA_VERSION% because that is the version the abetlen
::    CPU index publishes a Windows cp313 wheel for; newer versions resolve to a
::    non-cp313 build that crashes at model load (Windows Error 0xC000001D).
echo [STEP 5/7] Installing llama-cpp-python==%LLAMA_VERSION% (prebuilt CPU wheel)...
pip install --no-cache-dir "llama-cpp-python==%LLAMA_VERSION%" --only-binary :all: --extra-index-url %LLAMA_CPU_INDEX%
if errorlevel 1 (
    echo [ERROR] Failed to install the prebuilt llama-cpp-python==%LLAMA_VERSION% wheel.
    echo         The abetlen CPU index must have a cp313 win_amd64 wheel for this version.
    goto :error
)

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
echo [SUCCESS] Build completed successfully.
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
