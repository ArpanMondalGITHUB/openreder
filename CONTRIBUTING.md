# Contributing

Thanks for helping improve OpenReader. Keep changes small, focused, and easy to test.

## Setup

1. Install Python 3.13 and `uv`.
2. Install dependencies:

   ```powershell
   uv sync
   ```

3. Create your local config:

   ```powershell
   Copy-Item example.config.json config.json
   ```

4. Edit `config.json` if you want to use OpenRouter. Do not commit `config.json`.

## Running

Run from an elevated/admin terminal on Windows:

```powershell
uv run python openreder.py or .venv/Scripts/python.exe openreder.py
```

The app is Windows-focused because it uses global hotkeys, Windows UI Automation, and SAPI text-to-speech.

## Before Sending A Change

Run the smallest useful check:

```powershell
uv run python -m py_compile openreder.py
```

Then manually try the main flow:

1. Select text in any app you want.
2. Press `Ctrl+Alt`.
3. Confirm speech starts and the overlay appears.
4. Press `Ctrl+Alt` again and confirm speech stops.

## Pull Requests

- Describe the user-visible change.
- Mention whether you tested local TTS, OpenRouter TTS, or both.
- Keep credentials, generated audio files, virtual environments, and personal config out of commits.
- Prefer fixing one thing per pull request.

