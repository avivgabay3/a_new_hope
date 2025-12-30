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
Use the included PyInstaller spec to build a portable executable:
```bash
python -m PyInstaller mainApp.spec
```
The build output goes to `dist/mainApp/`, which you can copy to another PC. See `save_as_exe.txt` for detailed instructions.
