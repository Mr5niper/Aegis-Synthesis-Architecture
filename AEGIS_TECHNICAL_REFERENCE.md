# Aegis Synthesis Architecture — Technical Reference Manual

**Version:** 1.0  
**Date:** November 2025  
**Status:** Production Ready

---

## 1. Executive Summary

Aegis Synthesis Architecture (ASA) is a sovereign, local-first personal AI system that combines:

- Local LLM inference with multi-model hot-swapping
- Retrieval-augmented generation (RAG) with a local vector store
- Proactive agents (Sentinel/Curator) running asynchronously
- Secure end-to-end encrypted (E2EE) P2P collaboration with explicit consent
- Memory Inbox with user approval and CRDT-backed distributed fact synchronization
- Adaptive personalization (user profile, style adaptation), and an offline LoRA training pipeline
- A Gradio-based GUI and a headless/server mode
- Cross-platform packaging via PyInstaller

ASA is designed for privacy, reliability, and extensibility. It treats a single user's devices as a sovereign federation and optionally allows trusted inter-user collaboration sessions with verifiable consent tokens. Its architecture emphasizes: minimal dependencies, local storage via SQLite (WAL), robust async with cancellation, and clear operational controls and policies.

---

## 2. System Goals and Non-Goals

### Goals

- **Private by default**: local inference, local data, no third-party API required
- **Extensible**: tool registry, sandboxed code exec (opt-in), vector store, plugin-friendly
- **Safe and controlled**: policy gating (domain allowlist, quiet hours), explicit consent for collaboration, Memory Inbox approvals
- **Distributed**: secure peer-to-peer sessions with ephemeral session keys
- **Operationally friendly**: deterministic builds, health endpoints, offline packaging, WAL-hardened SQLite

### Non-Goals

- Cloud dependency or centralized service. The "Nexus" server is a stateless relay that sees only ciphertext
- Full-blown multi-tenant SaaS. ASA's collaboration is explicitly consent-driven between trusted peers
- Perfect sandboxing/security for arbitrary code. The `code_exec` tool is best-effort and opt-in only

---

## 3. High-Level Capabilities

### Chat Assistant
- Local LLM with async token streaming, cancellation, and tool-use via JSON schema

### RAG System
- Lite SQLite vector store
- Ingest arbitrary text or URLs
- Semantic search with sentence-transformers

### Proactive Agents
- **Sentinel**: monitors clipboard/window title (if available) and suggests actions
- **Curator**: background knowledge suggestions and potential KB actions

### Collaboration
- E2EE P2P via a local relay (Nexus)
- Consent tokens (Ed25519 signed) and ephemeral session keys (Curve25519)
- Session-scoped delegation of tasks and shared context

### Memory
- Conversation history (SQLite)
- CRDT LWW memory graph (distributed facts)
- Memory Inbox requiring user approval, with an audit log

### Personalization
- UserProfile to adjust prompt style
- StyleAdapter learns communication patterns with persistence
- LoRA correction logging and training dataset preparation with a UI viewer

### UI
- Gradio web app with chat, suggestions, model switcher, memory inbox, consent panel, training viewer, identity panel, contacts/collaboration panel
- Headless/server mode for non-interactive nodes

### Build and Ops
- PyInstaller packaging
- Health endpoint for the Nexus relay
- Config validation and optional-dependency checks at startup
- WAL + busy_timeout for all SQLite stores

---

## 4. Architecture Overview

### 4.1 Layers and Key Modules

#### Core (`src/core`)
- `config.py`: Pydantic-driven configuration (models, assistant behavior, paths)
- `llm_async.py`: Async wrapper around llama-cpp for blocking API with a semaphore to avoid concurrency issues, providing generate and stream
- `model_manager.py`: Multiple model management with active switching
- `policy.py`: Rate limiting, quiet hours, web domain allowlist
- `prompt.py`/`schemas.py`: Prompt builders and pydantic schemas for tool-calls, events
- `validate.py`: Configuration validation checks
- `user_profile.py`: Personal preferences used in prompt augmentation

#### Agent (`src/agent`)
- `react_async.py`: ReAct loop using JSON tool calls, with incremental observation and final synthesis, streaming token output, Memory Inbox distillation

