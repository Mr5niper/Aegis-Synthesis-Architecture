# src/core/model_manager.py
from typing import Dict, Optional
from .llm_async import AsyncLocalLLM

class ModelManager:
    """Manage multiple models and switch between them safely."""
    def __init__(self):
        self.models: Dict[str, AsyncLocalLLM] = {}
        self._active: Optional[str] = None

    def register_model(self, name: str, model: AsyncLocalLLM):
        self.models[name] = model
        # If no active model yet, prefer "default" else first registered
        if self._active is None:
            self._active = "default" if "default" in self.models else name

    def switch_model(self, name: str) -> bool:
        if name in self.models:
            self._active = name
            return True
        return False

    def get_active(self) -> AsyncLocalLLM:
        if not self.models:
            raise ValueError("No LLMs registered.")
        if self._active not in self.models:
            # Fallback to any available model
            self._active = next(iter(self.models.keys()))
        return self.models[self._active]

    def active_name(self) -> str:
        return self._active or ""
    
    def list_models(self) -> list:
        return list(self.models.keys())