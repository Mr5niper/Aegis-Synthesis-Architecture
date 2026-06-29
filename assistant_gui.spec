# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import (
    collect_submodules,
    collect_dynamic_libs,
    collect_data_files,
    collect_all,
)

block_cipher = None

# --- src package ----------------------------------------------------------
# Bundle every module under the `src` package so lazily-/dynamically-imported
# submodules (e.g. tools loaded by name) are included.
src_submodules = collect_submodules('src')

# --- llama-cpp-python native libraries ------------------------------------
# Ships compiled DLLs (llama.dll, ggml*.dll, mtmd.dll) in llama_cpp/lib and
# loads them at import via os.add_dll_directory(<pkg>/llama_cpp/lib).
# Without collecting them: FileNotFoundError [WinError 3] ... llama_cpp\lib
llama_binaries = collect_dynamic_libs('llama_cpp')
llama_datas = collect_data_files('llama_cpp')

# --- gradio + friends: collect EVERYTHING ---------------------------------
# gradio and its helper packages read non-code data files at import time
# (e.g. safehttpx/version.txt, gradio/package.json, gradio/templates,
#  gradio_client/types.json, groovy data). collect_all() gathers each
# package's datas + binaries + hidden submodules so the frozen app finds them.
# NOTE: 'models' and 'data' are intentionally NOT bundled. They are large,
# runtime-managed folders (models are downloaded on first launch into the
# 'models' folder beside the exe; 'data' is user data written at runtime).
# Bundling them copied ~6GB into every build for no benefit, since the app
# reads/writes them next to the executable. BUILD_EXE.bat creates empty
# 'models' and 'data' folders and copies config.yaml beside the exe.
datas = [('config.yaml','.')] + llama_datas
binaries = list(llama_binaries)
hiddenimports = [
    'sentence_transformers','torch','transformers','scipy','sklearn',
    'duckduckgo_search','bs4','pydantic.v1','yaml','gradio','fastapi','uvicorn',
    'websockets','nacl','nacl.public','nacl.signing','nacl.bindings',
    'pyperclip','pygetwindow','pyrect',
    'anyio','starlette','nacl.utils','sniffio','llama_cpp',
] + src_submodules

for _pkg in ('gradio', 'gradio_client', 'safehttpx', 'groovy'):
    _d, _b, _h = collect_all(_pkg)
    datas += _d
    binaries += _b
    hiddenimports += _h

a = Analysis(
    ['aegis_launcher.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False
)

# gradio uses lazy imports that PyInstaller can mis-handle when modules are
# frozen into the PYZ archive. Forcing gradio to be collected as plain source
# files avoids "module not found"/data-path errors at runtime.
try:
    a.set_module_collection_mode('gradio', 'py')
    a.set_module_collection_mode('gradio_client', 'py')
except Exception:
    pass

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
# UPX disabled: it can corrupt large native DLLs (torch, llama_cpp) -> launch crash.
exe = EXE(pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [], name='Aegis', console=True, upx=False)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=False, name='Aegis')