#### Memory (`src/memory`)
- `vector_store.py`: SQLite + sentence-transformers embeddings; compact RAG with normalized cosine similarity
- `conversation_store.py`: SQLite conversation storage
- `graph_crdt.py`: LWW CRDT representing user facts, with SQLite persistence and application of CRDT ops
- `inbox.py`: Memory Inbox pending approvals (SQLite)
- `context_manager.py`: Token-aware conversation compression/summarization (heuristic)

#### Tools (`src/tools`)
- `registry_async.py`: Tool registry including now, calc (safe eval), search_web, fetch_url, kb_add, kb_query, ingest_url, code_exec (opt-in)
- `sandbox.py`: Best-effort Python sandbox (isolated process, posix resource limits if available)
- `session_tools.py`: Session-sharing helpers (kept minimal)

#### Internet (`src/internet`)
- `search.py`: DuckDuckGo search
- `fetch.py`: Robust HTML fetch/clean with allowlist gating
- `cache.py`: SQLite-based response cache (WAL enabled)

#### Mesh (`src/mesh`)
- `p2p.py`: WebSocket-based P2P client with E2EE (box encryption), pubkey announce
- `session.py`: Ephemeral session management for secure collaboration (consent tokens, ephemeral keys, session messaging)
- `protocol_kairos.py`: High-level wrapper for initiating a collaboration session

#### Proactive (`src/proactive`)
- `sentinel.py`: Clipboard/window monitor with suggestions; supports updating LLM after model switch
- `curator.py`: Background suggestions over knowledge graph; also supports dynamic LLM update

#### Secure (`src/secure`)
- `crypto.py`: Key generation, ed25519↔curve25519 conversion, basic b64 helpers, fingerprints
- `consent.py`: Consent token (versioned, signed, scope, exp) with verify/allows functions
- `contacts.py`: SQLite contact storage with status and verify key

#### Services (`src/services`)
- `session_exec.py`: Restrictive execution of allowed tools upon session requests
- `sync.py`: Broadcast CRDT ops and apply inbound ops to the memory graph

#### UI (`src/ui`)
- `gui.py`: Gradio app with chat, model switch, suggestions, inbox approvals, collaboration requests, identity panel, training viewer
- `contacts_panel.py`: Manage trusted contacts and invitations
- `identity_panel.py`: Display verify key base64 and fingerprint for TOFU
- `consent.py`: ConsentBroker to handle interactive approvals

#### Utils (`src/utils`)
- `download.py`: First-run model download with optional SHA256 validation
- `db.py`: SQLite pragmas for WAL/synchronous/busy_timeout

#### Entry Points
- `main_gui.py`: GUI orchestration; model loading; config validation; shutdown hooks; background tasks; UI launch; model switching updates sentinel/curator LLM
- `main_headless.py`: Headless server-mode node; denies consent by default
- `nexus_server.py`: Stateless WebSocket relay; peer updates; routing; health endpoints

### 4.2 Data Plane vs Control Plane

**Data Plane:**
- LLM prompts/responses
- Embedding computation
- Tool execution
- RAG context retrieval
- CRDT state

**Control Plane:**
- Configuration
- Policy gating
- Model switching
- Consent flow
- Session management
- UI events
- Shutdown and lifecycle

---

## 5. Protocols and Data Flows

### 5.1 Local Chat Flow (ReAct)

1. User enters message in UI
2. Orchestrator builds system prompt from:
   - Assistant system prompt + user profile + style adaptation (analyzed from recent messages)
   - Recent conversation history (from DB)
   - RAG context (vector store)
3. ReAct loop:
   - LLM routes with low temperature using tool schema; returns either JSON tool call or direct answer
   - If tool call:
     - Registry executes the tool (async) with timeouts and safe eval for calc
     - Internet calls obey allowlist
     - Returns observation
     - Observations appended; loop continues (bounded by `max_reasoning_steps`)
   - If final answer, stream tokens to UI; store transcript and optionally distill facts into Memory Inbox

### 5.2 Proactive Agents

**Sentinel:**
- Polls clipboard/window title (if available)
- Generates a single actionable suggestion with a minimal prompt
- Emits to EventBus and UI

