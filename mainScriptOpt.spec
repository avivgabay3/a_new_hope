# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files


datas = [
    ("app_icon.png", "."),
    ("app_logo.png", "."),
    ("cursor.png", "."),
    ("conf_info.txt", "."),
]
datas += collect_data_files("customtkinter")

a = Analysis(
    ["finalGui.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=["cv2", "mss", "numpy", "pyaudio", "pyautogui", "pystray"],
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
    name="A_New_Hope",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["app_icon.png"],
)
