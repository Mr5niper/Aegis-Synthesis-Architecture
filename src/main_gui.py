import os, asyncio, uuid, base64, signal
import sys # Added for dependency check and graceful shutdown
from pathlib import Path

from .core.config import load_config, ensure_dirs, ModelConfig
from .core.llm_async import AsyncLocalLLM
from .core.event_bus import EventBus
from .core.policy import PolicyManager
from .core.model_manager import ModelManager
from .core.user_profile import UserProfile
from .core.validate import validate_config # Added for config check
from .__version__ import get_version_info # Added for versioning

from .secure.crypto import load_or_create_keys, verify_key_b64, verify_key_fingerprint
from .secure.contacts import ContactManager
from .mesh.p2p import P2P
from .mesh.session import SessionManager
from .mesh.protocol_kairos import Kairos

from .memory.vector_store import LiteVectorStore
from .memory.conversation_store import ConversationMemory
from .memory.graph_crdt import LWWGraph
from .memory.inbox import MemoryInbox
from .memory.context_manager import ContextWindow # For Agent

from .learning.lora_trainer import LoRATrainer
from .learning.style_adapter import StyleAdapter

from .tools.registry_async import AsyncToolRegistry
from .agent.react_async import ReActAgent
from .services.session_exec import SessionExec
from .services.sync import SyncService

from .proactive.sentinel import Sentinel
from .proactive.curator import Curator

from .ui.gui import launch_gui
from .ui.consent import ConsentBroker

from .utils.download import download_file

MODEL_THREADS = max(2, os.cpu_count() or 2)
NEXUS_URL = os.getenv("AEGIS_NEXUS_URL", "ws://127.0.0.1:7861")

stop_events: list[asyncio.Event] = []

def check_optional_dependencies():
    """Check and warn about missing optional dependencies"""
    warnings = []
    
    try:
        import pyperclip
    except ImportError:
        warnings.append("⚠️ pyperclip not installed - clipboard monitoring disabled")
    
    try:
        import pygetwindow
    except ImportError:
        warnings.append("⚠️ pygetwindow not installed - window context disabled")
    
    if warnings:
        print("\n".join(warnings))
        print("Install optional dependencies: pip install pyperclip pygetwindow\n")

def install_shutdown(p2p, sentinel, curator):
    loop = asyncio.get_event_loop()
    stop = asyncio.Event()
    stop_events.append(stop)

    async def cleanup():
        print("\n🛑 Shutting down Aegis Synthesis...")
        
        # Signal all background tasks to stop
        for e in stop_events:
            e.set()
        
        # Close websocket
        if p2p and p2p.ws:
            try:
                await p2p.ws.close()
            except Exception:
                pass
        
        # Give background tasks time to cleanup
        await asyncio.sleep(1)
        print("✅ Shutdown complete")

    def _handler(*_):
        try:
            loop.create_task(cleanup())
        except Exception as e:
            print(f"Shutdown error: {e}")
            sys.exit(1)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            signal.signal(sig, lambda s, f: _handler())

# Name of the marker file Aegis drops inside its own onefile unpack dir, used
# to identify which _MEI* temp folders belong to THIS app (see cleanup below).
_AEGIS_MEIPASS_MARKER = ".aegis_meipass"

def _mark_own_meipass():
    """Drop a marker file in this run's onefile unpack dir so a later launch
    can recognize an Aegis temp folder and clean it up safely.
    """
    if not getattr(sys, "frozen", False):
        return
    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return
    try:
        with open(os.path.join(meipass, _AEGIS_MEIPASS_MARKER), "w") as f:
            f.write("aegis")
    except Exception:
        pass

