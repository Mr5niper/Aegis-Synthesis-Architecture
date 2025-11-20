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
    allow_code_exec: bool = False  # NEW

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

def load_config(path: str = "config.yaml") -> AppConfig:
    with open(path, "r") as f: data = yaml.safe_load(f)
    return AppConfig(**data)

def ensure_dirs(cfg: AppConfig):
    for path_str in cfg.paths.model_dump().values():
        Path(path_str).parent.mkdir(parents=True, exist_ok=True)
    
    # Ensure model directories exist
    for model_data in cfg.models:
        Path(model_data['path']).parent.mkdir(parents=True, exist_ok=True)

    Path(cfg.learning.training_output_dir).mkdir(parents=True, exist_ok=True)
    Path(cfg.user_profile.path).parent.mkdir(parents=True, exist_ok=True)
