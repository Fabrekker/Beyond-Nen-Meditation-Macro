# Beyond Nen Meditation Macro

A Windows macro for Beyond Nen meditation training on Roblox, created with AI assistance.

## What's new — v1.0.3

- Added **Shu** hold/release control and **En** letter prompts, alongside the **Ren/Ten** circle tab.
- Improved ring-timed click retries, full-screen capture, and automatic result reading with a manual fallback.
- Added recordable keybinds, hover help, a custom icon, and an in-app menu-first start reminder.
- Clarified Preview mode, quieted color updates, and improved error messages and input cancellation.

## Features

- **Ren/Ten:** color-aware circle detection, ring-timed clicks, and result-based timing adjustments toward **+0.04 or higher**.
- **Shu:** hold/release control to keep the indicator inside the target zone through focus resets.
- **En:** read letter prompts and tap the matching key; unclear prompts are skipped.
- Full-screen or custom capture, automatic result reading, and a manual result-area option.
- Configurable start/pause keybinds, live tracking, and optional **Preview mode** that sends no input. Starts paused with Preview mode off.
- Input stops on pause, tab changes, or loss of Roblox focus. GitHub updates preserve saved settings.

## Getting started

Requires **Windows and Python 3.12**. Open **Start Macro.cmd**, choose your training tab, and select the game area or **Use full screen**. Defaults: **F1** starts/pauses; **F2** pauses. Close the macro and run **Update Macro.cmd** to install published updates.

**Start without leaving meditation:** open the Roblox menu with **Esc**, press your configured start keybind while the menu is open, then close the menu to return to the minigame. Pressing the key directly during meditation can interrupt it.

**Set Roblox graphics to Manual, quality 1** to reduce visual clutter and improve detection. Keep the mouse unlocked for circle training.

Settings, captures, and diagnostic logs stay on your computer. Results vary; perfect scores are not guaranteed. En recognition has been replay-tested; live game input is still being validated.
