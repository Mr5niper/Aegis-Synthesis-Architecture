# src/main_headless.py
import os, asyncio, uuid, base64
from pathlib import Path
from .core.config import load_config, ensure_dirs, ModelConfig
from .core.llm_async import AsyncLocalLLM
from .secure.crypto import load_or_create_keys
from .secure.contacts import ContactManager
from .mesh.p2p import P2P
from .mesh.session import SessionManager
from .mesh.protocol_kairos import Kairos
from .memory.vector_store import LiteVectorStore
from .memory.conversation_store import ConversationMemory
from .memory.graph_crdt import LWWGraph
from .memory.inbox import MemoryInbox
from .tools.registry_async import AsyncToolRegistry
from .agent.react_async import ReActAgent
from .services.session_exec import SessionExec
from .services.sync import SyncService
from .utils.download import download_file
from .core.model_manager import ModelManager
from .core.user_profile import UserProfile
from .learning.style_adapter import StyleAdapter # Added for ReActAgent

MODEL_THREADS = max(2, os.cpu_count() or 2)
NEXUS_URL = os.getenv("AEGIS_NEXUS_URL", "ws://127.0.0.1:7861")

async def main_async():
    cfg = load_config()
    ensure_dirs(cfg)
    
    model_manager = ModelManager()
    
    # Load Models and Download
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

    llm = model_manager.get_active()
    
    kb = LiteVectorStore(cfg.paths.knowledge_base_db, cfg.embeddings.model_name)
    mem = ConversationMemory(cfg.paths.conversation_db)
    graph = LWWGraph(cfg.paths.memory_graph_db)
    inbox = MemoryInbox(cfg.paths.inbox_db)

    user_profile = UserProfile(cfg.user_profile.path) # For prompt generation
    style_adapter = StyleAdapter() # For prompt generation

    peer_id = f"agent-{uuid.uuid4().hex[:6]}"
    ed_sk, ed_vk = load_or_create_keys(peer_id, cfg.paths.keys_dir)
    p2p = P2P(peer_id, NEXUS_URL, ed_sk)

    contacts = ContactManager(cfg.paths.contacts_db)
    def get_trusted_vk(pid: str):
        from nacl.signing import VerifyKey
        vk_b64 = contacts.get_verify_key(pid)
        return VerifyKey(base64.b64decode(vk_b64)) if vk_b64 else None

    sessions = SessionManager(p2p, ed_sk, get_trusted_vk)
    kairos = Kairos(sessions, contacts)
    sync = SyncService(graph, p2p)
    tools = AsyncToolRegistry(kb, cfg, peer_client=p2p)
    
    agent = ReActAgent(
        llm, tools, mem, kb, graph, cfg.assistant.system_prompt, 
        cfg.assistant.max_reasoning_steps, inbox=inbox,
        user_profile=user_profile, style_adapter=style_adapter
    )

    async def consent_cb(sender_id: str, session_id: str, consent_obj: dict) -> bool:
        # Headless mode: deny by default or implement a webhook to approve remotely
        return False
    sessions.on_consent_request = consent_cb

    SessionExec(sessions).register_kb(kb)

    await p2p.connect()
    asyncio.create_task(sessions.start_maintenance())

    print(f"[Headless] {peer_id} online. Nexus={NEXUS_URL}. Press Ctrl+C to stop.")
    while True:
        await asyncio.sleep(3600)

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()