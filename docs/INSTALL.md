# 🎉 AEGIS SYNTHESIS - COMPLETE SETUP & USER GUIDE

**Congratulations!** You've received **Aegis Synthesis** - a sovereign, privacy-first AI assistant that runs entirely on your computer. This guide will walk you through setup, first run, and usage.

---

## 📋 Table of Contents
1. [System Requirements](#system-requirements)
2. [Installation](#installation)
3. [First Run](#first-run)
4. [Using Aegis](#using-aegis)
5. [Troubleshooting](#troubleshooting)
6. [Advanced Features](#advanced-features)

---

## 🖥️ System Requirements

### Minimum:
- **OS:** Windows 10/11, macOS 10.15+, or Linux
- **CPU:** 4+ cores recommended
- **RAM:** 8GB minimum (16GB recommended)
- **Disk:** 15GB free space (10GB for models + 5GB for dependencies)
- **Python:** 3.13+ (tested with 3.13.5)

### Recommended:
- **RAM:** 16GB+ for the large model
- **SSD:** For faster model loading
- **GPU:** Optional (NVIDIA with CUDA support for faster inference)

---

## 🚀 Installation

### Step 1: Install Python 3.13

#### Windows:
1. Download Python 3.13 from [python.org](https://www.python.org/downloads/)
2. During installation, **check "Add Python to PATH"**
3. Verify: Open PowerShell and run:
   ```powershell
   python --version
   # Should show: Python 3.13.x
   ```

#### macOS:
```bash
# Install with Homebrew
brew install python@3.13
```

#### Linux:
```bash
# Ubuntu/Debian (if available in repos)
sudo apt update
sudo apt install python3.13 python3.13-venv python3.13-dev

# Or build from source if not in repos yet
# Follow instructions at python.org
```

---

### Step 2: Verify Project Structure

**You should have received the Aegis Synthesis project files.** Before proceeding, you need to verify and complete the directory structure.

#### Initial Structure Check

When you receive the project from GitHub or as a ZIP file, you should have these files:

```
aegis_synthesis/
├── src/
│   ├── agent/
│   │   └── react_async.py
│   ├── core/
│   │   ├── config.py
│   │   ├── event_bus.py
│   │   ├── llm_async.py
│   │   ├── model_manager.py
│   │   ├── policy.py
│   │   ├── prompt.py
│   │   ├── schemas.py
│   │   ├── user_profile.py
│   │   └── validate.py
│   ├── internet/
│   │   ├── cache.py
│   │   ├── fetch.py
│   │   └── search.py
│   ├── learning/
│   │   ├── lora_trainer.py
│   │   └── style_adapter.py
│   ├── memory/
│   │   ├── context_manager.py
│   │   ├── conversation_store.py
│   │   ├── graph_crdt.py
│   │   ├── inbox.py
│   │   └── vector_store.py
│   ├── mesh/
│   │   ├── p2p.py
│   │   ├── protocol_kairos.py
│   │   └── session.py
│   ├── proactive/
│   │   ├── curator.py
│   │   └── sentinel.py
│   ├── secure/
│   │   ├── consent.py
│   │   ├── contacts.py
│   │   └── crypto.py
│   ├── services/
│   │   ├── session_exec.py
│   │   └── sync.py
│   ├── tools/
│   │   ├── registry_async.py
│   │   ├── sandbox.py
│   │   └── session_tools.py
│   ├── ui/
│   │   ├── contacts_panel.py
│   │   ├── consent.py
│   │   ├── identity_panel.py
│   │   └── gui.py
│   ├── utils/
│   │   ├── download.py
│   │   └── db.py
│   ├── __version__.py
│   ├── main_gui.py
│   ├── main_headless.py
│   └── nexus_server.py
├── README.md
├── .gitignore
├── Makefile
├── assistant_gui.spec
├── build_executable.py
├── config.yaml
└── requirements.txt
```

#### Navigate to Project Directory

Open a terminal in the project directory:

**Windows PowerShell:**
```powershell
cd "C:\path\to\aegis_synthesis"  # Adjust to your actual path
```

**macOS/Linux:**
```bash
cd ~/path/to/aegis_synthesis  # Adjust to your actual path
```

#### Create Missing Directories

The `data/` and `models/` directories don't exist in the repository (they contain user-specific data). Create them:

**Windows:**
```powershell
mkdir data
mkdir data\conversations
mkdir data\kb
mkdir data\keys
mkdir data\user_data
mkdir models
```

**macOS/Linux:**
```bash
mkdir -p data/conversations
mkdir -p data/kb
mkdir -p data/keys
mkdir -p data/user_data
mkdir -p models
```

#### Create Required `__init__.py` Files

**⚠️ CRITICAL:** Python needs empty `__init__.py` files in every `src/` subdirectory to recognize them as packages. These files are **not in the repository**.

**Windows PowerShell:**
```powershell
# Copy and paste this entire block
$directories = @(
    "src",
    "src\agent",
    "src\core",
    "src\internet",
    "src\learning",
    "src\memory",
    "src\mesh",
    "src\proactive",
    "src\secure",
    "src\services",
    "src\tools",
    "src\ui",
    "src\utils"
)

foreach ($dir in $directories) {
    New-Item -ItemType File -Path "$dir\__init__.py" -Force | Out-Null
}

Write-Host "✅ All __init__.py files created!"
```

**macOS/Linux:**
```bash
# Copy and paste this entire block
touch src/__init__.py
touch src/agent/__init__.py
touch src/core/__init__.py
touch src/internet/__init__.py
touch src/learning/__init__.py
touch src/memory/__init__.py
touch src/mesh/__init__.py
touch src/proactive/__init__.py
touch src/secure/__init__.py
touch src/services/__init__.py
touch src/tools/__init__.py
touch src/ui/__init__.py
touch src/utils/__init__.py

echo "✅ All __init__.py files created!"
```

#### Verify Final Structure

Run this to verify all `__init__.py` files exist:

**Windows:**
```powershell
Get-ChildItem -Path src -Recurse -Filter "__init__.py" | Measure-Object | Select-Object Count
# Should show: Count = 13
```

**macOS/Linux:**
```bash
find src -name "__init__.py" | wc -l
# Should output: 13
```

---

### Step 3: Create Virtual Environment

**Windows:**
```powershell
# Create virtual environment
python -m venv venv

# Activate it
venv\Scripts\activate

# Your prompt should now show: (venv) PS C:\aegis_synthesis>
```

**macOS/Linux:**
```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Your prompt should now show: (venv) user@machine:~/aegis_synthesis$
```

---

### Step 4: Install Dependencies

**⚠️ IMPORTANT: This will download ~200MB of packages and may take 5-10 minutes**

#### Python 3.13 Compatible Installation

**All Platforms:**
```bash
# Update pip first
pip install --upgrade pip setuptools wheel

# Install core dependencies (Python 3.13 compatible versions)
pip install --no-cache-dir sentence-transformers scipy scikit-learn transformers requests beautifulsoup4 duckduckgo-search pydantic pyyaml gradio pyinstaller pynacl websockets fastapi uvicorn pyperclip

# Install PyTorch for CPU
pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Install llama-cpp-python
pip install --no-cache-dir llama-cpp-python --prefer-binary
```

**For Windows with clipboard/window monitoring:**
```powershell
pip install pygetwindow
```

**For macOS with window monitoring:**
```bash
pip install pyobjc-framework-Quartz pyobjc-framework-AppKit
```

**For Linux with clipboard monitoring:**
```bash
# Install system dependency first
sudo apt install xclip
# No additional Python packages needed
```

#### Verify Installation

```bash
python -c "import torch; import gradio; import llama_cpp; import sentence_transformers; print('✅ All dependencies installed successfully!')"
```

If you see "✅ All dependencies installed successfully!" you're ready to proceed.

---

## 🎬 First Run

### Launch Aegis

Make sure your virtual environment is activated (you should see `(venv)` in your prompt).

```bash
python -m src.main_gui
```

**What happens on first run:**

1. **Model Download** (5-10 minutes):
   ```
   Model 'default' not found. Downloading...
   Llama-3.2-3B-Instruct-Q4_K_M.gguf: 100% |████| 2.02G/2.02G [00:19<00:00, 106MB/s]
   ```
   - This downloads a 2GB AI model
   - Only happens once
   - May take longer on slower internet

2. **Embedding Model Download** (1-2 minutes):
   ```
   model.safetensors: 100% |████| 90.9M/90.9M [00:00<00:00, 105MB/s]
   ```
   - Downloads a 91MB embedding model
   - Also only happens once

3. **System Initialization**:
   ```
   llama_new_context_with_model: n_ctx_per_seq (4096) < n_ctx_train (131072)
   * Running on local URL:  http://127.0.0.1:7860
   ```

4. **Browser Opens**: Your browser will automatically open to `http://127.0.0.1:7860`

### Expected Warnings (Safe to Ignore)

You may see these deprecation warnings - they're harmless:

```
DeprecationWarning: There is no current event loop
RuntimeWarning: This package `duckduckgo_search` has been renamed to `ddgs`
UserWarning: You have not specified a value for the `type` parameter
DeprecationWarning: The 'bubble_full_width' parameter is deprecated
```

---

## 💬 Using Aegis

### Basic Chat

1. **Type your message** in the "Your Message" box at the bottom
2. **Press Enter** or click "Send"
3. **Wait for response** - you'll see tokens streaming in real-time
4. **Stop generation** anytime with the "Stop" button

**Example first conversation:**
```
You: Hello!
Aegis: Hello! I'm Aegis, your local AI assistant. How can I help you today?

You: What can you do?
Aegis: I can help with many tasks:
- Answer questions and have conversations
- Search the web for current information
- Perform calculations
- Store and recall information in my knowledge base
- Run Python code (if enabled)
- Much more!

What would you like to try?
```

---

### Available Tools

Aegis can use these tools automatically:

| Tool | What It Does | Example |
|------|-------------|---------|
| `search_web` | Searches DuckDuckGo | "What's the weather in Tokyo?" |
| `fetch_url` | Retrieves webpage content | "Summarize https://example.com" |
| `calc` | Safe math evaluation | "What's 15% of 380?" |
| `kb_add` | Store facts in knowledge base | "Remember that my birthday is June 15" |
| `kb_query` | Search stored facts | "When is my birthday?" |
| `now` | Current date/time | "What day is it?" |

**Example tool usage:**
```
You: What's 23 * 456?
Aegis: [Using calc tool]
The result is 10,488.

You: Search for Python async best practices
Aegis: [Using search_web tool]
I found several resources on Python async programming...
[Returns search results and summary]
```

---

### UI Components

#### Main Chat Area
- **Chatbot Window**: Your conversation history
- **Message Box**: Type your messages here
- **Send/Stop Buttons**: Control message sending

#### Right Sidebar

**Suggestions:**
- Real-time suggestions from proactive agents
- "Use Last Suggestion" button to insert into message box

**Models:**
- Switch between "default" (faster) and "large" (more capable)
- Shows current model status

**Memory Inbox:**
- Approve facts before they're permanently stored
- Check boxes and click "Approve Selected"

**Collaboration Requests:**
- Advanced feature for multi-device usage
- Can be ignored for single-device use

**Contacts:**
- Manage trusted peer connections
- Used for advanced collaboration features

**Identity:**
- Your device's unique ID and verification key
- Used for secure peer-to-peer features

**Training Data:**
- View LoRA fine-tuning progress
- Rate responses to improve the model

---

### Memory System

Aegis has a **consent-based memory** system:

1. During chat, Aegis may distill facts about you
2. These appear in **Memory Inbox** as pending
3. **You must approve** before they're stored
4. Approved facts are saved and used in future conversations

**Example:**
```
You: My favorite color is blue
Aegis: Got it! I'll remember that.
[In Memory Inbox: "User's favorite color is blue" appears]
[You check the box and click "Approve Selected"]
[Now Aegis will remember this in future chats]
```

---

### Proactive Agents

Aegis has two background agents:

#### Sentinel (Clipboard Monitor)
- Watches your clipboard
- Suggests actions based on copied text
- **Example:** Copy a URL → "Would you like me to summarize that webpage?"

#### Curator (Knowledge Suggestions)
- Periodically suggests knowledge base actions
- "You haven't queried your knowledge base recently. Try: 'What do I remember about Python?'"

**To disable:**
```bash
# Set environment variable before running
# Windows:
$env:AEGIS_PROACTIVE = "0"
python -m src.main_gui

# macOS/Linux:
AEGIS_PROACTIVE=0 python -m src.main_gui
```

---

### Model Switching

Aegis supports multiple models:

1. **Default** (Llama-3.2-3B):
   - Faster responses
   - Lower RAM usage (~4GB)
   - Good for most tasks

2. **Large** (Mistral-7B):
   - More capable
   - Higher RAM usage (~8GB)
   - Better for complex tasks

**To switch:**
1. Open "Models" accordion in sidebar
2. Select from dropdown
3. Wait for "Model switched successfully"

**When to use each:**
- **Default**: General chat, quick questions, fast responses
- **Large**: Complex reasoning, detailed analysis, creative writing

---

## 🐛 Troubleshooting

### "ModuleNotFoundError: No module named 'src.core'"

**Solution:** Activate your virtual environment:
```bash
# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

---

### "Permission denied" during pip install

**Windows Solution:**
```powershell
# Run PowerShell as Administrator
# OR use --no-cache-dir flag:
pip install --no-cache-dir -r requirements.txt
```

**macOS/Linux Solution:**
```bash
# Use --user flag (preferred):
pip install --user --no-cache-dir -r requirements.txt

# OR adjust permissions:
sudo chown -R $USER:$USER ~/.cache/pip
```

---

### "Database is locked"

**Cause:** Multiple instances running or interrupted shutdown

**Solution:**
1. Close all Aegis windows
2. Delete lock files:
   ```bash
   # Windows
   del data\**\*.db-wal
   del data\**\*.db-shm
   
   # macOS/Linux
   rm data/**/*.db-wal
   rm data/**/*.db-shm
   ```
3. Restart Aegis

---

### Slow responses

**Solutions:**

1. **Switch to default model** if using large
2. **Adjust thread count** in `config.yaml`:
   ```yaml
   models:
     - name: "default"
       n_threads: 8  # Set to your CPU core count
   ```
3. **Reduce context size** in `config.yaml`:
   ```yaml
   models:
     - name: "default"
       ctx_size: 2048  # Lower = faster but less memory
   ```

---

### Clipboard/window monitoring not working

**Windows:**
```powershell
pip install pygetwindow pywin32
```

**macOS:**
```bash
pip install pyobjc-framework-Quartz pyobjc-framework-AppKit
```

**Linux:**
```bash
# Install xclip or xsel
sudo apt install xclip
# OR
sudo apt install xsel
```

---

### "Cannot find model file"

**Solution:** Models auto-download on first run, but if it fails:

#### Manual Model Download

1. **Check the model filename** in `config.yaml`:
   ```yaml
   models:
     - name: "default"
       path: "models/Llama-3.2-3B-Instruct-Q4_K_M.gguf"  # ← This is the filename
       url: "https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf?download=true"
   ```

2. **Create the models directory** if it doesn't exist:
   ```bash
   # Windows
   mkdir models
   
   # macOS/Linux
   mkdir -p models
   ```

3. **Download manually:**
   
   **Windows (PowerShell):**
   ```powershell
   Invoke-WebRequest -Uri "https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf?download=true" -OutFile "models\Llama-3.2-3B-Instruct-Q4_K_M.gguf"
   ```
   
   **macOS/Linux:**
   ```bash
   wget -O models/Llama-3.2-3B-Instruct-Q4_K_M.gguf "https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf?download=true"
   
   # OR with curl:
   curl -L -o models/Llama-3.2-3B-Instruct-Q4_K_M.gguf "https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf?download=true"
   ```

4. **Verify the file:**
   ```bash
   # Windows
   dir models
   # Should show: Llama-3.2-3B-Instruct-Q4_K_M.gguf (~2GB)
   
   # macOS/Linux
   ls -lh models/
   # Should show: Llama-3.2-3B-Instruct-Q4_K_M.gguf (~2.0G)
   ```

5. **Retry launching Aegis:**
   ```bash
   python -m src.main_gui
   ```

#### For the Large Model (Optional)

If you also want the large model:

```bash
# Windows
Invoke-WebRequest -Uri "https://huggingface.co/bartowski/Mistral-7B-Instruct-v0.3-GGUF/resolve/main/Mistral-7B-Instruct-v0.3-Q4_K_M.gguf" -OutFile "models\Mistral-7B-Instruct-v0.3-Q4_K_M.gguf"

# macOS/Linux
wget -O models/Mistral-7B-Instruct-v0.3-Q4_K_M.gguf "https://huggingface.co/bartowski/Mistral-7B-Instruct-v0.3-GGUF/resolve/main/Mistral-7B-Instruct-v0.3-Q4_K_M.gguf"
```

---

### "llama-cpp-python build failed"

**Cause:** Python 3.13 is new and some binary wheels may not be available yet.

**Solution 1 - Use pre-built wheel:**
```bash
pip install llama-cpp-python --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
```

**Solution 2 - Install C++ compiler:**

**Windows:**
1. Download [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
2. Install "Desktop development with C++"
3. Restart terminal
4. Retry: `pip install llama-cpp-python`

**macOS:**
```bash
xcode-select --install
```

**Linux:**
```bash
# Ubuntu/Debian
sudo apt install build-essential

# Fedora
sudo dnf install gcc gcc-c++ make
```

---

### "Unclosed database" warnings

**Cause:** Resource warnings from async event loops (harmless)

**To suppress:**
```bash
# Windows
$env:PYTHONWARNINGS = "ignore::ResourceWarning"
python -m src.main_gui

# macOS/Linux
PYTHONWARNINGS="ignore::ResourceWarning" python -m src.main_gui
```

---

### "Connection refused" when starting

**Cause:** Trying to connect to Nexus relay (P2P feature) which isn't running

**Solution - Disable P2P for single-user mode:**
```bash
# Windows
$env:AEGIS_NEXUS_URL = "disabled"
python -m src.main_gui

# macOS/Linux
AEGIS_NEXUS_URL="disabled" python -m src.main_gui
```

**OR run the Nexus relay** (optional, for multi-device use):
```bash
# In a separate terminal
uvicorn src.nexus_server:app --host 127.0.0.1 --port 7861
```

---

## 🚀 Advanced Features

### Multi-Device Collaboration

Aegis supports secure peer-to-peer collaboration between trusted devices.

#### Setup:

1. **Start Nexus relay** on one machine:
   ```bash
   uvicorn src.nexus_server:app --host 0.0.0.0 --port 7861
   ```

2. **Point agents to relay:**
   ```bash
   # Device 1
   AEGIS_NEXUS_URL=ws://relay-ip:7861 python -m src.main_gui
   
   # Device 2
   AEGIS_NEXUS_URL=ws://relay-ip:7861 python -m src.main_gui
   ```

3. **Exchange verify keys:**
   - Open "Identity" panel on each device
   - Copy the verify key (base64)
   - Verify fingerprints out-of-band (phone call, secure message)

4. **Add contacts:**
   - Open "Contacts" panel
   - Add peer ID, alias, and verify key
   - Click "Trust Contact"

5. **Collaborate:**
   - Click "Invite to Collaborate"
   - Specify scope (allowed tools)
   - Accept invitation on other device

---

### Headless Mode

Run Aegis without a GUI (for servers or background tasks):

```bash
python -m src.main_headless
```

**Features:**
- No browser UI
- Denies collaboration by default
- Minimal resource usage
- Can be accessed via API (if implemented)

---

### Code Execution (Advanced)

Aegis can execute Python code in a sandboxed environment.

**⚠️ WARNING: This is experimental and not fully secure. Only enable on trusted systems.**

#### Enable:

1. Edit `config.yaml`:
   ```yaml
   assistant:
     allow_code_exec: true
   ```

2. Set environment variable:
   ```bash
   # Windows
   $env:AEGIS_ENABLE_CODE_EXEC = "1"
   
   # macOS/Linux
   export AEGIS_ENABLE_CODE_EXEC=1
   ```

3. Restart Aegis

#### Usage:
```
You: Run this Python code: print(sum([1,2,3,4,5]))
Aegis: [Using code_exec tool]
Output: 15
```

---

### LoRA Fine-Tuning

Aegis can learn from your corrections over time.

#### How it works:

1. **Rate responses** with 👍/👎/✏️
2. **Provide corrections** when needed
3. Aegis logs these to `data/user_data/lora_corrections.jsonl`
4. After 50+ corrections, training data is prepared
5. **Training viewer** shows progress and generates training script

#### View progress:
1. Open "Training Data" accordion in sidebar
2. Click "Refresh Status"
3. When ready, copy the training script
4. Run it externally with appropriate LoRA training tools

---

### Configuration Tuning

Edit `config.yaml` to customize behavior:

#### Performance:
```yaml
models:
  - name: "default"
    n_threads: 8          # Match your CPU cores
    n_gpu_layers: 0       # Set to 35+ if you have GPU
    ctx_size: 4096        # Lower = faster, less context
```

#### Behavior:
```yaml
assistant:
  max_reasoning_steps: 5  # Max tool-use iterations
  tool_timeout: 30        # Seconds per tool call
  quiet_hours:            # Don't run proactive agents
    start: "22:00"
    end: "07:00"
```

#### Security:
```yaml
assistant:
  allow_domains:          # Web fetch whitelist
    - "wikipedia.org"
    - "github.com"
  allow_code_exec: false  # Keep disabled by default
```

---

## 📚 Additional Resources

### Project Files:

- **README.md**: Quick start guide
- **config.yaml**: Full configuration reference
- **src/**: Source code (well-documented)

### Getting Help:

1. Check console output for error messages
2. Review this troubleshooting section
3. Check GitHub issues (if project is on GitHub)
4. Enable verbose logging:
   ```bash
   # Windows
   $env:AEGIS_LOG_LEVEL = "DEBUG"
   
   # macOS/Linux
   export AEGIS_LOG_LEVEL=DEBUG
   ```

---

## 🎓 Tips for Best Results

### Chat Tips:
- **Be specific**: "Search for Python async patterns in 2024" vs "help with Python"
- **Use tools explicitly**: "Calculate 15% tip on $45" triggers calc tool
- **Build context**: Reference previous messages, Aegis remembers the conversation

### Memory Tips:
- **Approve selectively**: Only approve facts you want long-term memory of
- **Review inbox regularly**: Old pending facts accumulate
- **Use KB queries**: "What do I know about Python?" searches your approved facts

### Performance Tips:
- **Close unused programs** before loading large models
- **Use default model** for routine tasks
- **Switch to large model** only when needed
- **Restart occasionally** to clear memory

---

## 🎉 You're Ready!

Aegis Synthesis is now fully set up and running. Experiment with different features, build up your knowledge base, and customize the configuration to match your workflow.

**Enjoy your privacy-first AI assistant!** 🚀

---