**Curator:**
- Periodically examines memory graph facts
- Suggests a single next action or idea
- Emits to EventBus and UI

### 5.3 Collaboration Session (Kairos)

**Precondition:** Both peers are trusted (contacts with verify key recorded)

**Flow:**
1. Initiator sends an invite with:
   - Signed ConsentToken (issuer, subject, scope like allowed tools/args, expiry)
   - Ephemeral public key for session channel
2. Recipient validates token (verify signature; not expired; scope OK) and prompts user via ConsentBroker in UI
3. Accept:
   - Generates ephemeral keypair; sends accept with its ephemeral pubkey
   - Both sides derive an E2EE Box. Session established
4. Messaging:
   - Session messages are encrypted with the session box (separate from P2P envelope encryption)
   - Task requests: limited toolset (kb_query, fetch_url, search_web by default)
   - Responses returned via session channel
5. Closure:
   - Sessions pruned by maintenance if stale; ephemeral keys discarded

### 5.4 Memory Inbox and CRDT Sync

- Distilled facts from chat are not auto-committed
- User approves via Inbox UI; on approval:
  - Relation upserted in the local LWW CRDT and appended to audit JSONL
  - CRDT ops broadcast to peers for eventual consistency (apply-op merges by timestamp)

---

## 6. Security Model

- **Local-first**: no third-party LLM APIs required
- **E2EE P2P**: The Nexus relay sees only ciphertext and routing metadata (peer IDs)
- **Consent Tokens**: Signed by Ed25519 key; contain scope and expiry; subject must match recipient peer; verified on receipt
- **Ephemeral Session Keys**: Curve25519; session-scoped; only valid for session lifetime
- **Tool Policies**:
  - Domain allowlist for web fetching
  - Timeouts for tools to avoid hangs
  - Safe eval for calc; code_exec disabled by default (requires `allow_code_exec: true` + env `AEGIS_ENABLE_CODE_EXEC=1`)
- **Privacy**:
  - Memory Inbox ensures no automatic personal fact commits
  - UserProfile/Style patterns stored locally in `data/user_data`

---

## 7. Storage and Schema

### 7.1 SQLite Configuration

- WAL mode enabled; synchronous NORMAL; busy_timeout=5000ms across all stores to reduce "database is locked" issues
- **DB files:**
  - `conversations`: stores session chat turns and context
  - `knowledge_base_db`: vector store (docs table with text and float32 embedding blobs)
  - `memory_graph_db`: relations table with key (src|rel|dst), ts
  - `inbox_db`: pending facts for approval
  - `web_cache_db`: url → text with TTL
  - `contacts_db`: verify keys and trust status

### 7.2 Vector Store

- Embeddings by sentence-transformers (all-MiniLM-L6-v2)
- Cosine similarity via dot product on normalized embeddings
- Single-table docs schema with BLOB embeddings and indexes by source

### 7.3 CRDT

- LWWGraph where each relation is keyed by `(src|rel|dst)` and tagged with a timestamp `ts`
- **Ops:**
  - `upsert_relation {op, src, rel, dst, ts}`; accept op iff `ts >= existing ts`

---

## 8. Model Management and Rationale

- **llama-cpp-python** for local inference:
  - Deterministic, CPU-first; optional GPU offload via `n_gpu_layers`
  - Async wrapper ensures semaphore-guarded access to prevent concurrency-related issues
- **Multi-model Manager:**
  - Register "default" and "large" or more; actively switchable in UI
  - Sentinel/Curator update LLM via `set_llm()` instantly upon switch

**Why this approach:**
- Keeps footprint manageable; no giant server side
- Gives engineers control over tradeoffs: RAM vs speed vs accuracy
- Avoids dependency on networked inference

---

## 9. Build, Packaging, and Deployment

### 9.1 Developer Setup

- Python 3.13+ recommended
- Create and activate virtualenv; `pip install -r requirements.txt`
- Optional OS-specific deps (commented in requirements.txt) if you need active window titles on Windows/macOS

### 9.2 Running Locally

**Nexus relay (stateless router):**
```bash
uvicorn src.nexus_server:app --host 0.0.0.0 --port 7861
```
- Health: `GET /health`; `GET /`

