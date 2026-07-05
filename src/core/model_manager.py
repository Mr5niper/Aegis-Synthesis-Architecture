# src/core/model_manager.py
import asyncio
from typing import Dict, Optional, Callable, Any
from .llm_async import AsyncLocalLLM


class ModelManager:
    """Manage multiple models with LAZY, ONE-AT-A-TIME loading.

    Only the ACTIVE model is resident in memory at any moment. This is a
    deliberate change from keeping every model loaded at once: on a GPU build
    all resident models share the card's VRAM, so keeping several loaded forces
    each into a small context to avoid running out of device memory. By loading
    only the model in use, the active model gets the whole card and can run a
    much larger context. The trade is a few seconds of load time when the user
    switches models, which is acceptable for a deliberate switch.

    Models are registered as SPECS (a name plus a zero-argument builder that
    constructs the AsyncLocalLLM when needed), not as pre-built instances. The
    active instance is built on first use and torn down on switch.

    Concurrency: a single asyncio.Lock (_swap_lock) serializes "get the active
    model" against "switch the model" so a swap cannot free a model while a
    caller is about to use it, and two swaps cannot interleave. The per-model
    AsyncLocalLLM.unload() additionally waits for any in-flight inference on
    that instance before freeing it, so a background agent mid-generation is
    never pulled out from under.
    """

    def __init__(self):
        # name -> zero-arg callable returning a fresh AsyncLocalLLM
        self._builders: Dict[str, Callable[[], AsyncLocalLLM]] = {}
        self._active: Optional[str] = None
        self._instance: Optional[AsyncLocalLLM] = None  # the one resident model
        self._swap_lock = asyncio.Lock()

    def register_model(self, name: str, builder: Callable[[], AsyncLocalLLM]):
        """Register a model by name and a builder that constructs it on demand.

        Nothing is loaded here; the model is built lazily on first get_active().
        """
        self._builders[name] = builder
        if self._active is None:
            self._active = "default" if "default" in self._builders else name

    async def get_active(self) -> AsyncLocalLLM:
        """Return the active model, building it (and only it) on first use.

        Held under the swap lock so a concurrent switch cannot free the
        instance between building and returning it.
        """
        if not self._builders:
            raise ValueError("No models registered.")
        async with self._swap_lock:
            if self._active not in self._builders:
                # Active name no longer valid; fall back to any registered name.
                self._active = next(iter(self._builders.keys()))
            if self._instance is None or not self._instance.is_loaded():
                self._instance = self._builders[self._active]()
            return self._instance

    async def switch_model(self, name: str) -> bool:
        """Switch the active model: unload the current one, then lazily build
        the new one on the next get_active(). Returns False for unknown names.

        The unload waits for any in-flight inference on the old instance (via
        AsyncLocalLLM.unload acquiring the inference semaphore), so this is safe
        even while a background agent is generating.
        """
        if name not in self._builders:
            return False
        async with self._swap_lock:
            if name == self._active and self._instance is not None:
                return True  # already active and loaded
            old = self._instance
            self._instance = None
            self._active = name
            if old is not None:
                try:
                    await old.unload()
                except Exception:
                    # Even if teardown hiccups, we have dropped our reference;
                    # the native model frees when the object is collected.
                    pass
        return True

    def active_name(self) -> str:
        return self._active or ""

    def list_models(self) -> list:
        return list(self._builders.keys())
