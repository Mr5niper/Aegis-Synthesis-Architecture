# AEGIS SYNTHESIS - SETUP AND USER GUIDE

Aegis Synthesis is a sovereign, privacy-first AI assistant that runs entirely on your computer. This guide covers setup, first run, and usage.

---

## Table of Contents
1. System Requirements
2. Installation
3. Building a Standalone Executable
4. First Run
5. Using Aegis
6. Troubleshooting
7. Advanced Features

---

## 1. System Requirements

### Minimum
- OS: Windows 10/11, macOS 10.15+, or Linux. The build script and prebuilt executable target Windows.
- CPU: 4+ cores recommended.
- RAM: 8 GB minimum (16 GB recommended).
- Disk: about 15 GB free (roughly 6 GB of models plus dependencies).
- Python: 3.13. The build is pinned and tested against 3.13.12.

### Recommended
- RAM: 16 GB or more for the large model.
- SSD for faster model loading.

---

## 2. Installation

### Step 1: Install Python 3.13

This project is pinned to Python 3.13 and relies on prebuilt 3.13 (cp313) wheels. Use 3.13, not an older or newer minor version.

Windows:
1. Download Python 3.13 from python.org.
2. During installation, enable "Add Python to PATH" and the py launcher.
3. Verify in PowerShell:
   ```powershell
   py -3.13 --version
   # Should show: Python 3.13.x
   ```

macOS:
```bash
brew install python@3.13
```

Linux:
```bash
sudo apt update
sudo apt install python3.13 python3.13-venv python3.13-dev
```

### Step 2: Get the Project

Clone the repository or unpack the ZIP, then open a terminal in the project directory.

Windows PowerShell:
```powershell
cd "C:\path\to\Aegis-Synthesis-Architecture"
```

macOS/Linux:
```bash
cd ~/path/to/Aegis-Synthesis-Architecture
```

The package __init__.py files are part of the repository, so no manual file creation is required. The models and data folders are created automatically at runtime; you do not need to create them by hand.

### Step 3: Create a Virtual Environment

Windows:
```powershell
py -3.13 -m venv venv
venv\Scripts\activate
```

macOS/Linux:
```bash
python3 -m venv venv
source venv/bin/activate
```

Your prompt should now begin with (venv).

### Step 4: Install Dependencies

All dependencies are pinned to versions that publish prebuilt Python 3.13 wheels, so nothing compiles from source. Install torch and llama-cpp-python from their CPU wheel indexes first, then the pinned requirements.

All platforms:
```bash
python -m pip install --upgrade pip wheel
python -m pip install "setuptools<82"

pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install "llama-cpp-python==0.3.2" --only-binary :all: --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu

pip install -r requirements.txt
```

Notes:
- torch and llama-cpp-python are intentionally not listed in requirements.txt. They come from the CPU wheel indexes above. See the comments in requirements.txt.
- llama-cpp-python is pinned to 0.3.2 because that is the only version with a Windows cp313 CPU wheel on the abetlen index. Newer versions crash at model load.
- On Windows, clipboard and window context use pygetwindow, which is already in requirements.txt.

Verify the install:
```bash
python -c "import torch, gradio, llama_cpp, sentence_transformers; print('dependencies OK')"
```

---

## 3. Building a Standalone Executable (Windows)

To produce a standalone Aegis.exe, run the build script from the project root:

```bat
BUILD_EXE.bat
```

What it does:
- Checks for Python 3.13.12 via the py launcher.
- Creates the venv and upgrades pip, then pins setuptools below 82.
- Installs torch and llama-cpp-python from their CPU wheel indexes.
- Installs the rest of requirements.txt with --only-binary :all: so a package with no wheel fails immediately instead of trying to compile. A scoped exception is used for pygetwindow and pyrect, which are pure-Python sdist-only packages.
- Builds with PyInstaller using assistant_gui.spec.
- Copies config.yaml next to the executable.

The build does not bundle the models or data folders. They are created next to the executable at runtime, and the default model downloads on first launch. The executable anchors all of its paths (models, data, config.yaml) to its own folder, so it works regardless of which directory you launch it from.