**Agent GUI:**
```bash
python -m src.main_gui
```
- `AEGIS_NEXUS_URL=ws://<relay-ip>:7861` to point to remote relay
- `AEGIS_PROACTIVE=0` to disable background agents

**Agent headless:**
```bash
python -m src.main_headless
```
- Denies collaboration by default

### 9.3 Packaging

**PyInstaller one-folder build:**
```bash
python build_executable.py
```
- `dist/Aegis/` contains the binary and bundled assets
- `assistant_gui.spec` includes hiddenimports for gradio/fastapi/uvicorn/nacl, and data directories

### 9.4 Configuration

- `config.yaml` drives:
  - **models**: list with name/path/url/ctx_size/n_gpu_layers
  - **assistant**: system behavior (max steps, proactive, timeouts, allowlist, allow_code_exec)
  - **user_profile**, learning paths
  - **paths** for all SQLite DBs
- At startup:
  - Config validated; directories ensured; optional deps checked

---

## 10. UI, Usage, and Operator Workflows

### 10.1 Identity and Contacts

**Identity panel shows:**
- Peer ID, verify key (base64), fingerprint (short sha256)

**Contacts panel:**
- Add contact (alias, peer_id, verify key base64)
- Trust contact (after out-of-band fingerprint confirmation)
- Invite to collaborate (scope JSON, redacted context)

### 10.2 Collaboration Consent

- Incoming request appears in Suggestions; copy the Request ID to Collaboration Requests panel and Approve/Deny
- After approval, you can session-delegate allowed tools

### 10.3 Memory Inbox

- Approved facts are committed to the CRDT and broadcast
- Append-only audit JSONL in `data/user_data/inbox_approved.jsonl`

### 10.4 Models

- Drop-down to switch active model; status shows success; Sentinel/Curator are re-pointed automatically

### 10.5 Feedback/Corrections

- Rate answers; log "Needs Correction" into LoRA corrections file
- Training viewer shows progress; after threshold, dataset generated and training script displayed

### 10.6 Proactive Agents

- Suggestions feed shows Sentinel or Curator prompts
- Use "Use Last Suggestion" to insert a suggestion into the message box

---

## 11. Performance, Scaling, and Tuning

- **LLM threads**: set `n_threads` to CPU count for throughput; adjust `n_gpu_layers` if compiled with GPU/MPS/Metal to offload layers
- **Sentence-transformers**: warm-up step avoids first inference latency
- **Vector store**: suitable up to tens of thousands of chunks. For larger corpora, replace with FAISS (not included by default to keep packaging simpler)
- **SQLite WAL**: store DBs on SSD; avoid networked file systems for concurrency

---

## 12. Security Hardening

- Leave `code_exec` disabled unless you explicitly enable: `assistant.allow_code_exec: true` + `AEGIS_ENABLE_CODE_EXEC=1`
- Maintain a strict domain allowlist in `assistant.allow_domains`
- Use TOFU to trust contacts by verifying fingerprints out-of-band
- Keep the Nexus relay private to your environment; all content is still encrypted, but treat peer IDs as metadata

---

## 13. Testing and CI Ideas

**Unit tests for:**
- Tool registry in isolation (calc, search, fetch with mock HTTP)
- CRDT op application
- Consent token verification/allows

**Integration smoke test:**
- Start Nexus; run two headless nodes; script an invitation; auto-approve; delegate kb_query; verify response; approve a fact; verify CRDT sync appears on peer

**Performance tests:**
- Evaluate token throughput and end-to-end latency per model

---

## 14. Troubleshooting

**GUI hangs or slow:**
- Verify llama-cpp model loads; adjust `n_threads`; ensure not over-subscribing CPU

**"database is locked":**
- WAL + busy_timeout are applied; if you push heavy parallelism, serialize operations or isolate per-DB operations; ensure DBs are not on NFS

**Clipboard/window titles missing:**
- Install optional deps pyperclip, pygetwindow; on Windows, consider pywin32; on macOS, PyObjC frameworks

**No peers appear:**
- Check Nexus `/health`; ensure agent uses correct `AEGIS_NEXUS_URL`; confirm firewall rules

