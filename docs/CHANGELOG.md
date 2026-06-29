# AEGIS SYNTHESIS ARCHITECTURE CHANGELOG

## vx.x.x.x - [next]

### Stability
- **Dropped connection no longer freezes the UI (`src/core/llm_async.py`):** When a chat connection was torn down mid-generation (for example toggling the theme, or closing and reopening the browser tab), the streaming producer kept running `llama.cpp` to its full token limit while holding the per-model semaphore. On a CPU model that blocked every other model operation for up to a couple of minutes until the abandoned generation finished on its own.
  - The streaming generator now signals an internal stop when the consumer is torn down (`GeneratorExit`) or the Stop button is pressed, so the producer halts at its next token instead of generating all of them while holding the lock.
  - Token enqueue is non-blocking with a bounded wait, so a gone consumer can never wedge the producer thread on a full queue. The model lock is released in roughly one token's time on disconnect rather than after the whole generation.

### Agent
- **Reasoning loop guard (`src/agent/react_async.py`):** The ReAct agent could get stuck repeating the same tool call (for example calling `calc` with `340 * 1` over and over) until it exhausted `max_reasoning_steps`, showing a wall of repeated Thinking/Action blocks before finally answering.
  - The agent now records each executed `(tool, args)` signature. If the model selects a call it has already run, the agent stops iterating and composes the final answer from the observations gathered so far instead of burning more steps.
  - The fallback final answer (reached by the loop guard or by exhausting `max_reasoning_steps`) is now streamed token-by-token like the normal path, rather than returned as one blocking generation.
- **Router no longer hallucinates a fake transcript (`src/agent/react_async.py`):** The tool-routing generation produced up to 220 tokens with only generic stop sequences, so the small model would emit its one JSON tool call and then keep going, inventing `Observation:`, `Assistant:`, and `User:` lines, fake follow-up questions, made-up tool calls, and fabricated URLs.
  - The routing call now passes tight stop sequences (a blank line and the `Observation:`/`Assistant:`/`User:`/`System:` role markers), so generation ends immediately after the single JSON object.
- **Simple questions answered directly instead of misusing tools (`src/core/prompt.py`):** For conversational questions such as "what is your name" the model reached for `kb_add`/`kb_query` against an empty knowledge base and took an unnecessary tool step before answering.
  - The routing guidance now leads with the rule that most messages need no tool: greetings, small talk, questions about the assistant itself, opinions, explanations, and anything answerable from existing knowledge must use `none` and answer directly, and must never use `kb_add`/`kb_query` for simple conversational questions. Added `none` few-shot examples for an identity question and a capabilities question.
  - The tool-call schema instruction was tightened to emit exactly one JSON object and then stop, with no observation, answer, or further turns.
- **Final answers are now plain prose, not JSON (`src/core/prompt.py`):** Primed by the JSON of the routing step, the small model sometimes returned the answer as a JSON object (for example `{"name": "Aegis", "type": "AI Assistant"}`) instead of a sentence.
  - `final_answer_prompt` now explicitly instructs the model to answer in plain, natural English and to not output JSON, key/value pairs, code blocks, curly braces, or field names.

## v1.1.0.0 - [current]

### Performance
- **Proactive agents disabled by default (lag fix):** The Sentinel clipboard/window watcher polled every 3 seconds and fired a full LLM generation on every clipboard or active-window change. Because it shares the single CPU-bound model instance with the chat (serialized by a per-model semaphore), user messages queued behind background suggestions, producing the lag and apparent freezes during normal use.
  - `config.yaml`: `assistant.proactive_enabled` now defaults to `false`. Both `main_gui.py` and the agents already gate on this flag, so no code change is required to keep them off.
  - Re-enable by setting `proactive_enabled: true` (and leaving the `AEGIS_PROACTIVE` env var unset or `!= 0`).
- **Optional per-turn fact distillation:** Every chat turn previously ran a third LLM generation to extract user facts ("triples"), adding latency to each message on the 3B CPU model.
  - Added `assistant.distill_facts` (default `true`). Set to `false` for maximum chat responsiveness; fact extraction is then skipped entirely.
  - Wired through `core/config.py` (new field), `main_gui.py` (passed into the agent factory), and `agent/react_async.py` (new `distill_facts` constructor arg gating a `_maybe_distill_facts` guard).

### Stability
- **Streaming inference race / crash fix (`core/llm_async.py`):** `stream_async` released the model semaphore as soon as the consumer loop ended, while its producer ran on a daemon thread that could still be executing inside `llama.cpp`. A second call could then acquire the semaphore and re-enter the non-reentrant library concurrently, corrupting state and crashing the process.
  - The producer is now a non-daemon thread that is explicitly `join()`-ed (off the event loop) inside the `async with self._sem` block, so the lock is never released until the worker has fully exited `llama.cpp`.
  - Cancellation now drains the queue until the producer emits its end sentinel, guaranteeing the worker is never left running after a stop.

