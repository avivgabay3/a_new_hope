# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_dynamic_libs

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

binaries = collect_dynamic_libs("cv2")
datas = [(str(project_root / name), ".") for name in resource_names if (project_root / name).exists()]


a = Analysis(
    ['mainApp.py'],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=['cv2', 'numpy', 'watchdog', 'mss', 'customtkinter', 'pyautogui'],
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
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_root / "app_icon.ico") if (project_root / "app_icon.ico").exists() else None,
)
