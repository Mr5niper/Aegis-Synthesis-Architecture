# src/proactive/curator.py
import asyncio
from ..core.event_bus import EventBus
from ..core.policy import PolicyManager
from ..core.llm_async import AsyncLocalLLM
from ..memory.graph_crdt import LWWGraph
from ..memory.vector_store import LiteVectorStore

class Curator:
    def __init__(self, llm: AsyncLocalLLM, bus: EventBus, policy: PolicyManager, graph: LWWGraph, kb: LiteVectorStore, interval_sec: int = 300):
        self.llm, self.bus, self.policy, self.graph, self.kb, self.interval = llm, bus, policy, graph, kb, interval_sec

    def set_llm(self, llm: AsyncLocalLLM):
        self.llm = llm

    async def run(self):
        await self.bus.publish("suggestions", {"text":"Curator online.", "source":"curator"})
        while True:
            await asyncio.sleep(self.interval)
            if not self.policy.proactive_enabled or not self.policy.throttle_ok() or not (facts := self.graph.facts_for_prompt(20)):
                continue
            prompt = (f"System: Analyze the user's facts and suggest one valuable next action, concise and actionable. "
                      f"Examples: 'Tag KB notes about project X for quick access?' or 'Ingest docs for library Y?'\n\nFacts:\n{facts}\n\nSuggestion:")
            try:
                if suggestion := (await self.llm.generate_async(prompt, 96, 0.5)).strip():
                    await self.bus.publish("suggestions", {"text":suggestion, "source":"curator"})
            except Exception:
                pass