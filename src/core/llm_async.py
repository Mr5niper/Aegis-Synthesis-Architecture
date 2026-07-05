# src/core/llm_async.py
import asyncio, threading
from typing import AsyncGenerator, Optional, List
from pathlib import Path
from llama_cpp import Llama

class AsyncLocalLLM:
    def __init__(self, model_path: str, n_ctx: int, n_threads: int, n_gpu_layers: int = 0, verbose: bool = False):
        mp = Path(model_path)
        if not mp.exists():
            raise FileNotFoundError(f"Model not found at {mp}")
        self._llm = Llama(
            model_path=str(mp),
            n_ctx=n_ctx,
            n_threads=n_threads,
            n_gpu_layers=n_gpu_layers,
            use_mmap=True,
            verbose=verbose,
        )
        # Serialize access across all calls to this instance.
        # llama.cpp is NOT reentrant: only one inference may touch self._llm at a time.
        self._sem = asyncio.Semaphore(1)
        self.n_ctx = n_ctx  # Expose context window size

    async def unload(self):
        """Free the underlying llama.cpp model and its GPU/CPU memory.

        Used by ModelManager when swapping models so only the active model is
        resident (the active model then gets the whole card, allowing a larger
        context). We acquire the same semaphore that guards inference FIRST, so
        unload cannot run while a generation is mid-flight (llama.cpp is not
        reentrant; freeing under an active call would crash). Once acquired, we
        drop the reference and force a collection; llama_cpp frees the native
        model (and its VRAM) when the Llama object is destroyed. Idempotent:
        a second call is a no-op.
        """
        async with self._sem:
            if getattr(self, "_llm", None) is None:
                return
            self._llm = None
            import gc
            gc.collect()

    def is_loaded(self) -> bool:
        return getattr(self, "_llm", None) is not None

    def _generate_blocking(self, prompt: str, max_tokens: int, temperature: float = 0.6, top_p: float = 0.9, top_k: int = 40, repeat_penalty: float = 1.1, stop: Optional[List[str]] = None) -> str:
        stop = stop or ["\nUser:", "\nSystem:"]
        out = self._llm(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            repeat_penalty=repeat_penalty,
            stop=stop,
            echo=False,
            stream=False,
        )
        return out["choices"][0]["text"]

    async def generate_async(self, *args, **kwargs) -> str:
        async with self._sem:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, lambda: self._generate_blocking(*args, **kwargs))

    async def _stream_tokens(
        self,
        run_stream,
        extract_token,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> AsyncGenerator[str, None]:
        """Shared streaming machinery for both raw-completion and chat-
        completion generation. run_stream() must return the llama.cpp
        streaming iterator; extract_token(chunk) must return the token text
        (or empty string) for a chunk. All the disconnect/cancel/semaphore
        safety lives here so both callers share it identically.
        """
        async with self._sem:
            q: asyncio.Queue = asyncio.Queue(maxsize=100)
            end_sentinel = object()
            loop = asyncio.get_event_loop()
            internal_stop = threading.Event()

            async def _offer(item):
                try:
                    q.put_nowait(item)
                    return True
                except asyncio.QueueFull:
                    pass
                for _ in range(50):  # ~5s total (50 x 0.1s)
                    if internal_stop.is_set() or (cancel_event and cancel_event.is_set()):
                        return False
                    await asyncio.sleep(0.1)
                    try:
                        q.put_nowait(item)
                        return True
                    except asyncio.QueueFull:
                        continue
                return False

            def producer():
                try:
                    for chunk in run_stream():
                        if internal_stop.is_set() or (cancel_event and cancel_event.is_set()):
                            break
                        token = extract_token(chunk)
                        if not token:
                            continue
                        try:
                            fut = asyncio.run_coroutine_threadsafe(_offer(token), loop)
                            if not fut.result():
                                break
                        except Exception:
                            break
                finally:
                    try:
                        asyncio.run_coroutine_threadsafe(_offer(end_sentinel), loop).result(timeout=5)
                    except Exception:
                        pass

            # NOT a daemon thread: must be joined before releasing the
            # semaphore so a second caller cannot re-enter llama.cpp while this
            # worker is still mid-inference (non-reentrant -> corruption).
            producer_thread = threading.Thread(target=producer)
            producer_thread.start()

            try:
                while True:
                    item = await q.get()
                    if item is end_sentinel:
                        break
                    if cancel_event and cancel_event.is_set():
                        internal_stop.set()
                        while True:
                            tail = await q.get()
                            if tail is end_sentinel:
                                break
                        break
                    yield item
            except GeneratorExit:
                internal_stop.set()
                raise
            finally:
                internal_stop.set()
                await loop.run_in_executor(None, producer_thread.join)

    async def stream_async(
        self,
        prompt: str, max_tokens: int, temperature: float, top_p: float, top_k: int, repeat_penalty: float,
        stop: Optional[List[str]] = None, cancel_event: Optional[asyncio.Event] = None
    ) -> AsyncGenerator[str, None]:
        """Raw-completion streaming (used by the JSON router, where we need
        tight control over stop strings)."""
        stop_tokens = stop or ["\nUser:", "\nSystem:"]
        def run_stream():
            return self._llm(
                prompt=prompt, max_tokens=max_tokens, temperature=temperature,
                top_p=top_p, top_k=top_k, repeat_penalty=repeat_penalty,
                stop=stop_tokens, echo=False, stream=True,
            )
        def extract(chunk):
            return chunk["choices"][0]["text"]
        async for tok in self._stream_tokens(run_stream, extract, cancel_event):
            yield tok

    async def stream_chat_async(
        self,
        messages: List[dict], max_tokens: int, temperature: float = 0.6, top_p: float = 0.9,
        top_k: int = 40, repeat_penalty: float = 1.1,
        stop: Optional[List[str]] = None, cancel_event: Optional[asyncio.Event] = None
    ) -> AsyncGenerator[str, None]:
        """Chat-completion streaming. Uses the model's built-in chat template
        (Llama/Mistral special tokens) via create_chat_completion, so the model
        sees the exact format it was trained on and stops at its own end-of-turn
        token instead of running on into a fake transcript. This is the correct
        home for the final answer generation."""
        def run_stream():
            return self._llm.create_chat_completion(
                messages=messages, max_tokens=max_tokens, temperature=temperature,
                top_p=top_p, top_k=top_k, repeat_penalty=repeat_penalty,
                stop=stop, stream=True,
            )
        def extract(chunk):
            # Chat streaming chunks carry the text in choices[0].delta.content
            # (absent on the role-priming first chunk and the final chunk).
            try:
                return chunk["choices"][0]["delta"].get("content", "") or ""
            except (KeyError, IndexError, AttributeError):
                return ""
        async for tok in self._stream_tokens(run_stream, extract, cancel_event):
            yield tok
