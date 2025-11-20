import json
import asyncio
from typing import AsyncGenerator, Optional
from pydantic import ValidationError
from ..core.llm_async import AsyncLocalLLM
from ..core.prompt import react_step_prompt, final_answer_prompt
from ..core.schemas import ToolCall
from ..tools.registry_async import AsyncToolRegistry
from ..memory.vector_store import LiteVectorStore
from ..memory.conversation_store import ConversationMemory
from ..memory.graph_crdt import LWWGraph
from ..memory.inbox import MemoryInbox
from ..core.user_profile import UserProfile
from ..learning.style_adapter import StyleAdapter

def _extract_first_json(text: str) -> Optional[str]:
    start = text.find("{")
    if start == -1: return None
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{": depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0: return text[start:i+1]
    return None

class ReActAgent:
    def __init__(self, llm: AsyncLocalLLM, tools: AsyncToolRegistry, mem: ConversationMemory, kb: LiteVectorStore, graph: LWWGraph, system_prompt: str, max_steps: int, inbox: MemoryInbox, user_profile: UserProfile, style_adapter: StyleAdapter):
        self.llm, self.tools, self.mem, self.kb, self.graph, self.inbox = llm, tools, mem, kb, graph, inbox
        self.system_prompt, self.max_steps = system_prompt, max_steps
        self.profile = user_profile
        self.style_adapter = style_adapter

    async def run(self, session_id: str, user: str, cancel: asyncio.Event) -> AsyncGenerator[str, None]:
        # 1. Update style model based on user input
        self.style_adapter.analyze_message(user)
        
        # 2. Get contextual system prompt parts
        profile_prompt = self.profile.get_system_prompt_addon()
        style_prompt = self.style_adapter.get_adapted_prompt_prefix()
        
        full_system_prompt = f"{self.system_prompt} {profile_prompt} {style_prompt}".strip()
        
        scratch = self.mem.get_recent_context(session_id)
        rag = await asyncio.get_event_loop().run_in_executor(None, self.kb.retrieve_context, user, 3)
        facts = self.graph.facts_for_prompt(8)
        if facts: rag = (rag + "\n\nPersonal facts:\n" + facts).strip()
        observations = []

        for step in range(self.max_steps):
            if cancel.is_set():
                yield "\n[Stopped by user]\n"; return

            step_prompt = react_step_prompt(full_system_prompt, self.tools.list_tools(), scratch, user)
            route_text = await self.llm.generate_async(step_prompt, 220, 0.1, 0.9, 40, 1.1)

            js = _extract_first_json(route_text.strip())
            call = None
            if js:
                try: call = ToolCall.model_validate(json.loads(js))
                except ValidationError: pass

            if not call or call.tool == "none":
                full_answer = ""
                final_prompt = final_answer_prompt(full_system_prompt, scratch, rag, "\n".join(observations), user)
                async for tok in self.llm.stream_async(final_prompt, 512, 0.6, 0.9, 40, 1.1, cancel_event=cancel):
                    full_answer += tok
                    yield tok
                self.mem.add_message(session_id, user, full_answer, context="\n".join(observations))
                await self._distill_facts(user, full_answer)
                return

            thought = call.rationale or "Planning next step."
            yield f"\n---\n*Thinking:* {thought}\n*Action:* `{call.tool}` {call.args}\n---\n"

            obs = await self.tools.call(call.tool, call.args)
            observations.append(f"{call.tool} -> {obs[:800]}")
            scratch += f"\nAssistant: {json.dumps(call.model_dump(exclude_none=True))}\nObservation: {obs}"

        final_answer_text = await self.llm.generate_async(final_answer_prompt(full_system_prompt, scratch, rag, "\n".join(observations), user), 512, 0.6, 0.9, 40, 1.1)
        yield final_answer_text
        self.mem.add_message(session_id, user, final_answer_text, context="\n".join(observations))
        await self._distill_facts(user, final_answer_text)

    async def _distill_facts(self, user: str, reply: str):
        prompt = (f"System:\nExtract up to 3 factual triples about the user from the exchange if present. Output strict JSON array of {{src,rel,dst,confidence}}. Use 'User' as src for user facts; only include confidence >= 0.8.\n\nUser: {user}\nAssistant: {reply}\n\nJSON:")
        txt = await self.llm.generate_async(prompt, 200, 0.1)
        js = _extract_first_json(txt)
        if not js: return
        try:
            items = json.loads(js)
            if isinstance(items, list):
                for it in items:
                    if it.get("confidence", 0) >= 0.8:
                        self.inbox.add(str(it["src"]), str(it["rel"]), str(it["dst"]), float(it["confidence"]))
        except Exception: pass
