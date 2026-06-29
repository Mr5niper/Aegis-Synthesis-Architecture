# Aegis Synthesis

<img width="250" height="250" alt="image" src="https://github.com/user-attachments/assets/777b0949-44b8-4943-bec2-f632390e57d9" />

A personal AI assistant that runs entirely on your own Windows PC. No cloud, no
account, no API keys. Your conversations and data stay on your machine.

There are two ways to use Aegis:

- **Just run the app:** download the release zip, extract it, and run the
  included `Aegis.exe`. No Python or developer tools needed. Start with
  "Running the app" below.
- **Build or run from source:** developers can build the executable or run from
  Python. See "Building from source" near the end.

## Features

- Local LLM: Llama 3.2 3B or Mistral 7B (GGUF), switchable at runtime.
- Private by design: conversations and data are stored locally on your PC.
- RAG knowledge base with semantic search, and a consent-based memory system
  that asks before saving facts about you.
- Web search on demand, limited to sites you allow in the settings file.
- Optional proactive suggestions and secure peer-to-peer collaboration
  (both off by default).
- Runs as a single Windows executable, or from source on Windows, macOS, or
  Linux.

---

# Running the app

This section is for running the prebuilt `Aegis.exe`. You do not need Python or
any developer tools.

## What is in the release zip

After you extract the release zip you get a folder containing:

- `Aegis.exe` - the application (a single file).
- `config.yaml` - a settings file that must stay next to `Aegis.exe`.
- `README.md` - this guide.

Keep `Aegis.exe` and `config.yaml` together in the same folder. They are already
side by side in the extracted folder; just leave them that way.

## Requirements

- Windows 10 or 11 (64-bit).
- 16 GB of RAM recommended. Aegis loads both of its AI models at startup, so
  8 GB will be tight.
- About 10 GB of free disk space. On first run the app downloads two AI models
  (about 6 GB total) plus a small text-processing model, and stores them next
  to the exe.
- An internet connection the first time you run it, to download the models.
  After that it works offline.

## Setup

1. Extract the zip. Right-click it and choose "Extract All", or use your usual
   unzip tool. Do not run `Aegis.exe` from inside the zip without extracting -
   it needs `config.yaml` next to it and room to create its folders.
2. Move the extracted folder somewhere you can write to, for example `C:\Aegis`.
   Avoid `C:\Program Files` and the Desktop; pick a normal folder.
3. That is it. There is nothing to install.

## Running it

Double-click `Aegis.exe`.

A black console window opens and stays open while Aegis runs - that is normal,
leave it open. After a few moments your web browser opens automatically to the
app at `http://127.0.0.1:7860`. If it does not open on its own, open your browser
and go to that address manually.

To quit, close the browser tab and then close the black console window.

### Windows SmartScreen warning

Because this is a small independent app and is not code-signed, Windows may show
a blue "Windows protected your PC" box the first time. If you trust the source of
this download, click **More info**, then **Run anyway**. This warning is normal
for unsigned software and usually does not appear again.

## First launch: what to expect

The very first run is the slow one. In order, it will:

1. Download both AI models - the default (about 2 GB) and the larger one
   (about 4 GB), roughly 6 GB in total. This can take a while depending on your
   internet speed. The console shows download progress.
2. Download a small text-processing model (a few seconds to a minute).
3. Load the models and open your browser to the app.

The models are saved into a `models` folder created next to `Aegis.exe`, so the
download only happens once. A `data` folder is also created next to the exe to
store your conversations and settings. Every later launch starts in well under a
minute (no downloads, just loading the models).

If nothing seems to happen for a while on first run, it is almost certainly the
model download in progress - watch the console window for activity.

## Using Aegis

- Type a message in the **Your Message** box and press Enter or click **Send**.
- The reply streams in as it is written. **Stop** cancels a reply in progress.
- **Clear** starts a new conversation. **Export** saves the conversation to a
  file.
- Rate replies with **Good**, **Bad**, or **Needs Correction** to help it
  improve over time.

Things to try:

- "Hello"
- "What is 23 * 456?"
- "What is the latest stable version of Python?" (it can search the web)
- "Remember that my favorite color is blue" (it asks before saving facts)

### Two models

Aegis comes with two AI models, both downloaded on first run, and you can switch
between them in the **Models** panel on the right:

- **default** (Llama 3.2 3B): faster, lighter, good for everyday use.
- **large** (Mistral 7B): more capable but heavier and slower, and uses more
  RAM.

Both models are already on disk after the first run, so switching does not
download anything.

## Changing settings

Open `config.yaml` (next to the exe) in any text editor like Notepad. It controls
things such as which web sites the assistant may visit, whether background
suggestions are on, and how many reasoning steps it takes. Save the file and
restart `Aegis.exe` for changes to take effect.

You do not need to touch this file to use Aegis; the defaults work out of the box.

## Privacy

Everything runs locally. The AI model runs on your CPU, your conversations are
stored only in the `data` folder on your PC, and nothing is sent to any company.
The only time Aegis reaches the internet on its own is:

- the one-time model download on first run, and
- web searches, but only when you ask a question that needs current information,
  and only to the sites allowed in `config.yaml`.

## Troubleshooting

**The black console window closed immediately.**
`config.yaml` is probably not next to `Aegis.exe`, or the folder is not writable.
Make sure both files are together in a normal folder (not Program Files), and try
again.

**The browser did not open.**
Open it yourself and go to `http://127.0.0.1:7860`. Make sure the console window
is still open.

**First run is stuck / taking forever.**
It is downloading the model. Watch the console window - if there is activity, let
it finish. A slow connection can make the first run take several minutes.

**It says it cannot download the model.**
Check your internet connection and try again. If your network blocks the
download, you can place the model file manually: create a `models` folder next to
`Aegis.exe` and put the `.gguf` file there (the exact file name and download link
are in `config.yaml`).

**Replies are slow.**
The model runs on your CPU, so speed depends on your hardware. Use the **default**
model rather than **large**, and close other heavy programs.

**Windows blocked it (SmartScreen).**
See the SmartScreen note above - More info, then Run anyway.

---

# Building from source

For developers who want to build the executable or run from Python. Full setup,
usage, and troubleshooting are in `docs/INSTALL.md`; the short version follows.

Requirements: Python 3.13 (pinned and tested against 3.13.12), and the same disk
and RAM as above.

## Run from source

```bash
git clone https://github.com/Mr5niper/Aegis-Synthesis-Architecture/ aegis-synthesis
cd aegis-synthesis

python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install "llama-cpp-python==0.3.2" --only-binary :all: --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
pip install -r requirements.txt

python -m src.main_gui
```

`torch` and `llama-cpp-python` are not listed in `requirements.txt`; they install
from their own CPU wheel indexes (see the comments in `requirements.txt`). The
first run downloads both models (about 6 GB total) into the `models` folder, then
opens your browser to `http://127.0.0.1:7860`.

## Build the Windows executable

```bat
BUILD_EXE.bat
```

This creates a clean virtual environment, installs the CPU wheels and pinned
requirements, and builds a single `Aegis.exe` into the `dist` folder with
`config.yaml` copied beside it. The models and data folders are not bundled; they
are created next to the executable on first run.

## Build on Linux or macOS

PyInstaller cannot cross-compile, so a Linux build must be made on Linux and a
macOS build on macOS. See `docs/BUILD_CROSS_PLATFORM.md` for the build script
(`build_executable.py` / `makefile`) and the per-platform notes. These paths are
provided but are not maintainer-tested.

## Documentation

- `docs/INSTALL.md` - full setup, first run, usage, and troubleshooting.
- `docs/BUILD_CROSS_PLATFORM.md` - Linux/macOS build path.
- `docs/CHANGELOG.md` - version history.
- `config.yaml` - configuration reference.

---

## A note on what this is

Aegis is an independent, locally-run assistant using small open models. It is not
as capable as large cloud AI services, and the smaller model can occasionally get
things wrong or phrase things oddly. Its strength is privacy and running entirely
on your own machine.