For a clean rebuild:
```bat
rmdir /s /q venv build dist
BUILD_EXE.bat
```

---

## 4. First Run

With the virtual environment active:

```bash
python -m src.main_gui
```

Or run the built executable from the dist folder.

What happens on first run:
1. Model download (a few minutes): the default model (Llama-3.2-3B-Instruct-Q4_K_M.gguf, about 2 GB) downloads into the models folder.
2. Embedding model download (a minute or two): a small sentence-transformers model downloads.
3. The server starts and your browser opens to http://127.0.0.1:7860.

If you have already placed the GGUF files in the models folder, no download happens.

### Expected console messages (safe to ignore)
```
llama_new_context_with_model: n_ctx_per_seq (4096) < n_ctx_train (131072)
Impersonate 'safari_15.3' does not exist, using 'random'
```
The first is informational. The second comes from the search library's HTTP layer picking a browser profile and is harmless.

---

## 5. Using Aegis

### Basic Chat
1. Type your message in the "Your Message" box.
2. Press Enter or click Send.
3. Tokens stream in as the model responds.
4. Use Stop to cancel a response.

### Available Tools

Aegis can use these automatically through its ReAct loop:

| Tool | What it does | Example |
|------|--------------|---------|
| search_web | Searches the web | "What's the weather in Tokyo?" |
| fetch_url | Retrieves webpage content | "Summarize https://example.com" |
| calc | Safe math evaluation | "What's 15% of 380?" |
| kb_add | Stores a fact in the knowledge base | "Remember that my birthday is June 15" |
| kb_query | Searches stored facts | "When is my birthday?" |
| now | Current date and time | "What day is it?" |

### UI Components

Main chat area: the conversation, the message box, and the Send/Stop/Clear/Export buttons.

Right sidebar:
- Suggestions: output from the proactive agents, with a "Use Last Suggestion" button. (Proactive agents are off by default; see below.)
- Models: switch between "default" (faster) and "large" (more capable).
- Memory Inbox: approve facts before they are stored.
- Collaboration Requests: for multi-device use; can be ignored on a single device.
- Contacts and Identity: for secure peer-to-peer features.
- Training Data: LoRA fine-tuning progress.

### Rating Responses
Use Good, Bad, or Needs Correction under each response. Good and Bad record quick feedback. Needs Correction reveals a box where you type the corrected answer; pressing Enter logs it to data/training/corrections.jsonl for later LoRA fine-tuning.

### Memory System
Aegis uses consent-based memory. During chat it may distill facts about you. Those appear in the Memory Inbox as pending. You must approve them before they are stored and used in future conversations.

### Proactive Agents
Two background agents exist: Sentinel (clipboard and active-window suggestions) and Curator (periodic knowledge-base suggestions). They are disabled by default because they share the single CPU model with the chat and add latency.

To enable them, set proactive_enabled: true in config.yaml (and leave the AEGIS_PROACTIVE environment variable unset or not equal to 0).

To keep them off you do not need to do anything. To force them off even if enabled in config:
```bash
# Windows
$env:AEGIS_PROACTIVE = "0"
python -m src.main_gui

# macOS/Linux
AEGIS_PROACTIVE=0 python -m src.main_gui
```

### Model Switching
- default (Llama-3.2-3B): faster, lower RAM, good for most tasks.
- large (Mistral-7B): more capable, higher RAM, better for complex tasks.

Open the Models accordion, pick from the dropdown, and wait for the status to confirm the switch.

---

## 6. Troubleshooting

