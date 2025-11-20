# src/proactive/sentinel.py
import asyncio
from typing import Optional
from datetime import datetime
try: import pyperclip
except Exception: pyperclip = None
try: import pygetwindow as gw
except Exception: gw = None
from ..core.event_bus import EventBus
from ..core.policy import PolicyManager
from ..core.llm_async import AsyncLocalLLM

class Sentinel:
    def __init__(self, llm: AsyncLocalLLM, bus: EventBus, policy: PolicyManager, poll_sec: int = 3):
        self.llm, self.bus, self.policy, self.poll_sec = llm, bus, policy, poll_sec
        self._last_clip, self._last_title = "", ""

    def set_llm(self, llm: AsyncLocalLLM):
        self.llm = llm

    def _get_context(self) -> tuple[str, str]:
        clip = pyperclip.paste() if pyperclip else ""
        title = (w.title if (w := gw.getActiveWindow()) else "") if gw else ""
        return clip or "", title or ""

    async def _suggest(self, clip: str, title: str) -> Optional[str]:
        prompt = (f"System: You are a proactive assistant. Based on the clipboard and window title, suggest one highly relevant action in a single sentence. "
                  f"Examples: 'Summarize the copied text.' or 'Search docs for: pandas read_csv'.\n\nClipboard: {clip[:500]}\nActive Window: {title[:200]}\n\nSuggestion:")
        try: return (await self.llm.generate_async(prompt, 64, 0.4)).strip()
        except Exception: return None

    async def run(self):
        await self.bus.publish("suggestions", {"text":"Sentinel online.", "source":"sentinel"})
        while True:
            await asyncio.sleep(self.poll_sec)
            if not self.policy.proactive_enabled or self.policy.in_quiet_hours(datetime.now().hour) or not self.policy.throttle_ok():
                continue
            clip, title = self._get_context()
            if not ((clip and clip != self._last_clip) or (title and title != self._last_title)):
                continue
            self._last_clip, self._last_title = clip or self._last_clip, title or self._last_title
            if sug := await self._suggest(clip, title):
                await self.bus.publish("suggestions", {"text":sug, "source":"sentinel"})