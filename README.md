# a_new_hope / ScanOT2

This repository contains the ScanOT2 screen recording app. The dynamic, copy-ready entry point is `mainApp.py`, which uses relative resource lookup so it works both in development and inside the PyInstaller-built EXE without machine-specific paths.

## Getting the latest code
1. Ensure you are on the `work` branch (the branch used in this repo). Run:
   ```bash
   git checkout work
   git pull
   ```
2. Confirm you have the dynamic `mainApp.py` by opening the file and looking for the top-of-file note describing it as a "Fully self-contained" copy-ready version.

## Building the EXE
Use the included PyInstaller spec to build a portable executable. UPX compression is disabled in the spec to avoid Pillow
extraction errors (e.g., `Failed to extract PIL_imaging...`):
```bash
python -m PyInstaller mainApp.spec
```
The build output goes to `dist/mainApp/`, which you can copy to another PC. See `save_as_exe.txt` for detailed instructions.

## Troubleshooting the EXE
- A `mainApp.log` file is written next to `mainApp.exe` on startup to capture any hidden errors (helpful because the EXE runs without a console window).
- The writable `conf_info.txt` also lives next to the EXE. If it is missing or corrupted, delete it and restart the app to recreate it from the bundled template.
- If recording does not start, open `mainApp.log` and look for "VideoWriter failed to open". This usually means the save path is not writable or the OpenCV FFmpeg DLLs were not bundled. Rebuild with the provided `mainApp.spec` (which now collects the OpenCV dynamic libraries), and ensure you launch the EXE from a folder you can write to.