### Web Search
- **Reliable tool routing (`core/prompt.py`):** Web search was enabled in config and registered as a tool, but the router prompt only listed bare tool names with no descriptions or examples. The 3B model rarely emitted the tool-call JSON, so it answered current-info questions from stale memory instead of searching.
  - Rewrote the ReAct routing prompt to include a per-tool description menu, an explicit instruction to use `search_web` for any current/uncertain information, and few-shot examples (including web-search and `fetch_url` cases).
  - Clarified the final-answer prompt to instruct the model to use tool observations and cite URLs when present.

### User Interface
- **Migrated the GUI from Gradio 4 to Gradio 5.50.0 (`src/ui/gui.py`, `requirements.txt`):** Gradio 4.44.1 bundled a `gradio_client` whose API-schema generator crashed at request time with `TypeError: argument of type 'bool' is not iterable` when running against pydantic 2.11+, which the resolver pulled in. The schema generator expected a dict where pydantic 2.11 now emits a bare boolean (gradio issues #10662 and #11084). Moving to Gradio 5.50.0 takes the upstream fix instead of pinning pydantic backward.
  - Converted the Chatbot component and the four functions that touch chat history (`user_turn`, `bot_turn`, `export_conversation`, and the rating handler) from the Gradio 4 tuple-pair format to the Gradio 5 messages format (`{"role": ..., "content": ...}`).
  - Set explicit `server_name`, `server_port`, and `show_api=False` on launch.
- **Fixed the rating buttons not responding (`src/ui/gui.py`):** Clicking Good or Bad did nothing because `handle_rating` returned a value that wrote back to the rating radio. Setting the radio value re-fired its own change event with no selection, which immediately blanked the feedback status that had just been written. Two separate non-queued change handlers were also bound to the same radio and raced each other.
  - `handle_rating` now returns only two outputs (feedback status text and correction-box visibility) and never writes back to the radio, so it cannot re-trigger itself.
  - Merged the two rating change handlers into one.
  - Good and Bad no longer require the trainer to be present; only "Needs Correction" uses it (logged to `data/training/corrections.jsonl`).

### Dependencies
- **Pinned all dependencies to versions with prebuilt Python 3.13 (cp313) Windows wheels (`requirements.txt`):** The previous manifest used `>=` version floors. On Python 3.13 those floors resolved to versions that predated cp313 wheels, so pip fell back to compiling NumPy and scikit-learn from source, which failed with `fatal error C1083: 'stdalign.h'` on any machine without a full MSVC build toolchain. Every package is now pinned with `==` to a version that publishes a cp313 Windows wheel, so installation is a binary download and nothing compiles.
  - NumPy is intentionally not pinned. It is pulled in transitively by torch at a known-good wheel version; pinning it separately reintroduced the source build.
  - pydantic, gradio-client, websockets, and audioop-lts are left unpinned. Gradio 5.50.0 constrains all of them itself, and pinning them separately only risks conflicting with Gradio's own requirements.
- **Added `audioop-lts`:** Python 3.13 removed the `audioop` standard-library module. `pydub`, pulled in through Gradio's dependency chain, still imports it unconditionally, so a fresh 3.13 install failed at import with `ModuleNotFoundError: No module named 'audioop'`. `audioop-lts` backports the module. Aegis uses no audio feature; this only satisfies the import. (On the Gradio 5 build it is also pulled in automatically as a Gradio dependency.)

### Runtime / Frozen Executable
- **Paths now resolve next to the executable when frozen (`src/main_gui.py`):** Every path in the application (`models/`, `data/`, `config.yaml`, key stores) is relative to the current working directory. Running from source in the repo root this is correct, but a PyInstaller executable launched from another directory (for example a desktop shortcut) resolved those paths against the wrong location and would create a fresh `models/` folder and re-download the model weights.
  - Added a frozen-aware `os.chdir(<exe directory>)` at the start of `main()`. When frozen, the process anchors its working directory to the executable's folder, so all relative paths resolve next to the .exe exactly as they resolve next to the repo root from source. Running from source is unaffected.
- **Single-file temp directory is cleaned up safely (`src/main_gui.py`):** The single-file executable (see Build) unpacks to a temporary `_MEIxxxxxx` folder on each launch. The bootloader removes it on a normal exit, but a hard kill (Task Manager, crash, power loss) leaves it behind.
  - On startup the app now sweeps and removes its own orphaned temp folders from previous runs. Because every PyInstaller single-file app unpacks to a `_MEIxxxxxx` folder with no app name, deleting by that name alone would destroy other apps' temp dirs, so Aegis writes a marker file into its own unpack dir and only ever removes folders that contain that marker.
  - It never removes the current process's own folder, and it uses `rmtree` without `ignore_errors`, so a folder whose files are still locked by a concurrently running instance fails to delete and is left intact rather than partially gutted. Other applications' temp folders are never touched.

### Build
- **`BUILD_EXE.bat` added:** Same `py -3.13` launcher resolution and `3.13.12` version gate, venv creation, and dependency install flow used by the WindowsAudioControl build script. Because Aegis is a package (run as `-m src.main_gui`) rather than a single script, the final step builds through the project spec: `pyinstaller --clean --noconfirm assistant_gui.spec`.
- **Wheel-only dependency install (build failure fix):** `BUILD_EXE.bat` installs `torch` from the PyTorch CPU index and `llama-cpp-python==0.3.2` from its prebuilt CPU wheel index before installing the rest of `requirements.txt`. Previously pip tried to build `llama-cpp-python` from source, which requires an MSVC + CMake toolchain and failed with `CMAKE_C_COMPILER not set` / `nmake` not found on machines without a C/C++ compiler. `torch` and `llama-cpp-python` were also removed from `requirements.txt` (with a documented note) so they can only come from their correct wheel indexes.
  - The remaining dependencies install with `--only-binary :all:` so a package with no wheel fails immediately with a clear "no matching distribution" message instead of silently invoking a compiler. A scoped exception, `--no-binary pygetwindow,pyrect`, is required because those two packages are pure Python and ship only as sdists at every version (no wheel exists), but they contain no compiled code, so installing them from sdist is a safe file copy.
  - `llama-cpp-python` is pinned to 0.3.2 because that is the only version the abetlen CPU index publishes a Windows cp313 wheel for. Newer versions resolve to a non-cp313 build that crashes at model load with Windows Error 0xC000001D.
  - Step 3 pins `setuptools<82` to satisfy torch's build metadata.
  - After the build, `config.yaml` is copied next to the executable so the app loads it from beside the .exe.
- **Frozen-executable import fix (`ImportError: attempted relative import with no known parent package`):** Added a top-level launcher (`aegis_launcher.py`) that imports `src.main_gui` as a package and calls `main()`, and pointed the PyInstaller spec at it instead of `src/main_gui.py`. Running `src/main_gui.py` directly as the entry script gave it no parent package, so its `from .core ...` relative imports failed at startup in the built exe. The spec also collects all `src` submodules via `collect_submodules('src')`.
- **Added missing package `__init__.py` files:** Only `src/__init__.py` existed; the 12 subpackages (`agent`, `core`, `internet`, `learning`, `memory`, `mesh`, `proactive`, `secure`, `services`, `tools`, `ui`, `utils`) had none. They worked from source as namespace packages but were not reliably bundled by PyInstaller. All 13 `__init__.py` files are now committed, and `BUILD_EXE.bat` recreates any that are missing as a safety net.
- **Single-file executable (`assistant_gui.spec`):** The spec now produces one self-contained `dist/Aegis.exe` instead of a one-folder build. All binaries, zipped modules, and data files are folded into the `EXE()` call and the separate `COLLECT()` step was removed, so there is no longer an accompanying `dist/Aegis/` folder.
- **Embedded Windows version metadata (`assistant_gui.spec`):** The spec reads `__version__` and `__codename__` from `src/__version__.py` at build time, parses the dotted version into the required integer tuple, and builds a Windows `VSVersionInfo` resource from it. Right-click `Aegis.exe` -> Properties -> Details now shows File version, Product version, and Product name, all matching `src/__version__.py` with nothing to keep in sync by hand. The resource construction is guarded so a missing Windows-only dependency cannot abort the build (it falls back to building without metadata).
- **Executable icon (`assistant_gui.spec`, `BUILD_EXE.bat`, `aegis.ico`):** The spec sets the executable icon via `icon='aegis.ico'`. `BUILD_EXE.bat` checks that `aegis.ico` exists in the project root before building and fails with a clear message if it is missing, instead of a confusing PyInstaller error.
- **Stopped bundling the `models/` and `data/` folders (`assistant_gui.spec`):** The spec's `datas` list previously included `models/` and `data/`, which copied roughly 6 GB of model weights into every build for no benefit. Those folders are runtime-managed (models are downloaded on first launch; data is written during use) and are created next to the executable at runtime. The spec's `datas` is now `[('config.yaml', '.')]` plus the collected `llama_cpp` data files.
- **UPX disabled in PyInstaller spec (`assistant_gui.spec`):** `upx=False` on the `EXE`. UPX frequently corrupts large native DLLs (torch, `llama_cpp`) and is a common cause of executables that crash on launch.

### Compatibility
- No changes to the chat API, tool schemas, or on-disk databases. Config gains two additive `assistant` fields (`distill_facts`, and the changed default for `proactive_enabled`); existing `config.yaml` files remain valid and the new fields fall back to their defaults if absent.
- The GUI chat history moved to the Gradio 5 messages format internally. This does not change any saved data; conversation history is stored separately in SQLite and is unaffected.

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
