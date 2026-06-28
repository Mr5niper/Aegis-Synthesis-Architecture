@echo off
setlocal enabledelayedexpansion

:: ==========================================================================
:: Configuration
:: ==========================================================================
set "REQUIRED_PYTHON_VERSION=3.13.12"
set "PYTHON_DOWNLOAD_URL=https://www.python.org/downloads/release/python-31312/"
set "PY=py -3.13"

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
:: Creates a virtual environment, installs dependencies, and builds the
:: Aegis executable using the existing PyInstaller spec (assistant_gui.spec).
::
:: NOTE: Aegis is a large ML app (torch, sentence-transformers, gradio).
:: The build can take several minutes and the output folder is large.
:: ==========================================================================
echo [INFO] Python version matches. Starting build process...

:: 1. Create Virtual Environment
echo [STEP 1/5] Creating virtual environment in '.\venv'...

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
echo [STEP 2/5] Activating virtual environment...
call .\venv\Scripts\activate.bat

if not defined VIRTUAL_ENV (
    echo [ERROR] Failed to activate the virtual environment. Make sure '.\venv\Scripts\activate.bat' exists.
    goto :error
)

:: 3. Install Dependencies
echo [STEP 3/5] Upgrading pip and installing dependencies from requirements.txt...
python -m pip install --upgrade pip > nul
if errorlevel 1 (
    echo [ERROR] Failed to upgrade pip.
    goto :error
)

pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies from requirements.txt.
    goto :error
)

:: 4. Ensure runtime folders exist so the spec's datas=() collection succeeds.
::    (PyInstaller's spec bundles 'models' and 'data'; create them if missing
::    so the build does not fail on a fresh checkout.)
echo [STEP 4/5] Ensuring 'models' and 'data' folders exist...
if not exist .\models mkdir .\models
if not exist .\data mkdir .\data

:: 5. Build with PyInstaller using the project spec.
::    The spec (assistant_gui.spec) already lists the hidden imports, datas,
::    and COLLECT settings, so we invoke it directly rather than passing flags.
echo [STEP 5/5] Building executable with PyInstaller (this may take a while)...
pyinstaller --clean --noconfirm assistant_gui.spec
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    goto :error
)

echo.
echo [SUCCESS] Build completed successfully.
echo The application can be found in the '.\dist\Aegis' directory (run Aegis.exe).
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
