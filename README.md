# OpenReader

OpenReader lets you select text in any Windows app and read it aloud with a synced floating highlight overlay.

## Features

- Global `Ctrl+Alt` hotkey to read selected text.
- Press `Ctrl+Alt` again to stop reading.
- Local offline text-to-speech through Windows SAPI.
- Optional OpenRouter cloud text-to-speech.
- Floating overlay that shows the current spoken line.

## Requirements

- Windows 10 or 11.
- Python 3.13 or newer.
- Admin/elevated terminal access for the global hotkey library.

## Install

Using `uv`:

```powershell
uv sync
```

Or using `pip`:

```powershell
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
```

## Configure

Copy the example config:

```powershell
Copy-Item example.config.json config.json
```

Default local mode:

```json
{
  "engine": "local",
  "openrouter_api_key": "",
  "openrouter_voice": "flux-haley-en"
}
```

For OpenRouter mode, set `"engine"` to `"openrouter"` and add your API key. Keep `config.json` private.

## Run

From an elevated/admin terminal:

```powershell
uv run python openreder.py
```

Or:

```powershell
.\.venv\Scripts\python.exe openreder.py
```

## Use

1. Select text in another app.
2. Press `Ctrl+Alt`.
3. Listen while the overlay highlights the current line.
4. Press `Ctrl+Alt` again to stop.

## Troubleshooting

- If the hotkey does nothing, run the terminal as administrator.
- If no text is read, check that the selected app allows copying with `Ctrl+C`.
- If OpenRouter audio does not work, check `config.json` and your API key.
- Long selections may take longer in OpenRouter mode because audio is generated over the network.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).


