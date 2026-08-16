# A New Hope

A desktop screen and microphone recorder with a system-tray controller. The app records each
connected display to its own folder and safely finalizes the current file when recording stops
or the application quits.

## Run from source

Use Python 3.10 or newer. From this folder:

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python finalGui.py
```

On macOS or Linux, activate the environment with `source .venv/bin/activate`. PyAudio may require
PortAudio from the operating system package manager.

The first time recording starts, the operating system may ask for Screen Recording, Accessibility,
or Microphone permission. Grant the requested permission and restart the app if the operating
system asks you to do so.

## Operation

- **Start recording** creates one AVI recorder per connected display.
- Each video is finalized after the configured number of minutes, then the next segment begins.
- Closing the window hides it to the tray. Double-click the tray icon, or choose **Open A New Hope**,
  to bring it back.
- The tray menu can start or stop screen recording, open the recordings folder, or fully quit.
- **Quit application** stops the microphone and display workers and finalizes their current files.
- Settings are stored in the current user's application-data folder, so packaged builds do not try
  to write beside the executable.

The old `mainScript.py`, `mainScriptOpt.py`, `configScript.py`, and `micRecorder.py` names are retained
as compatibility launchers; all of them now open the same unified application.

## Test

```powershell
python -m unittest discover -s tests -v
```

## Build a Windows executable

```powershell
python -m pip install -r requirements-dev.txt
pyinstaller --clean mainScriptOpt.spec
```

The windowless executable is written to `dist/A_New_Hope.exe`. Build on Windows to produce a
Windows executable.
