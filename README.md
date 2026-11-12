# Beyond Nen Meditation Macro

A Windows macro for Beyond Nen meditation training on Roblox.

> **IMPORTANT - Extract All before launching:** right-click the downloaded ZIP, choose **Extract All**, then run **Start Macro.exe** inside the extracted folder. Keep all files together. Running the launcher inside the ZIP causes the missing `bootstrap.py` error.

**[Download the macro ZIP](https://github.com/Fabrekker/Beyond-Nen-Meditation-Macro/releases/download/v1.1/nen-macro-1.1.zip)** - the same download works for new installs and updates.

## Windows security notice

> [!IMPORTANT]
> Windows may show **"Open File - Security Warning"** when opening the downloaded launcher. This is a standard downloaded-file prompt; by itself, it does not mean a virus was detected. [Learn more from Microsoft](https://support.microsoft.com/en-gb/windows/security/information-about-the-attachment-manager-in-microsoft-windows).
>
> Beyond Nen Meditation Macro is a community-made tool designed specifically for Beyond Nen training, with privacy in mind. Gameplay images are processed locally, and the macro does not request your Roblox login or upload images, settings, or logs. The source code is publicly available here if you'd like to review how it works.

## Features

- **Ren/Ten:** color-aware circle detection, smooth cursor travel, ring-timed clicks, and result-based timing adjustments toward **+0.04 or higher**.
- **Shu/Gyo/Zetsu:** hold/release control to keep the indicator inside the target zone until focus fills; choose left-click or Space.
- **En/Ken:** read letter prompts and tap the matching key; unclear prompts are skipped.
- **Ko/RyuS/RyuD:** hold the selected input and release it in the gold zone to finish each attempt; choose left-click or Space.
- Compact and full views, optional Always on top and light mode, numbered instructions, and saved window positions.
- Full-screen or custom minigame capture, automatic result reading, and a manual result-area option.
- Configurable start/pause keybinds and live tracking that continues while paused. Starts paused; the start key enables controls.
- Input stops on pause, tab changes, or loss of Roblox focus. GitHub updates preserve saved settings.

## What is new - 1.1

- Fixed errors when switching training modes.
- Added in-app Retry for tracking and reader errors, without restarting the macro. Controls stay paused during recovery.

## Getting started

> [!TIP]
> **Automatic downloads:** starting the macro automatically downloads and installs its required Python libraries. **Python itself must already be installed.**

The information below covers initial setup, general requirements, and manual download links in case they are needed.

1. On **64-bit Windows 10 or 11**, install **[Python 3.12 for Windows (64-bit)](https://www.python.org/downloads/release/python-31210/)**. Keep **pip**, **Tcl/Tk and IDLE**, and the **Python launcher** enabled in the installer. RapidOCR 1.4.4 requires Python below 3.13; use 3.12 for this macro.
2. Download **nen-macro-1.1.zip** from [Releases](https://github.com/Fabrekker/Beyond-Nen-Meditation-Macro/releases/latest). Right-click the ZIP and choose **Extract All**. **Do not run the launcher from inside the ZIP or copy it out on its own.** Keep both launchers beside the `App` folder; do not move individual files.
3. Open **Start Macro.exe**. Keep the **App** folder beside both launchers. The launcher opens the GUI directly; setup progress appears only when dependencies need installation. **Update Macro.exe** opens the graphical updater.
4. Choose your training group and select **Select minigame area** or **Full screen** in Settings. Configure your start/pause keys there; **F1** and **F2** are the defaults. Close the macro and open **Update Macro.exe** for published updates.

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
- **Python not found:** select your existing Python **3.12, 64-bit** `python.exe` when prompted, or install it using the link above.
- **DLL load failed:** install Microsoft's [Visual C++ x64 runtime](https://aka.ms/vc14/vc_redist.x64.exe), required by Windows ONNX Runtime builds ([installation guide](https://onnxruntime.ai/docs/install/)).
- **pip or dependency installation failed:** keep the terminal open and read the last error before pressing a key. Libraries install automatically; downloading their source ZIPs is unnecessary.

**Compact view:** use Tracking for the preview, Data for results and activity, Settings for capture and keybinds, and Instructions for your selected training. Use the **Full view** button for the expanded interface.

**Start without leaving meditation:** open the Roblox menu with **Esc**, press your configured start keybind while the menu is open, then close the menu to return to the minigame. Pressing the key directly during meditation can interrupt it.

**Ren/Ten visibility:** meditation aura and other effects can interfere with circle detection. **Aim your camera at a clearer area and set Roblox graphics to Manual, quality 1.** Keep the mouse unlocked and avoid moving it manually during circle training; manual movement cancels the current glide.

The `.pkg` and `update.json` release assets are used by the automatic updater. For a manual download, use **nen-macro-1.1.zip**. Existing installations retain their settings.
