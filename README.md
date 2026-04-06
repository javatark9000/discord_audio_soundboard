# Discord Audio Soundboard

Desktop soundboard for Windows that plays a selected audio file through a VB-Audio virtual microphone and automatically restores your previous microphone when playback stops.

## Features

- Modern desktop UI built with `customtkinter`
- Select a single audio file and play it into Discord
- Automatically switch the Windows default recording device to `CABLE Output`
- Automatically restore the previous microphone when playback finishes or you press `Stop`
- Volume control inside the app

## Requirements

- Windows 10 or Windows 11
- Python 3.11+ recommended
- Discord desktop app
- [VB-Audio Virtual Cable](https://vb-audio.com/Cable/)
- `ffmpeg` on `PATH` if you want MP3, AAC, or M4A support

## 1. Install VB-Cable

VB-Cable installs a signed audio driver, so this step must be done manually with administrator privileges.

1. Download VB-Cable from [VB-Audio Virtual Cable](https://vb-audio.com/Cable/).
2. Extract the archive.
3. Right-click `VBCABLE_Setup_x64.exe` and choose `Run as administrator`.
4. Finish the driver installation and reboot Windows if prompted.
5. After reboot, confirm that these devices exist in Windows:
   - `CABLE Input (VB-Audio Virtual Cable)` in playback devices
   - `CABLE Output (VB-Audio Virtual Cable)` in recording devices

## 2. Configure Discord

Discord must use the Windows default microphone for the automatic switching to work.

1. Open Discord.
2. Go to `User Settings` -> `Voice & Video`.
3. Set `Input Device` to `Default`.
4. Keep `Input Mode` and other options as you prefer.

If Discord is locked to a specific microphone instead of `Default`, the app will change the Windows default device but Discord will keep listening to the old mic.

## 3. Install Python Dependencies

From the project folder:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 4. Install ffmpeg

`soundfile` already supports WAV, FLAC, and OGG. For MP3, AAC, and M4A, install `ffmpeg`.

### Option A: Install with winget

```powershell
winget install Gyan.FFmpeg
```

### Option B: Manual install

1. Download FFmpeg from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/).
2. Extract it to a folder such as `C:\ffmpeg`.
3. Add the `bin` folder to your Windows `PATH`.
4. Open a new terminal and verify:

```powershell
ffmpeg -version
```

## 5. Run the App

```powershell
.venv\Scripts\Activate.ps1
python main.py
```

## How It Works

1. You select an audio file.
2. The app stores your current default recording devices.
3. The app changes the default recording device to `CABLE Output`.
4. The app plays the selected file to `CABLE Input`.
5. Discord receives the virtual cable as microphone input.
6. When playback ends, the app restores your previous microphone.

## Supported Audio Formats

- Native support: `.wav`, `.flac`, `.ogg`
- Requires `ffmpeg`: `.mp3`, `.aac`, `.m4a`, and most other compressed formats

## Troubleshooting

### VB-Cable not found

- Reinstall VB-Cable as administrator
- Check that the devices are enabled in Windows Sound settings
- Restart Discord after installing the driver

### Discord does not switch microphones

- Make sure Discord `Input Device` is set to `Default`
- Close and reopen Discord if it was running during VB-Cable installation
- Confirm Windows really changed to `CABLE Output` in Sound settings

### Audio file fails to load

- Install `ffmpeg`
- Try a `.wav` file first to verify the rest of the pipeline works

### Playback works but no one hears it in Discord

- Verify `CABLE Input` exists as a playback device
- Verify `CABLE Output` exists as a recording device
- Check Discord input sensitivity and noise suppression settings
- Test the signal in `Windows Sound Settings` before using Discord
