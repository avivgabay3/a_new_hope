# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_all
import customtkinter as ctk

# PyInstaller executes the spec via exec(), so __file__ may be undefined.
# Use sys.argv[0] (the spec file path) to locate the project root reliably.
spec_path = Path(sys.argv[0]).resolve()
project_root = spec_path.parent

# Bundle resources so resource_path can find them when frozen
resource_names = [
    "conf_info.txt",
    "cursor.png",
    "red.json",
    "app_icon.png",
    "app_logo.png",
]

ctk_data, ctk_binaries, ctk_hiddenimports = collect_all("customtkinter")

# Explicitly bundle the CustomTkinter package directory so all JSON/OTF assets
# are available in the onedir layout (mirrors `--add-data <ctk_path>;customtkinter/`).
ctk_path = Path(ctk.__file__).resolve().parent
ctk_data.append((str(ctk_path), "customtkinter"))

# Make sure the Python DLL ships with the onedir build so the EXE can start
# even on machines without Python installed. PyInstaller usually grabs this
# automatically, but we add it explicitly to avoid "Failed to load Python DLL"
# errors seen on some systems.
python_dll_name = f"python{sys.version_info.major}{sys.version_info.minor}.dll"
python_dll_candidates = [
    Path(sys.executable).with_name(python_dll_name),
    Path(sys.base_prefix) / python_dll_name,
    Path(sys.exec_prefix) / python_dll_name,
]

python_dll_entries = [
    (str(path), "_internal") for path in python_dll_candidates if path.exists()
]

binaries = (
    collect_dynamic_libs("cv2")
    + collect_dynamic_libs("numpy")
    + ctk_binaries
    + python_dll_entries
)
datas = [(str(project_root / name), ".") for name in resource_names if (project_root / name).exists()] + ctk_data


a = Analysis(
    ['mainApp.py'],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=['cv2', 'numpy', 'watchdog', 'mss', 'customtkinter', 'pyautogui'] + ctk_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    # Keep binaries loose in the onedir folder (no archive) to avoid runtime
    # extraction failures for large DLLs (e.g., cv2, Pillow, numpy/scipy).
    noarchive=True,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    [],
    [],
    name='mainApp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[
        # Disable UPX for all binaries to avoid decompression failures (e.g., PIL _imaging)
    ],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_root / "app_icon.ico") if (project_root / "app_icon.ico").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='mainApp',
)
