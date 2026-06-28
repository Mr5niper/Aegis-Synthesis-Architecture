# AEGIS SYNTHESIS ARCHITECTURE CHANGELOG

## v1.1.0.0 - [current]

### Performance
- **Proactive agents disabled by default (lag fix):** The Sentinel clipboard/window watcher polled every 3 seconds and fired a full LLM generation on every clipboard or active-window change. Because it shares the single CPU-bound model instance with the chat (serialized by a per-model semaphore), user messages queued behind background suggestions, producing the lag and apparent freezes during normal use.
  - `config.yaml`: `assistant.proactive_enabled` now defaults to `false`. Both `main_gui.py` and the agents already gate on this flag, so no code change is required to keep them off.
  - Re-enable by setting `proactive_enabled: true` (and leaving the `AEGIS_PROACTIVE` env var unset or `!= 0`).
- **Optional per-turn fact distillation:** Every chat turn previously ran a third LLM generation to extract user facts ("triples"), adding latency to each message on the 3B CPU model.
  - Added `assistant.distill_facts` (default `true`). Set to `false` for maximum chat responsiveness; fact extraction is then skipped entirely.
  - Wired through `core/config.py` (new field), `main_gui.py` (passed into the agent factory), and `agent/react_async.py` (new `distill_facts` constructor arg gating a `_maybe_distill_facts` guard).

### Stability
- **Streaming inference race / crash fix (`core/llm_async.py`):** `stream_async` released the model semaphore as soon as the consumer loop ended, while its producer ran on a **daemon** thread that could still be executing inside `llama.cpp`. A second call could then acquire the semaphore and re-enter the non-reentrant library concurrently, corrupting state and crashing the process.
  - The producer is now a **non-daemon** thread that is explicitly `join()`-ed (off the event loop) inside the `async with self._sem` block, so the lock is never released until the worker has fully exited `llama.cpp`.
  - Cancellation now drains the queue until the producer emits its end sentinel, guaranteeing the worker is never left running after a stop.

### Web Search
- **Reliable tool routing (`core/prompt.py`):** Web search was enabled in config and registered as a tool, but the router prompt only listed bare tool *names* with no descriptions or examples. The 3B model rarely emitted the tool-call JSON, so it answered current-info questions from stale memory instead of searching.
  - Rewrote the ReAct routing prompt to include a per-tool description menu, an explicit instruction to use `search_web` for any current/uncertain information, and few-shot examples (including web-search and `fetch_url` cases).
  - Clarified the final-answer prompt to instruct the model to use tool observations and cite URLs when present.

### Build
- **`BUILD_EXE.bat` added:** Mirrors the WindowsAudioControl build script — same `py -3.13` launcher resolution and `3.13.12` version gate, venv creation, and `pip install -r requirements.txt` flow. Because Aegis is a package (run as `-m src.main_gui`) rather than a single script, the final step builds through the project spec: `pyinstaller --clean --noconfirm assistant_gui.spec`. Also pre-creates the `models/` and `data/` folders so the spec's `datas` collection succeeds on a fresh checkout.
- **UPX disabled in PyInstaller spec (`assistant_gui.spec`):** Changed `upx=True` to `upx=False` on both `EXE` and `COLLECT`. UPX frequently corrupts large native DLLs (torch, `llama_cpp`) and is a common cause of executables that crash on launch. This matches the `--noupx` choice already used in the WindowsAudioControl build.

### Compatibility
- No changes to the chat API, tool schemas, on-disk databases, or config keys beyond the two new additive `assistant` fields (`distill_facts`, and the changed default for `proactive_enabled`). Existing `config.yaml` files remain valid; the new fields fall back to their defaults if absent.

---

## v1.0.0.0

### Initial Release
- **Local LLM core:** llama.cpp-backed assistant (`AsyncLocalLLM`) with support for Llama 3.2 3B and Mistral 7B GGUF models, hot-swappable at runtime via `ModelManager`. All generation serialized per-instance for thread safety.
- **ReAct agent:** Tool-using reasoning loop (`ReActAgent`) that routes user input to tools via JSON, observes results, and streams a final answer. Tools: `now`, `calc`, `search_web`, `fetch_url`, `ingest_url`, `kb_add`, `kb_query`, `code_exec` (sandboxed, opt-in).
- **Memory systems:**
  - Conversation history in WAL-mode SQLite.
  - Vector knowledge base with sentence-transformers embeddings and semantic retrieval (RAG).
  - CRDT (LWW) memory graph for distributed fact synchronization.
  - Memory inbox with user approval workflow before facts are committed to the graph.
- **Secure mesh networking:** End-to-end encrypted P2P collaboration over a Nexus relay, Ed25519 identity keys, the Kairos session protocol, consent tokens, and a contacts trust store.
- **Proactive agents:** Sentinel (clipboard/active-window context suggestions) and Curator (periodic knowledge-base suggestions), gated by a policy manager with quiet hours and rate limiting.
- **Adaptive learning:** Style adapter that adjusts tone from user messages, and a LoRA training-data collector driven by in-GUI feedback/corrections.
- **Web UI:** Gradio chat interface with streaming responses, model switcher, proactive suggestion feed, memory-inbox approval, collaboration-request approval, conversation export, and a feedback/rating panel.
- **Packaging:** Headless and GUI entry points, a PyInstaller spec, and a model auto-downloader (~2 GB on first run).
