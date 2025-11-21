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


A privacy-first AI assistant that runs entirely on your computer - no cloud, no data sharing, no third-party APIs.

Core Features:

Local AI Brain: Multiple AI models you can switch between (small/fast or large/smart)
Smart Memory: Remembers facts with your approval, searches past conversations
Proactive Helpers: Background agents that suggest actions (clipboard monitoring, knowledge suggestions)
Multi-Device Sync: Securely connect your own devices with end-to-end encryption
Learning System: Gets better over time from your feedback
Web Interface: Easy-to-use chat UI in your browser
Key Design Principles:

Privacy: Everything stored locally in SQLite databases
Control: You approve what it remembers
Extensible: Tool system for calculations, web search, code execution
Secure: Optional P2P collaboration uses military-grade encryption with explicit consent
Reliable: Can run 24/7 in headless mode, packages as standalone app
Architecture Highlights:

Async Python throughout for responsiveness
ReAct reasoning loop for tool use
CRDT for distributed memory sync across devices
Consent tokens for collaboration security
WAL-mode SQLite for data integrity
Think of it as: Your personal ChatGPT that lives on your computer, remembers what you tell it, can connect your devices securely, and never sends your data anywhere.

## **Quick Start**

```bash
# 1. Setup environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 1. Clone and setup
git clone https://github.com/Mr5niper/Aegis-Synthesis-Architecture/ aegis-synthesis
cd aegis-synthesis
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run Aegis
python -m src.main_gui
```

**First run downloads ~2GB model automatically (5-10 min). Browser opens to `http://localhost:7860` when ready.**

**Try:** "Hello" → "What's 23 * 456?" → "Remember my favorite color is blue"

---


# 4. (Optional) Run relay server for P2P
make nexus