**Collaboration approval stuck:**
- Ensure Request ID is pasted exactly; check console logs; verify ConsentBroker resolves

---

## 15. Design Rationale

**Local-first + SQLite:**
- Predictable, low-ops footprint. WAL config + busy timeout reduces lock thrash without distributed DB complexity

**Async everything:**
- LLM streaming, tools, web requests, and background agents are non-blocking; UI stays responsive and cancellable

**Explicit consent & Memory Inbox:**
- Prevents accidental data propagation; users approve what becomes "memory"

**P2P with Zero Trust Relay:**
- Keeps all content encrypted and avoids central data stores; introduces only a lightweight "router"

**Simplicity over frameworks:**
- Avoid large orchestration frameworks; clear Python modules are easier to audit and package

---

## 16. Extensibility and Plugin Approach

**Tools:**
- Add new tools by extending `registry_async`. Use pydantic schemas for args if desired. Gate network tools with allowlist

**Models:**
- Add more models to config; register automatically; update UI dropdown

**APIs:**
- Expose local HTTP endpoints for automation (not included by default)

**Voice:**
- Add STT/TTS building blocks (e.g., faster-whisper, pyttsx3) gated behind config

---

## 17. File and Module Index

- `src/main_gui.py`: Primary entry; loads config, models; starts UI and background tasks; installs shutdown, validates config
- `src/core/*.py`: Configuration, prompts, schemas, policies, model management, validation, version
- `src/agent/react_async.py`: ReAct loop implementation with tool calling
- `src/tools/*.py`: Tool registry; sandboxed code exec; session tools
- `src/memory/*.py`: All persistence stores and CRDT implementation
- `src/mesh/*.py`: P2P E2EE client; ephemeral session and protocol wrapper
- `src/proactive/*.py`: Sentinel and Curator background agents with dynamic LLM updates
- `src/ui/*.py`: Gradio UI and panels
- `src/internet/*.py`: Web search/fetch + cache
- `src/secure/*.py`: Keys, consent tokens, contacts
- `src/services/*.py`: Session execution and CRDT synchronization
- `src/utils/*.py`: Common helpers, including SQLite configuration and model download
- `src/nexus_server.py`: Stateless relay with peer updates and health

---

## 18. Appendix

### 18.1 Sample Consent Token JSON

```json
{
  "version": "1",
  "session_id": "ses-abc12345",
  "initiator_id": "agent-1a2b3c",
  "recipient_id": "agent-9f8e7d",
  "scope": {
    "tools": ["kb_query", "search_web"],
    "args": {"max_k": 3}
  },
  "context_hash": "a3a0aef...e9c",
  "exp": 1735689600,
  "_sig": "base64_signature_here"
}
```

### 18.2 Nexus Health Check

**`GET /health`:**
- Returns JSON with `connected_peers` and `peer_ids`

**`GET /`:**
- Returns basic service metadata

### 18.3 Configuration Validation

- Errors (❌) will abort
- Warnings (⚠️) show potential misconfigurations but allow start

---

## 19. Commands Reference

**Start relay:**
```bash
uvicorn src.nexus_server:app --host 0.0.0.0 --port 7861
```

**Start GUI agent:**
```bash
AEGIS_NEXUS_URL=ws://<relay-ip>:7861 python -m src.main_gui
```

**Start headless node:**
```bash
python -m src.main_headless
```

**Disable proactive:**
```bash
AEGIS_PROACTIVE=0 python -m src.main_gui
```

**Enable code_exec:**
- Set `assistant.allow_code_exec: true` in config.yaml and `export AEGIS_ENABLE_CODE_EXEC=1`

**Build executable:**
```bash
python build_executable.py
```

---

## 20. Conclusion

ASA is designed to be a trustworthy, capable personal AI platform: private by default, powerful when federated, and friendly to operate. Engineers can manage the deployment as a local desktop app or a headless service, grow it with additional tools and models, and rely on a strong security posture with explicit consent-driven collaboration.

This document should be sufficient to build, operate, extend, and reason about the system confidently.

---

**Document Information:**

**Title:** Aegis Synthesis Architecture — Technical Reference Manual  
**Version:** 1.0  
**Date:** November 2025  
**Status:** Alpha (Testing and Updates are welcome)

---
