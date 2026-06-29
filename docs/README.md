# Aegis Synthesis Architecture (ASA)

A fully-featured personal AI assistant with a local LLM, secure P2P collaboration, proactive agents, and adaptive learning. It runs entirely on your computer: no cloud, no data sharing, no third-party APIs.

## Features

- Local LLM: Llama 3.2 3B or Mistral 7B (GGUF), hot-swappable at runtime.
- Secure mesh network: end-to-end encrypted P2P collaboration with consent tokens.
- Proactive agents: context-aware suggestions (Sentinel and Curator), disabled by default.
- RAG system: vector knowledge base with semantic search.
- CRDT memory graph: distributed fact synchronization.
- Adaptive learning: style adaptation and a LoRA training-data collector.
- Sandboxed code execution: opt-in, off by default.

## Design Principles

- Privacy: everything is stored locally in SQLite databases.
- Control: you approve what it remembers before it is saved.
- Extensible: a tool system for calculations, web search, and code execution.
- Secure: optional P2P collaboration uses strong encryption with explicit consent.
- Reliable: can run headless, and packages as a standalone executable.

## Architecture Highlights

- Async Python throughout for responsiveness.
- ReAct reasoning loop for tool use.
- CRDT for distributed memory sync across devices.
- Consent tokens for collaboration security.
- WAL-mode SQLite for data integrity.

## Requirements

- Python 3.13 (the build is tested and pinned against 3.13.12).
- Windows, macOS, or Linux. The prebuilt executable and the build script target Windows.
- About 15 GB free disk space (roughly 6 GB of models plus dependencies).
- 8 GB RAM minimum; 16 GB recommended for the large model.

## Quick Start (run from source)

```bash
# 1. Clone
git clone https://github.com/Mr5niper/Aegis-Synthesis-Architecture/ aegis-synthesis
cd aegis-synthesis

# 2. Create and activate a virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 3. Install the CPU wheels for torch and llama-cpp-python first,
#    then the pinned requirements (nothing compiles from source).
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install "llama-cpp-python==0.3.2" --only-binary :all: --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
pip install -r requirements.txt

# 4. Run
python -m src.main_gui
```

torch and llama-cpp-python are not listed in requirements.txt; they install from their own CPU wheel indexes (see the comments in requirements.txt). The first run downloads the default model (about 2 GB) into the models folder, then opens your browser to http://127.0.0.1:7860.

Try: "Hello", then "What's 23 * 456?", then "Remember my favorite color is blue".

## Building a standalone executable (Windows)

```bat
BUILD_EXE.bat
```

This creates a clean virtual environment, installs the CPU wheels and the pinned requirements, and builds the executable with PyInstaller into the dist folder. The models and data folders are not bundled; they are created next to the executable on first run, and the default model downloads at that point. See INSTALL.md for details and troubleshooting.

## Documentation

- INSTALL.md: full setup, first run, usage, and troubleshooting.
- CHANGELOG.md: version history.
- config.yaml: configuration reference.
