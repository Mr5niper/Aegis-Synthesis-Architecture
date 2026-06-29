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

    async def stream_async(
        self,
        prompt: str, max_tokens: int, temperature: float, top_p: float, top_k: int, repeat_penalty: float,
        stop: Optional[List[str]] = None, cancel_event: Optional[asyncio.Event] = None
    ) -> AsyncGenerator[str, None]:
        async with self._sem:
            q: asyncio.Queue = asyncio.Queue(maxsize=100)
            stop_tokens, end_sentinel = stop or ["\nUser:", "\nSystem:"], object()
            loop = asyncio.get_event_loop()

            def producer():
                try:
                    for chunk in self._llm(
                        prompt=prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        top_p=top_p,
                        top_k=top_k,
                        repeat_penalty=repeat_penalty,
                        stop=stop_tokens,
                        echo=False,
                        stream=True,
                    ):
                        if cancel_event and cancel_event.is_set():
                            break
                        token = chunk["choices"][0]["text"]
                        asyncio.run_coroutine_threadsafe(q.put(token), loop)
                finally:
                    asyncio.run_coroutine_threadsafe(q.put(end_sentinel), loop)

            # NOT a daemon thread. We MUST join it before releasing the semaphore,
            # otherwise a second caller could grab the semaphore and re-enter
            # llama.cpp while this thread is still mid-inference -> corruption/crash.
            producer_thread = threading.Thread(target=producer)
            producer_thread.start()

            try:
                while True:
                    item = await q.get()
                    if item is end_sentinel:
                        break
                    if cancel_event and cancel_event.is_set():
                        # Drain until the producer reaches its own cancel check and
                        # emits the sentinel, so we never leave it running.
                        while True:
                            tail = await q.get()
                            if tail is end_sentinel:
                                break
                        break
                    yield item
            finally:
                # Wait for the worker to fully exit llama.cpp before the
                # `async with self._sem` block releases the lock.
                await loop.run_in_executor(None, producer_thread.join)
