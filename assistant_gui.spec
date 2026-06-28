# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# Bundle every module under the `src` package. This guarantees lazily- or
# dynamically-imported submodules (e.g. tools loaded by name) are included.
src_submodules = collect_submodules('src')

a = Analysis(
    ['aegis_launcher.py'],
    pathex=['.'],
    binaries=[],
    datas=[('models','models'),('data','data'),('config.yaml','.')],
    hiddenimports=[
        'sentence_transformers','torch','transformers','scipy','sklearn',
        'duckduckgo_search','bs4','pydantic.v1','yaml','gradio','fastapi','uvicorn',
        'websockets','nacl','nacl.public','nacl.signing','nacl.bindings',
        'pyperclip','pygetwindow','pyrect',
        'anyio', 'starlette', 'nacl.utils',
        'sniffio',
    ] + src_submodules,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
# UPX disabled: it frequently corrupts large native DLLs (torch, llama_cpp,
# CUDA) and produces executables that crash on launch. Matches the --noupx
# choice used in the WindowsAudioControl build.
exe = EXE(pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [], name='Aegis', console=True, upx=False)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=False, name='Aegis')