def _cleanup_orphaned_meipass():
    """Remove leftover Aegis onefile temp dirs from previous hard-killed runs.

    In a onefile build the bootloader unpacks into a temporary _MEIxxxxxx
    folder and deletes it when the process exits normally. A hard kill (Task
    Manager, crash, power loss) skips that cleanup and orphans the folder.

    IMPORTANT: every PyInstaller onefile app on the system unpacks to a
    _MEIxxxxxx folder with no app name in it, so we must NOT delete by the
    _MEI* name alone - that would destroy other apps' running temp dirs. We
    only delete a folder if it contains OUR marker file (_AEGIS_MEIPASS_MARKER,
    written by _mark_own_meipass), and never the current process's own dir.
    """
    if not getattr(sys, "frozen", False):
        return
    import tempfile, shutil, glob
    current = getattr(sys, "_MEIPASS", None)
    current_norm = os.path.normcase(os.path.abspath(current)) if current else None
    temp_root = tempfile.gettempdir()
    for path in glob.glob(os.path.join(temp_root, "_MEI*")):
        # Skip the temp dir this running exe is using.
        if current_norm and os.path.normcase(os.path.abspath(path)) == current_norm:
            continue
        # Only touch folders we can prove are Aegis's, via our marker file.
        marker = os.path.join(path, _AEGIS_MEIPASS_MARKER)
        if not os.path.isfile(marker):
            continue
        # Guard against a CONCURRENTLY running Aegis instance: its unpack dir
        # also carries the marker, but a live instance holds its DLLs/pyd files
        # open so they cannot be deleted. Use rmtree WITHOUT ignore_errors: if
        # any file is locked the call raises partway and we abort for that dir,
        # leaving it intact rather than gutting a running instance. Only a fully
        # idle orphan (no open handles) deletes cleanly. ignore_errors is
        # deliberately NOT used here, precisely so locked dirs are left alone.
        try:
            shutil.rmtree(path)
        except Exception:
            # In use by a live instance, or a permission issue - leave it.
            pass

