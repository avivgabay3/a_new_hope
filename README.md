# a_new_hope / ScanOT2

This repository contains the ScanOT2 screen recording app. The dynamic, copy-ready entry point is `mainApp.py`, which uses relative resource lookup so it works both in development and inside the PyInstaller-built EXE without machine-specific paths.

## Getting the latest code
1. Ensure you are on the `work` branch (the branch used in this repo). Run:
   ```bash
   git checkout work
   git pull
   ```
2. Confirm you have the dynamic `mainApp.py` by opening the file and looking for the top-of-file note describing it as a "Fully self-contained" copy-ready version.

## Install runtime dependencies
Before running the script or building the EXE, install the required packages:
```bash
pip install customtkinter pillow pystray pyautogui mss watchdog tqdm opencv-python numpy
```
If you plan to build the EXE, also install PyInstaller:
```bash
pip install pyinstaller
```

## Building the EXE
Use the included PyInstaller spec to build a portable **folder**-style executable. UPX compression is disabled in the spec to
avoid Pillow extraction errors (e.g., `Failed to extract PIL_imaging...`), and the build keeps binaries loose in the one-folder
layout (no archives) to avoid runtime extraction errors with large numpy/OpenCV/Pillow DLLs. The spec also ships the matching
`pythonXY.dll` into the `_internal` subfolder so the EXE can start on machines without Python installed:
```bash
python -m PyInstaller mainApp.spec
```
The build output goes to `dist/mainApp/`, which you can copy to another PC. Run `dist/mainApp/mainApp.exe` directly from that
folder. See `save_as_exe.txt` for detailed instructions.

## Troubleshooting the EXE
- A `mainApp.log` file is written next to `mainApp.exe` on startup to capture any hidden errors (helpful because the EXE runs without a console window).
- The writable `conf_info.txt` also lives next to the EXE. If it is missing or corrupted, delete it and restart the app to recreate it from the bundled template.
- If recording does not start, open `mainApp.log` and look for "VideoWriter failed to open". This usually means the save path is not writable or the OpenCV FFmpeg DLLs were not bundled. Rebuild with the provided `mainApp.spec` (which now collects the OpenCV dynamic libraries), and ensure you launch the EXE from a folder you can write to.
- If the EXE reports a missing `customtkinter` even though it is installed, open `mainApp.log` to see the full import error. Rebuild using `mainApp.spec` (which now bundles the CustomTkinter data files and hidden imports) and run the app from the `dist/mainApp/` folder so the bundled assets are discovered.
- If you see `Failed to load Python DLL ... python313.dll`, rebuild with the provided `mainApp.spec` (it explicitly bundles the `pythonXY.dll` into `_internal/`) and run the app from the `dist/mainApp/` folder so the DLL is discovered.
