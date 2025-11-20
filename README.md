# Aegis Synthesis Architecture (ASA)

A fully-featured personal AI assistant with local LLM, secure P2P collaboration, proactive agents, and adaptive learning.

## Features

- 🧠 **Local LLM** - Llama 3.2 or Mistral 7B with hot-swapping
- 🔐 **Secure Mesh Network** - E2EE P2P collaboration with consent tokens
- 🎯 **Proactive Agents** - Context-aware suggestions (Sentinel & Curator)
- 📚 **RAG System** - Vector knowledge base with semantic search
- 🔄 **CRDT Memory Graph** - Distributed fact synchronization
- 📖 **Adaptive Learning** - Style adaptation & LoRA fine-tuning
- 🛡️ **Sandboxed Code Execution** - Safe Python code execution

## Quick Start

```bash
# 1. Create virtual environment
make venv
make install

# 2. Download models (automatic on first run)
# Edit config.yaml to choose models

# 3. Run GUI mode
make gui

# 4. (Optional) Run relay server for P2P
make nexus
