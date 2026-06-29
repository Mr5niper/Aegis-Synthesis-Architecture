# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import (
    collect_submodules,
    collect_dynamic_libs,
    collect_data_files,
    collect_all,
)

block_cipher = None

# --- version info --------------------------------------------------------
# Read the single source of truth (src/__version__.py) at build time and
# build the Windows version resource from it, so the exe's right-click
# Properties -> Details tab always matches __version__ with nothing to keep
# in sync by hand. __version__ is a dotted string like "1.1.0.0".
import re

def _read_version():
    text = open('src/__version__.py', 'r', encoding='utf-8').read()
    ver = re.search(r'__version__\s*=\s*[\'"]([^\'"]+)[\'"]', text).group(1)
    code = re.search(r'__codename__\s*=\s*[\'"]([^\'"]+)[\'"]', text)
    codename = code.group(1) if code else ''
    # Pad/truncate the dotted version to exactly 4 integers for the tuple.
    nums = [int(x) for x in re.findall(r'\d+', ver)][:4]
    while len(nums) < 4:
        nums.append(0)
    return ver, codename, tuple(nums)

_ver_str, _codename, _ver_tuple = _read_version()

# Build the version resource. The win32 versioninfo module needs Windows-only
# deps; on the Windows build host they are present. Guard it so that on any
# other platform (or if the import is unavailable) the build still succeeds,
# just without embedded version metadata.
try:
    from PyInstaller.utils.win32.versioninfo import (
        VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable,
        StringStruct, VarFileInfo, VarStruct,
    )
    version_resource = VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=_ver_tuple,
            prodvers=_ver_tuple,
            mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0),
        ),
        kids=[
            StringFileInfo([StringTable('040904B0', [
                StringStruct('CompanyName', 'David Johnson'),
                StringStruct('FileDescription', 'Aegis Synthesis - local-first AI assistant'),
                StringStruct('FileVersion', _ver_str),
                StringStruct('InternalName', 'Aegis'),
                StringStruct('LegalCopyright', 'Copyright (c) 2026 David Johnson'),
                StringStruct('OriginalFilename', 'Aegis.exe'),
                StringStruct('ProductName', 'Aegis Synthesis'),
                StringStruct('ProductVersion', _ver_str),
                StringStruct('Comments', _codename),
            ])]),
            VarFileInfo([VarStruct('Translation', [1033, 1200])]),
        ],
    )
except Exception as _e:
    print('WARNING: could not build version resource (%s); building without it.' % _e)
    version_resource = None

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
# Single-file build: all binaries, zipped modules, and data files are folded
# into the one EXE() call below, so the output is just dist/Aegis.exe with no
# accompanying dist/Aegis/ folder. (Previously a COLLECT step also produced a
# one-folder build; that has been removed.)
#
# version=  embeds the Windows version resource built above from
#           src/__version__.py, so right-click Properties -> Details shows it.
# icon=     sets the executable's icon. Provide aegis.ico in the repo root.
# UPX disabled: it can corrupt large native DLLs (torch, llama_cpp) -> launch crash.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Aegis',
    console=True,
    upx=False,
    version=version_resource,
    icon='aegis.ico',
)