def main():
    # When running as a PyInstaller-built exe, the process working directory is
    # wherever the user launched from (e.g. C:\Windows\System32 for a shortcut),
    # NOT where Aegis.exe lives. Every path in this app (models/, data/*, keys,
    # config.yaml) is relative, so anchor the working directory to the exe's
    # folder. This makes the frozen app behave exactly like running from the
    # repo root: models download into <exe dir>\models, data into <exe dir>\data,
    # and config.yaml is read from beside the exe. Running from source is
    # unaffected (sys.frozen is not set).
    if getattr(sys, "frozen", False):
        os.chdir(Path(sys.executable).parent)

    # Mark this run's onefile unpack dir as ours, then sweep any Aegis temp
    # dirs orphaned by a previous hard-killed run. Only folders containing our
    # marker are removed, so other onefile apps' temp dirs are never touched.
    _mark_own_meipass()
    _cleanup_orphaned_meipass()

    check_optional_dependencies()
    
    cfg = load_config()

    # Validate config
    if issues := validate_config(cfg):
        print("\n".join(issues))
        if any("❌" in i for i in issues):
            print("\n❌ Fatal configuration errors. Exiting.")
            sys.exit(1)
    
    ensure_dirs(cfg)
    
    model_manager = ModelManager()
    
    # 1. Load Models and Download
    for model_cfg_data in cfg.models:
        model_cfg = ModelConfig(**model_cfg_data)
        mp = Path(model_cfg.path)
        if not mp.exists():
            print(f"Model '{model_cfg.name}' not found. Downloading...")
            download_file(model_cfg.url, mp, model_cfg.sha256 or "")
            
        llm_instance = AsyncLocalLLM(
            model_cfg.path, 
            n_ctx=model_cfg.ctx_size, 
            n_threads=MODEL_THREADS, 
            n_gpu_layers=model_cfg.n_gpu_layers
        )
        model_manager.register_model(model_cfg.name, llm_instance)

    bus = EventBus()

    PROACTIVE_ENV = os.getenv("AEGIS_PROACTIVE", "").strip()
    proactive_enabled = cfg.assistant.proactive_enabled and PROACTIVE_ENV != "0"

    policy = PolicyManager(
        allow_web_search=cfg.assistant.allow_web_search,
        proactive_enabled=proactive_enabled,
        allow_domains=cfg.assistant.allow_domains,
        quiet_hours=cfg.assistant.quiet_hours,
        suggestions_per_min=cfg.assistant.suggestions_per_min,
    )

    # Core Systems
    user_profile = UserProfile(cfg.user_profile.path)
    style_adapter = StyleAdapter(storage_path="data/user_data/style_patterns.json") # Added persistence path
    lora_trainer = LoRATrainer(cfg.learning.training_output_dir)

    kb = LiteVectorStore(cfg.paths.knowledge_base_db, cfg.embeddings.model_name)
    try:
        # Pre-warm embeddings to avoid first-lag
        _ = kb.model.encode(["warmup"], normalize_embeddings=True)
    except Exception:
        pass

    mem = ConversationMemory(cfg.paths.conversation_db)
    graph = LWWGraph(cfg.paths.memory_graph_db)
    inbox = MemoryInbox(cfg.paths.inbox_db)
    # context_window = ContextWindow(model_manager.get_active().n_ctx) # Not used directly in main_gui, but available

    peer_id = f"agent-{uuid.uuid4().hex[:6]}"
    ed_sk, ed_vk = load_or_create_keys(peer_id, cfg.paths.keys_dir)
    p2p = P2P(peer_id, NEXUS_URL, ed_sk)

    # Initialize background agents with the currently active model
    sentinel = Sentinel(model_manager.get_active(), bus, policy) 
    curator = Curator(model_manager.get_active(), bus, policy, graph, kb) 
    
    install_shutdown(p2p, sentinel, curator) # Updated shutdown call

    contacts = ContactManager(cfg.paths.contacts_db)
    def get_trusted_vk(pid: str):
        from nacl.signing import VerifyKey
        vk_b64 = contacts.get_verify_key(pid)
        return VerifyKey(base64.b64decode(vk_b64)) if vk_b64 else None

    session_manager = SessionManager(p2p, ed_sk, get_trusted_vk)
    kairos_protocol = Kairos(session_manager, contacts)
    sync_service = SyncService(graph, p2p)

    tools = AsyncToolRegistry(kb, cfg, peer_client=p2p)
    
    # Agent factory must fetch the current LLM model on demand
    def agent_factory():
        llm_current = model_manager.get_active()
        return ReActAgent(
            llm_current, tools, mem, kb, graph, cfg.assistant.system_prompt, 
            cfg.assistant.max_reasoning_steps, inbox=inbox,
            user_profile=user_profile, style_adapter=style_adapter,
            distill_facts=cfg.assistant.distill_facts
        )

    consent_broker = ConsentBroker()

    async def consent_cb(sender_id: str, session_id: str, consent_obj: dict) -> bool:
        req_id = f"{session_id}-{uuid.uuid4().hex[:6]}"
        await bus.publish("suggestions", {"type": "consent_request", "text": f"Collab request from {sender_id} (session {session_id})"})
        fut = consent_broker.create(req_id)
        await bus.publish("suggestions", {"type": "consent_request", "text": f"[APPROVE?] {sender_id} scope={consent_obj.get('scope')} req_id={req_id}"})
        try:
            decision = await asyncio.wait_for(fut, timeout=120)
            return decision
        except asyncio.TimeoutError:
            return False

    session_manager.on_consent_request = consent_cb

    session_exec = SessionExec(session_manager)
    session_exec.register_kb(kb)
    session_exec.register_config(cfg)

    async def start_background_tasks():
        # await p2p.connect()  # Disabled for single-user mode
        # asyncio.create_task(session_manager.start_maintenance())
        pass
        if proactive_enabled:
            asyncio.create_task(sentinel.run())
            asyncio.create_task(curator.run())

    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_background_tasks())

    async def subscribe_suggestions():
        q = asyncio.Queue()
        await bus.subscribe("suggestions", q.put)
        while True:
            event = await q.get()
            yield event.get("text", "...")

    identity = (peer_id, verify_key_b64(ed_vk), verify_key_fingerprint(ed_vk))
    model_names = model_manager.list_models()

    def switch_model_cb(name: str) -> str:
        ok = model_manager.switch_model(name)
        if not ok:
            return f"Unknown model: {name}"
        # Hot-swap LLM for background agents too
        new_llm = model_manager.get_active()
        sentinel.set_llm(new_llm)
        curator.set_llm(new_llm)
        return f"Switched to: {name}"

    launch_gui(
        agent_factory=agent_factory,
        subscribe_suggestions=subscribe_suggestions,
        contacts=contacts,
        kairos=kairos_protocol,
        inbox=inbox,
        graph=graph,
        sync_service=sync_service,
        broker=consent_broker,
        identity=identity,
        trainer=lora_trainer,
        style_adapter=style_adapter,
        model_names=model_names,
        on_switch_model=switch_model_cb,
        cfg=cfg,
        policy=policy,
    )

if __name__ == "__main__":
    main()