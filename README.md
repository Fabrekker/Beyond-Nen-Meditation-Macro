# Beyond Nen Meditation Macro

A Windows macro for Beyond Nen meditation training on Roblox, created with AI assistance.

> **IMPORTANT — Extract All before launching:** right-click the downloaded ZIP, choose **Extract All**, then run **Start Macro.cmd** inside the extracted folder. Keep all files together. Running the launcher inside the ZIP causes the missing `bootstrap.py` error.

**[Download the macro ZIP](https://github.com/Fabrekker/Beyond-Nen-Meditation-Macro/releases/download/v1.0.5/nen-macro-1.0.5-update.zip)** — the same download works for new installs and updates.

## What's new — v1.0.5

- Added smooth cursor travel to Ren/Ten circles with steadier target tracking and ring-timed clicks.
- Reduced capture-related cursor flicker and added live Roblox window capture while the macro panel is in front.
- Removed Preview mode; live tracking continues while paused, with simpler Running/Paused controls.
- Added Ren/Ten guidance for aura effects: aim the camera at a clearer area and use graphics quality 1.

## Features

- **Ren/Ten:** color-aware circle detection, smooth cursor travel, ring-timed clicks, and result-based timing adjustments toward **+0.04 or higher**.
- **Shu:** hold/release control to keep the indicator inside the target zone through focus resets.
- **En:** read letter prompts and tap the matching key; unclear prompts are skipped.
- Full-screen or custom capture, automatic result reading, and a manual result-area option.
- Configurable start/pause keybinds and live tracking that continues while paused. Starts paused; the start key enables controls.
- Input stops on pause, tab changes, or loss of Roblox focus. GitHub updates preserve saved settings.

## Getting started

1. On **64-bit Windows 10 or 11**, install **[Python 3.12 for Windows (64-bit)](https://www.python.org/downloads/release/python-31210/)**. Keep **pip**, **Tcl/Tk and IDLE**, and the **Python launcher** enabled in the installer. RapidOCR 1.4.4 requires Python below 3.13; use 3.12 for this macro.
2. Download **nen-macro-1.0.5-update.zip** from [Releases](https://github.com/Fabrekker/Beyond-Nen-Meditation-Macro/releases/latest). Right-click the ZIP and choose **Extract All**. **Do not run the launcher from inside the ZIP or copy it out on its own.** Keep `Start Macro.cmd`, `bootstrap.py`, and the other extracted files together.
3. Open **Start Macro.cmd** in that extracted folder. Stay connected to the internet and leave the window open while the launcher installs the Python dependencies automatically.
4. Choose your training tab and game capture area. **F1** starts/pauses and **F2** pauses by default. Close the macro and run **Update Macro.cmd** for published updates.

**Other manual download, if needed:** [Microsoft Visual C++ Redistributable (x64)](https://aka.ms/vc14/vc_redist.x64.exe). Install it if dependency loading reports a missing DLL. See Microsoft's [official download information](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist/).

### What gets installed automatically?

These are Python libraries, not separate apps you need to download manually. The launcher installs the libraries listed in your version's `requirements.txt`:

| Library | Purpose | Official source |
| --- | --- | --- |
| MSS | Captures the game area on screen | [MSS documentation](https://python-mss.readthedocs.io/stable/) |
| Windows Capture | Captures the Roblox window for the live preview | [Windows Capture](https://pypi.org/project/windows-capture/2.0.0/) |
| OpenCV | Detects circles, rings, and bars | [OpenCV Python](https://pypi.org/project/opencv-python/) |
| RapidOCR / ONNX Runtime | Reads key prompts and score text | [RapidOCR 1.4.4](https://pypi.org/project/rapidocr-onnxruntime/1.4.4/), [ONNX Runtime](https://onnxruntime.ai/docs/install/) |
| Pillow / NumPy | Displays the preview and processes image pixels | [Pillow](https://pypi.org/project/pillow/), [NumPy](https://pypi.org/project/numpy/) |

### If it does not open

- **Cannot open `bootstrap.py` / No such file or directory:** extract the entire release ZIP first and launch from the extracted folder.
- **Python not found / requested Python version not installed:** install Python **3.12, 64-bit**, with the Python launcher enabled.
- **DLL load failed:** install Microsoft's [Visual C++ x64 runtime](https://aka.ms/vc14/vc_redist.x64.exe), required by Windows ONNX Runtime builds ([installation guide](https://onnxruntime.ai/docs/install/)).
- **pip or dependency installation failed:** keep the terminal open and read the last error before pressing a key. Libraries install automatically; downloading their source ZIPs is unnecessary.

**Start without leaving meditation:** open the Roblox menu with **Esc**, press your configured start keybind while the menu is open, then close the menu to return to the minigame. Pressing the key directly during meditation can interrupt it.

**Ren/Ten visibility:** meditation aura and other effects can interfere with circle detection. **Aim your camera at a clearer area and set Roblox graphics to Manual, quality 1.** Keep the mouse unlocked and avoid moving it manually during circle training; manual movement cancels the current glide.

Window capture needs Roblox restored rather than minimized. If window capture is unavailable, the app falls back to desktop capture; keep Roblox visible.

Settings, captures, and diagnostic logs stay on your computer. Results vary; perfect scores are not guaranteed. En recognition has been replay-tested; live game input is still being validated.
