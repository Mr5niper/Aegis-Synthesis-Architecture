import yaml
from pydantic import BaseModel, Field
from pathlib import Path
from typing import List, Tuple, Dict, Any

class ModelConfig(BaseModel):
    name: str
    url: str; path: str; sha256: str = ""; ctx_size: int = 4096; n_gpu_layers: int = 0

class AssistantConfig(BaseModel):
    system_prompt: str; max_reasoning_steps: int = 5; allow_web_search: bool = True
    tool_timeout_sec: int = 20; proactive_enabled: bool = True
    quiet_hours: Tuple[int, int] = (23, 7); suggestions_per_min: int = 5
    allow_domains: List[str] = Field(default_factory=list)
    distill_facts: bool = True  # NEW: run fact-extraction generation after each turn
    allow_code_exec: bool = False

class UserProfileConfig(BaseModel):
    enabled: bool = True
    path: str = "data/user_data/profile.json"

class LearningConfig(BaseModel):
    lora_training: bool = False
    min_corrections_for_training: int = 50
    training_output_dir: str = "data/training"

class EmbeddingsConfig(BaseModel):
    model_name: str

class PathsConfig(BaseModel):
    conversation_db: str; knowledge_base_db: str; web_cache_db: str
    memory_graph_db: str; inbox_db: str; contacts_db: str; keys_dir: str

class AppConfig(BaseModel):
    models: List[Dict[str, Any]] # List of raw model configs
    assistant: AssistantConfig
    user_profile: UserProfileConfig
    learning: LearningConfig
    embeddings: EmbeddingsConfig
    paths: PathsConfig

def resolve_config_path(path: str = "config.yaml") -> str:
    """Return the path load_config/save_config should use.

    When running as a PyInstaller-built exe, the working directory is wherever
    the user launched from, not where the exe lives. Prefer config.yaml next to
    the executable (e.g. dist/config.yaml beside dist/Aegis.exe), NOT inside the
    temporary _MEIPASS extraction dir, so the user can edit it and edits persist.
    """
    import sys
    if getattr(sys, "frozen", False):
        exe_dir_cfg = Path(sys.executable).parent / "config.yaml"
        if exe_dir_cfg.is_file():
            return str(exe_dir_cfg)
    return path

def load_config(path: str = "config.yaml") -> AppConfig:
    path = resolve_config_path(path)
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    return AppConfig(**data)

def save_config(cfg: AppConfig, path: str = "config.yaml") -> str:
    """Write the config back to YAML, to the same file load_config reads.

    Returns the path written. Used by the in-app settings (e.g. the Web Access
    panel) so changes survive a restart. Reads the current file first and only
    overwrites the known top-level sections, so any comments-free extra keys a
    user added by hand are preserved as data (comments themselves are not kept
    by the YAML round-trip; this is documented for users in the settings panel).
    """
    path = resolve_config_path(path)
    data = cfg.model_dump()
    # quiet_hours is a tuple in the model; YAML should store it as a list.
    try:
        qh = data.get("assistant", {}).get("quiet_hours")
        if isinstance(qh, tuple):
            data["assistant"]["quiet_hours"] = list(qh)
    except Exception:
        pass
    with open(path, "w") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True, default_flow_style=False)
    return path

def update_web_access(cfg: AppConfig, policy, allow_all: bool, domains: List[str], path: str = "config.yaml") -> str:
    """Apply web-access settings live and persist them.

    allow_all=True is represented as an EMPTY allow_domains list, which both the
    policy and the fetch layer already treat as "allow any domain". Otherwise the
    provided domain list is used. The list is mutated IN PLACE on cfg so the
    already-constructed tool registry (which reads cfg.assistant.allow_domains at
    call time) sees the change immediately, and the policy copy is updated too.
    Returns the saved file path.
    """
    cleaned = [] if allow_all else _clean_domains(domains)
    # Mutate in place (do not rebind) so shared references stay valid.
    cfg.assistant.allow_domains[:] = cleaned
    if policy is not None:
        policy.allow_domains = cleaned
    return save_config(cfg, path)

def _clean_domains(domains: List[str]) -> List[str]:
    """Normalize a user-entered domain list: strip scheme/paths/whitespace,
    drop blanks and duplicates, keep bare hostnames like "github.com"."""
    out = []
    for d in domains or []:
        d = (d or "").strip()
        if not d:
            continue
        # Strip a scheme if the user pasted a full URL.
        if "://" in d:
            d = d.split("://", 1)[1]
        # Strip any path/query after the host.
        d = d.split("/", 1)[0].split("?", 1)[0]
        # Strip a leading "www." for consistency (endswith match still works).
        d = d.strip().lower()
        if d and d not in out:
            out.append(d)
    return out

def ensure_dirs(cfg: AppConfig):
    for path_str in cfg.paths.model_dump().values():
        Path(path_str).parent.mkdir(parents=True, exist_ok=True)

    # Ensure model directories exist
    for model_data in cfg.models:
        Path(model_data['path']).parent.mkdir(parents=True, exist_ok=True)

    Path(cfg.learning.training_output_dir).mkdir(parents=True, exist_ok=True)
    Path(cfg.user_profile.path).parent.mkdir(parents=True, exist_ok=True)
