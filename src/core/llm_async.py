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
            # Internal stop flag, separate from the external Stop-button
            # cancel_event. It is set if the consumer side is torn down (client
            # disconnect, GeneratorExit) so the producer stops at its next token
            # instead of running to max_tokens while holding the semaphore.
            internal_stop = threading.Event()

            async def _offer(item):
                # Enqueue without blocking the producer thread indefinitely.
                # If the queue is full we wait briefly for the consumer to drain
                # (normal slowness), but give up after a short timeout so a gone
                # consumer cannot wedge the producer. Returns False to tell the
                # producer to stop.
                try:
                    q.put_nowait(item)
                    return True
                except asyncio.QueueFull:
                    pass
                # Queue full: wait up to a bit for space, rechecking stop.
                for _ in range(50):  # ~5s total (50 x 0.1s)
                    if internal_stop.is_set() or (cancel_event and cancel_event.is_set()):
                        return False
                    await asyncio.sleep(0.1)
                    try:
                        q.put_nowait(item)
                        return True
                    except asyncio.QueueFull:
                        continue
                # Still full after the wait: consumer is gone, stop.
                return False

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
                        if internal_stop.is_set() or (cancel_event and cancel_event.is_set()):
                            break
                        token = chunk["choices"][0]["text"]
                        # Use put_nowait via the loop. If the consumer has gone
                        # away the queue can fill; a blocking put would wedge this
                        # thread so it never re-checks the stop flags. On a full
                        # queue we drop the token and stop instead of blocking.
                        try:
                            fut = asyncio.run_coroutine_threadsafe(_offer(token), loop)
                            if not fut.result():
                                break
                        except Exception:
                            break
                finally:
                    # Best-effort end sentinel; ignore if the loop/queue is gone.
                    try:
                        asyncio.run_coroutine_threadsafe(_offer(end_sentinel), loop).result(timeout=5)
                    except Exception:
                        pass

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
                        # Stop button pressed: tell the producer to stop now, then
                        # drain until it emits the sentinel so it is never left
                        # running.
                        internal_stop.set()
                        while True:
                            tail = await q.get()
                            if tail is end_sentinel:
                                break
                        break
                    yield item
            except GeneratorExit:
                # The consumer was torn down (client disconnected, or Gradio
                # abandoned the stream). Signal the producer to stop at its next
                # token rather than generating all max_tokens while we hold the
                # semaphore. Without this the join below blocks for the full
                # generation (up to ~minutes on CPU), freezing every other
                # model call behind the lock.
                internal_stop.set()
                raise
            finally:
                # Make sure the producer is told to stop, then wait for it to
                # fully exit llama.cpp before the `async with self._sem` block
                # releases the lock. internal_stop is idempotent; setting it here
                # covers normal completion, cancel, and disconnect paths.
                internal_stop.set()
                await loop.run_in_executor(None, producer_thread.join)
