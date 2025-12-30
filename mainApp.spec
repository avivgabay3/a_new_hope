# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_all

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

binaries = collect_dynamic_libs("cv2") + collect_dynamic_libs("numpy") + ctk_binaries
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
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
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