### "ModuleNotFoundError: No module named 'src.core'"
Activate the virtual environment first:
```bash
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### A dependency tries to compile from source / "stdalign.h" error
This happens when a package is installed without a matching prebuilt wheel. Make sure you are on Python 3.13, and install using the pinned requirements.txt (and the torch / llama-cpp-python wheel index commands above) rather than installing packages unpinned. The build script enforces this automatically with --only-binary :all:.

### "argument of type 'bool' is not iterable" on a chat request
This was a Gradio 4 / pydantic incompatibility. The project is on Gradio 5, which fixes it. If you see it, your environment still has an old Gradio; reinstall from the pinned requirements.txt in a clean venv.

### "No module named 'audioop'"
Python 3.13 removed the audioop standard-library module. It is supplied by audioop-lts, which Gradio pulls in. Install from the pinned requirements.txt in a clean venv.

### "Database is locked"
Close all Aegis windows and remove the SQLite side files, then restart:
```bash
# Windows
del data\**\*.db-wal
del data\**\*.db-shm
# macOS/Linux
rm data/**/*.db-wal data/**/*.db-shm
```

### Slow responses
- Switch to the default model.
- Lower ctx_size for a model in config.yaml (for example 2048).
- Set n_gpu_layers above 0 in config.yaml only if you have a supported GPU build.

### Model did not download
Models auto-download on first run. To place one manually, check the filename and URL in config.yaml, create the models folder if needed, and download into it:

Windows (PowerShell):
```powershell
Invoke-WebRequest -Uri "https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf?download=true" -OutFile "models\Llama-3.2-3B-Instruct-Q4_K_M.gguf"
```

macOS/Linux:
```bash
curl -L -o models/Llama-3.2-3B-Instruct-Q4_K_M.gguf "https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf?download=true"
```

For the large model, use the Mistral-7B-Instruct-v0.3-Q4_K_M.gguf URL from config.yaml the same way.

### "Connection refused" at startup
P2P networking (the Nexus relay) is not running. Single-user mode does not need it; the relevant background connection is disabled by default. To run the relay for multi-device use:
```bash
uvicorn src.nexus_server:app --host 127.0.0.1 --port 7861
```

---

## 7. Advanced Features

### Multi-Device Collaboration
Aegis supports secure peer-to-peer collaboration between trusted devices.
1. Start the Nexus relay on one machine:
   ```bash
   uvicorn src.nexus_server:app --host 0.0.0.0 --port 7861
   ```
2. Point each device at the relay:
   ```bash
   AEGIS_NEXUS_URL=ws://relay-ip:7861 python -m src.main_gui
   ```
3. Exchange verify keys: open the Identity panel on each device, copy the base64 verify key, and confirm fingerprints out-of-band.
4. Add contacts: open the Contacts panel, add the peer ID, alias, and verify key, then Trust Contact.
5. Collaborate: click Invite to Collaborate, set the scope (allowed tools), and accept on the other device.

### Headless Mode
Run without a GUI:
```bash
python -m src.main_headless
```

### Code Execution (experimental)
Aegis can run Python in a sandbox. This is experimental and not fully secure; only enable on trusted systems.
1. In config.yaml set:
   ```yaml
   assistant:
     allow_code_exec: true
   ```
2. Restart Aegis.

### LoRA Fine-Tuning
1. Rate responses and provide corrections when needed.
2. Corrections are logged to data/training/corrections.jsonl.
3. After enough corrections (default 50), a training set is prepared.
4. Open the Training Data accordion, click Refresh Status, and copy the generated training script to run externally.

### Configuration Reference (config.yaml)

Models (per entry):
```yaml
models:
  - name: "default"
    path: "models/Llama-3.2-3B-Instruct-Q4_K_M.gguf"
    url: "https://huggingface.co/.../Llama-3.2-3B-Instruct-Q4_K_M.gguf?download=true"
    ctx_size: 4096       # lower = faster, less context
    n_gpu_layers: 0      # raise only with a GPU build
```

Assistant:
```yaml
assistant:
  max_reasoning_steps: 5
  tool_timeout_sec: 20
  allow_web_search: true
  proactive_enabled: false   # background agents off by default
  distill_facts: true        # set false for fastest chat
  quiet_hours: [23, 7]       # list: [start_hour, end_hour]
  suggestions_per_min: 5
  allow_domains:
    - "wikipedia.org"
    - "pypi.org"
  allow_code_exec: false
```

Thread count is chosen automatically from your CPU; it is not a per-model config key.

---

## Additional Resources
- README.md: overview and quick start.
- CHANGELOG.md: version history.
- config.yaml: full configuration.
- src/: source code.
