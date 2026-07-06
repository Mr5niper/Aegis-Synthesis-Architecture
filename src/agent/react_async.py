import json
import asyncio
from typing import AsyncGenerator, Optional
from pydantic import ValidationError
from ..core.llm_async import AsyncLocalLLM
from ..core.prompt import react_step_prompt, final_answer_prompt, build_answer_messages
from ..core.schemas import ToolCall
from ..tools.registry_async import AsyncToolRegistry
from ..memory.vector_store import LiteVectorStore
from ..memory.conversation_store import ConversationMemory
from ..memory.graph_crdt import LWWGraph
from ..memory.inbox import MemoryInbox
from ..core.user_profile import UserProfile
from ..learning.style_adapter import StyleAdapter

import datetime as _datetime

def _date_preamble() -> str:
    """A one-line statement of today's real date, prepended to the system
    prompt every turn. A local LLM has no clock and no timestamps on its own
    knowledge, so without this it cannot tell that its memorized facts are
    stale. Giving it the real date lets it judge for itself that a question
    about recent/current things needs a web lookup rather than memory."""
    today = _datetime.datetime.now()
    return (
        f"Today's date is {today:%A, %B %d, %Y}. Your built-in knowledge was "
        f"frozen well before today and has no timestamps, so for anything that "
        f"can change over time (current events, news, sports, prices, versions, "
        f"who currently holds a role, anything 'latest'/'recent'/'today'), treat "
        f"your memory as possibly out of date and use the web tools to check."
    )

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

# Stop sequences for the FINAL ANSWER generation. Small models tend to keep
# going after their reply and role-play the next turn: they write a fake user
# message (often starting "Please answer as ..." or a new "User:" line),
# answer it themselves, and append a fabricated "Sources:" list. Stopping on
# these markers ends generation at the end of the actual answer.
_ANSWER_STOP = [
    "\nUser:", "\nUser ", "\nSystem:", "\nAssistant:",
    "\nSources:", "\n\nSources:", "\nQuestion:",
    # Runaway self-conversation tells seen from the small model on the
    # fetch_url path: echoed instructions, stage directions in parentheses,
    # and fake meta-notes. Stop as soon as any of these begin a line.
    "\nPlease answer", "\nPlease respond", "\nAnswer the user",
    "\n(Note", "\n(No additional", "\n(I will", "\n(Assistant",
    "\nObservation:", "\nAction:", "\nThinking:", "\nThought:",
]

# Signals that a message needs the full ReAct pipeline (tools/RAG). If NONE of
# these are present and the message is short, we take the fast path: a single
# streamed generation with no routing call, no RAG retrieval, and no fact
# distillation. This is what makes a plain "hello" fast instead of running
# three sequential model calls.
import re as _re

# Matches an http/https URL anywhere in a message. Used so that when the user
# pastes a link ("go to this page: https://..."), the program fetches THAT page
# directly instead of sending the whole sentence to a search engine.
_URL_RE = _re.compile(r"https?://[^\s<>\"')]+", _re.IGNORECASE)

def _first_url(text: str) -> Optional[str]:
    """Return the first http(s) URL in the text, or None. Trailing sentence
    punctuation is trimmed so 'see https://x.com/page.' yields the clean URL."""
    if not text:
        return None
    m = _URL_RE.search(text)
    if not m:
        return None
    url = m.group(0).rstrip(".,;:!?)")
    return url

_TOOL_HINTS = (
    "http://", "https://", "www.", ".com", ".org", ".net", ".io",
    "search", "google", "look up", "lookup", "latest", "current",
    "today", "news", "weather", "price", "stock", "version",
    "calculate", "compute", "convert", "remember", "fetch", "url",
    "who is", "what year", "when did", "how much", "how many",
)

def _needs_full_pipeline(msg: str) -> bool:
    """Conservative gate. Return True (use full ReAct) whenever there is ANY
    hint the message might need a tool, is long, contains code, or has math.
    Only clearly simple, short, conversational messages return False."""
    if not msg:
        return False
    text = msg.strip()
    low = text.lower()
    # Long messages: let the full pipeline handle context/tools.
    if len(text) > 240 or text.count("\n") >= 3:
        return True
    # Code fences or obvious code punctuation density.
    if "```" in text or text.count(";") >= 3 or "def " in low or "import " in low:
        return True
    # Arithmetic like 2+2, 45 * 9, 100/4 -> let calc route.
    if _re.search(r"\d\s*[-+*/^]\s*\d", text):
        return True
    # Any tool-hint keyword/substring.
    if any(h in low for h in _TOOL_HINTS):
        return True
    return False

class ReActAgent:
    def __init__(self, llm: AsyncLocalLLM, tools: AsyncToolRegistry, mem: ConversationMemory, kb: LiteVectorStore, graph: LWWGraph, system_prompt: str, max_steps: int, inbox: MemoryInbox, user_profile: UserProfile, style_adapter: StyleAdapter, distill_facts: bool = True):
        self.llm, self.tools, self.mem, self.kb, self.graph, self.inbox = llm, tools, mem, kb, graph, inbox
        self.system_prompt, self.max_steps = system_prompt, max_steps
        self.profile = user_profile
        self.style_adapter = style_adapter
        self.distill_facts = distill_facts
        # Per-session web-search consent, used only when 'Allow all sites' is OFF.
        # _web_consent: session_ids that have granted consent this session.
        # _pending_web: session_id -> the original user question that triggered
        # the consent ask, so when the user says 'yes' we run the search for that
        # question WITHOUT making them type it again.
        self._web_consent = set()
        self._pending_web = {}

    @staticmethod
    def _is_affirmative(msg: str) -> bool:
        """True if the message is a short yes/go-ahead. Used only to answer a
        pending web-search consent prompt; kept tight so normal messages that
        merely contain 'yes' somewhere do not trigger it."""
        t = (msg or "").strip().lower().rstrip(".!")
        return t in {
            "yes", "y", "yeah", "yep", "yes please", "ok", "okay", "sure",
            "go", "go ahead", "do it", "do that", "yes do that", "search",
            "search it", "look it up", "please do", "proceed", "fine",
            "yes go ahead", "go for it",
        }

    async def _web_would_help(self, user: str, scratch: str) -> bool:
        """Ask the model a single, cheap yes/no as a strict 1 or 0: would
        answering this well benefit from a live web search? This replaces
        brittle keyword lists with the model's own judgment, and demanding a
        single digit keeps parsing unambiguous (a plain 'hello' should give 0).

        Returns True only when the model's first character is '1'; anything else
        (0, blank, or garbled output) is treated as NO, so it errs toward NOT
        searching rather than searching on noise.
        """
        today = _datetime.datetime.now().strftime("%A, %B %d, %Y")
        prompt = (
            f"Today is {today}. Decide whether answering the user's message well "
            f"would need a live web search (for current, recent, changing, or "
            f"factual-lookup information that may be out of date), as opposed to "
            f"small talk, general knowledge, or a question about yourself.\n"
            f"Recent conversation (for context):\n{scratch or '(none)'}\n\n"
            f"User message: {user}\n\n"
            f"Respond with a single character and nothing else: 1 if a web search "
            f"is needed, or 0 if it is not. Answer:"
        )
        try:
            txt = (await self.llm.generate_async(prompt, 2, 0.0)).strip()
        except Exception as e:
            print(f"[web?] classifier error: {type(e).__name__}: {e}; defaulting to 0 (NO)")
            return False
        # Strict: only a leading '1' counts as yes. Everything else -> no.
        decision = txt[:1] == "1"
        print(f"[web?] would web help? -> {'YES (1)' if decision else 'NO (0)'} (model said {txt!r})")
        return decision

    async def _answer_with_research(self, session_id: str, user: str, full_system_prompt: str,
                                    scratch: str, rag: str, cancel: asyncio.Event):
        """Get web content, then stream an answer grounded in it plus local
        knowledge. Enforced in code so the model cannot skip or fake the lookup.

        Two paths:
          - If the message contains a URL, FETCH THAT PAGE DIRECTLY (fetch_url).
            This is what "go to this page: https://..." needs; it does not touch
            the search engine at all, so it works even when search is rate-limited.
          - Otherwise, run the search-based research loop.

        Degrades gracefully: on timeout / error / empty result, fall back to a
        local answer and say so, instead of hanging or pretending it looked."""
        budget = max(15, int(self.tools.cfg.assistant.tool_timeout_sec) + 10)
        url = _first_url(user)
        obs = ""
        try:
            if url:
                # Direct fetch of the pasted link. Bypasses search entirely.
                print(f"[web?] message has a URL -> fetching directly: {url}")
                page = await asyncio.wait_for(
                    self.tools.call("fetch_url", {"url": url}), timeout=budget)
                if page and not page.startswith("[Blocked") and not page.startswith("[Error"):
                    # For a SINGLE fetched page, do NOT aggressively keyword-trim
                    # it: that is what silently discarded the answer before (e.g.
                    # asking "what year did it come out" scored zero against a
                    # page whose label reads "Publication date", so the old
                    # extract_relevant returned the page header/nav and the date
                    # was never shown to the model). The model has a large
                    # context and is far better than a word-count heuristic at
                    # finding the asked-for detail, so hand it a big slice of the
                    # page and let it read. We still cap the size so we never
                    # blow the context or stall. (The multi-result research loop
                    # still uses extract_relevant per page, since it cannot fit
                    # several full pages.)
                    PAGE_CHARS = 6000
                    body = page[:PAGE_CHARS]
                    truncated = " [page truncated]" if len(page) > PAGE_CHARS else ""
                    obs = (f"Fetched page: {url}\n"
                           f"Full page text below; find the specific detail the "
                           f"user asked about.{truncated}\n\n{body}")
                else:
                    # Blocked/error: keep the status so we report honestly.
                    obs = page or ""
                print(f"[web?] fetch_url returned {len(obs)} chars; head={obs[:120]!r}")
            else:
                obs = await asyncio.wait_for(
                    self.tools.call("research_web", {"query": user, "k": 4}), timeout=budget)
                print(f"[web?] research_web returned {len(obs)} chars; head={obs[:120]!r}")
        except asyncio.TimeoutError:
            obs = ""
            print("[web?] web step timed out; falling back to local answer")
        except Exception as e:
            obs = ""
            print(f"[web?] web step error: {type(e).__name__}: {e}; local fallback")

        # Detect an unusable result (empty, rate-limited note, blocked, or error)
        # so we can tell the user honestly rather than dress up stale memory.
        stripped = obs.strip()
        unusable = (
            (not stripped)
            or stripped.startswith("No search results")
            or stripped.startswith("[Blocked")
            or stripped.startswith("[Error")
        )
        note = ""
        observations = "" if unusable else obs
        if unusable:
            if url:
                note = (f"\n\n(Note: I could not read {url} just now"
                        + (f" - {stripped}" if stripped else "")
                        + ". This answer is from my local knowledge and may be "
                        "out of date.)")
            else:
                note = ("\n\n(Note: I could not reach the web just now, so this "
                        "answer is from my local knowledge and may be out of date.)")

        full_answer = ""
        sys_with_ctx = full_system_prompt
        if scratch:
            sys_with_ctx = full_system_prompt + "\n\nRecent conversation:\n" + scratch
        messages = build_answer_messages(sys_with_ctx, [], rag, observations, user)
        async for tok in self.llm.stream_chat_async(messages, 512, 0.6, 0.9, 40, 1.1,
                                                     stop=_ANSWER_STOP, cancel_event=cancel):
            full_answer += tok
            yield tok
        if note:
            yield note
            full_answer += note
        self.mem.add_message(session_id, user, full_answer, context=observations)
        await self._maybe_distill_facts(user, full_answer)

    async def run(self, session_id: str, user: str, cancel: asyncio.Event) -> AsyncGenerator[str, None]:
        # 1. Update style model based on user input
        self.style_adapter.analyze_message(user)

        # CONSENT REPLY: if this session is waiting on a yes/no for web-search
        # consent (asked once when 'Allow all sites' is OFF) and the user just
        # said yes, grant consent for the session and resume the ORIGINAL
        # question they asked, so they never have to type it twice. A 'no' (or
        # anything not affirmative) clears the pending state and is handled as a
        # normal message.
        resumed_from_consent = False
        pending = self._pending_web.get(session_id)
        if pending is not None:
            self._pending_web.pop(session_id, None)
            if self._is_affirmative(user):
                self._web_consent.add(session_id)
                user = pending  # resume the original question
                resumed_from_consent = True
            # else: fall through and treat the new message normally.

        # 2. Contextual system prompt parts, needed by every branch below.
        profile_prompt = self.profile.get_system_prompt_addon()
        style_prompt = self.style_adapter.get_adapted_prompt_prefix()
        full_system_prompt = f"{_date_preamble()} {self.system_prompt} {profile_prompt} {style_prompt}".strip()
        scratch = self.mem.get_recent_context(session_id)

        # DECIDE WITH JUDGMENT, NOT KEYWORDS: ask the model a single cheap yes/no
        # -- would a live web search help answer this? This replaces the old
        # keyword gate. The PROGRAM then controls what happens based on the
        # answer and the web-access setting, so the model never gets to silently
        # refuse to search.
        #   - resumed_from_consent means the user already said 'yes' to searching
        #     a prior question, so we skip the classifier and go straight to
        #     research.
        web_helps = resumed_from_consent or await self._web_would_help(user, scratch)

        if web_helps:
            # RAG/personal facts still enrich the grounded answer.
            rag = await asyncio.get_event_loop().run_in_executor(None, self.kb.retrieve_context, user, 3)
            facts = self.graph.facts_for_prompt(8)
            if facts:
                rag = (rag + "\n\nPersonal facts:\n" + facts).strip()

            if self.tools.web_open() or session_id in self._web_consent or resumed_from_consent:
                # Web is allowed: the program runs the research directly and the
                # model answers from the results (it cannot skip the search).
                print("[web?] web allowed -> running research directly")
                async for tok in self._answer_with_research(
                        session_id, user, full_system_prompt, scratch, rag, cancel):
                    yield tok
                return
            else:
                # Web is restricted ('Allow all sites' off) and no consent yet:
                # answer locally first, then ask one-time consent. On 'yes' the
                # next turn resumes via resumed_from_consent above.
                print("[web?] web would help but access is restricted -> local answer + consent ask")
                full_answer = ""
                sys_with_ctx = full_system_prompt
                if scratch:
                    sys_with_ctx = full_system_prompt + "\n\nRecent conversation:\n" + scratch
                messages = build_answer_messages(sys_with_ctx, [], rag, "", user)
                async for tok in self.llm.stream_chat_async(messages, 512, 0.6, 0.9, 40, 1.1,
                                                            stop=_ANSWER_STOP, cancel_event=cancel):
                    full_answer += tok
                    yield tok
                warning = self.tools.consent_warning()
                yield warning
                self._pending_web[session_id] = user
                self.mem.add_message(session_id, user, full_answer + warning, context="")
                return

        # web_helps == False: no web needed. Fast local answer (one generation).
        print("[web?] no web needed -> fast local answer")
        async for tok in self._fast_answer(session_id, user, cancel):
            yield tok
        return

    async def _run_legacy_react(self, session_id: str, user: str, cancel: asyncio.Event) -> AsyncGenerator[str, None]:
        # 2. Get contextual system prompt parts (full ReAct path below).
        profile_prompt = self.profile.get_system_prompt_addon()
        style_prompt = self.style_adapter.get_adapted_prompt_prefix()

        full_system_prompt = f"{_date_preamble()} {self.system_prompt} {profile_prompt} {style_prompt}".strip()

        scratch = self.mem.get_recent_context(session_id)
        rag = await asyncio.get_event_loop().run_in_executor(None, self.kb.retrieve_context, user, 3)
        facts = self.graph.facts_for_prompt(8)
        if facts: rag = (rag + "\n\nPersonal facts:\n" + facts).strip()
        observations = []
        seen_actions = set()  # signatures of (tool, args) already executed

        for step in range(self.max_steps):
            if cancel.is_set():
                yield "\n[Stopped by user]\n"; return

            step_prompt = react_step_prompt(full_system_prompt, self.tools.list_tools(), scratch, user)
            # Hard stop sequences for the router: the model must emit ONE JSON
            # object and stop. Small models otherwise keep going and hallucinate
            # a whole fake transcript (Observation:/Assistant:/User: lines, made-
            # up tool calls and URLs). Stopping on a blank line or any of those
            # role markers ends generation right after the JSON object.
            route_stop = ["\n\n", "\nObservation:", "\nAssistant:", "\nUser:", "\nSystem:"]
            route_text = await self.llm.generate_async(step_prompt, 220, 0.1, 0.9, 40, 1.1, stop=route_stop)

            js = _extract_first_json(route_text.strip())
            call = None
            if js:
                try: call = ToolCall.model_validate(json.loads(js))
                except ValidationError: pass

            # Visibility: print what the router decided so failures are diagnosable
            # from the console instead of guessed at. Shows the chosen tool (or
            # 'none'/unparsed) and the raw router text when nothing parsed.
            if call and call.tool != "none":
                print(f"[route] step {step}: tool={call.tool} args={call.args}")
            else:
                _parsed = "none" if (call and call.tool == "none") else "UNPARSED"
                print(f"[route] step {step}: {_parsed} (no tool) :: router said: {route_text.strip()[:160]!r}")

            if not call or call.tool == "none":
                full_answer = ""
                sys_with_ctx = full_system_prompt
                if scratch:
                    sys_with_ctx = full_system_prompt + "\n\nRecent conversation:\n" + scratch
                messages = build_answer_messages(sys_with_ctx, [], rag, "\n".join(observations), user)
                async for tok in self.llm.stream_chat_async(messages, 512, 0.6, 0.9, 40, 1.1, stop=_ANSWER_STOP, cancel_event=cancel):
                    full_answer += tok
                    yield tok
                self.mem.add_message(session_id, user, full_answer, context="\n".join(observations))
                await self._maybe_distill_facts(user, full_answer)
                return

            # Loop guard: if the model picks a tool call it has already run
            # (same tool + same args), it is stuck repeating itself instead of
            # answering. Stop iterating and compose the final answer from the
            # observations gathered so far rather than burning more steps.
            sig = f"{call.tool}:{json.dumps(call.args, sort_keys=True)}"
            if sig in seen_actions:
                break
            seen_actions.add(sig)

            # The model's step reasoning (rationale) and the raw tool call are
            # internal scratch-work, NOT part of the user-facing answer. They
            # used to be streamed into the chat here, which glued a
            # "Thinking:/Action:" block onto the front of the reply (visible on
            # any tool-using turn). We deliberately do NOT yield them: the chat
            # bubble should contain only the final answer. The tool still runs
            # below, and the rationale/observations still feed the model via the
            # scratchpad - the user just doesn't see the plumbing.

            # WEB CONSENT GATE (one time per session, only when 'Allow all
            # sites' is OFF). The router choosing a web tool is the signal that a
            # search is warranted. If web access is not open and this session has
            # not yet consented, do NOT search silently: first give the best
            # local answer so the user is not left waiting, then show the warning
            # and ask permission once. We remember the original question so a
            # 'yes' resumes it without re-asking. Enforced here in code, so both
            # models behave the same regardless of prompt-following.
            if (call.tool in self.tools.WEB_TOOLS
                    and not self.tools.web_open()
                    and session_id not in self._web_consent):
                # Local-first answer from the model's own knowledge.
                full_answer = ""
                sys_with_ctx = full_system_prompt
                if scratch:
                    sys_with_ctx = full_system_prompt + "\n\nRecent conversation:\n" + scratch
                messages = build_answer_messages(sys_with_ctx, [], rag, "\n".join(observations), user)
                async for tok in self.llm.stream_chat_async(messages, 512, 0.6, 0.9, 40, 1.1, stop=_ANSWER_STOP, cancel_event=cancel):
                    full_answer += tok
                    yield tok
                # Ask for consent once; remember the question to resume on 'yes'.
                warning = self.tools.consent_warning()
                yield warning
                self._pending_web[session_id] = user
                self.mem.add_message(session_id, user, full_answer + warning, context="\n".join(observations))
                return

            obs = await self.tools.call(call.tool, call.args)
            print(f"[route] ran {call.tool}: {len(obs)} chars returned; head={obs[:120]!r}")
            observations.append(f"{call.tool} -> {obs[:800]}")
            scratch += f"\nAssistant: {json.dumps(call.model_dump(exclude_none=True))}\nObservation: {obs}"

        # Reached here by exhausting max_steps or by the loop guard above.
        # Stream the final answer using whatever observations were gathered.
        full_answer = ""
        sys_with_ctx = full_system_prompt
        if scratch:
            sys_with_ctx = full_system_prompt + "\n\nRecent conversation:\n" + scratch
        messages = build_answer_messages(sys_with_ctx, [], rag, "\n".join(observations), user)
        async for tok in self.llm.stream_chat_async(messages, 512, 0.6, 0.9, 40, 1.1, stop=_ANSWER_STOP, cancel_event=cancel):
            full_answer += tok
            yield tok
        self.mem.add_message(session_id, user, full_answer, context="\n".join(observations))
        await self._maybe_distill_facts(user, full_answer)

    async def _fast_answer(self, session_id: str, user: str, cancel: asyncio.Event) -> AsyncGenerator[str, None]:
        """Single-generation answer for simple messages. No routing, no RAG, no
        distillation. Still records the turn so conversation history is intact."""
        profile_prompt = self.profile.get_system_prompt_addon()
        style_prompt = self.style_adapter.get_adapted_prompt_prefix()
        full_system_prompt = f"{_date_preamble()} {self.system_prompt} {profile_prompt} {style_prompt}".strip()
        # Include only recent conversation for continuity; no RAG/observations.
        scratch = self.mem.get_recent_context(session_id)
        # Fold prior-conversation context into the system message; the current
        # user message is a proper chat turn. Uses the model native chat
        # template so it stops at its own end-of-turn token.
        sys_with_ctx = full_system_prompt
        if scratch:
            sys_with_ctx = full_system_prompt + "\n\nRecent conversation:\n" + scratch
        messages = build_answer_messages(sys_with_ctx, [], "", "", user)
        full_answer = ""
        async for tok in self.llm.stream_chat_async(messages, 512, 0.6, 0.9, 40, 1.1, stop=_ANSWER_STOP, cancel_event=cancel):
            full_answer += tok
            yield tok
        self.mem.add_message(session_id, user, full_answer, context="")
        # Deliberately NO _maybe_distill_facts here: the fast path is for simple
        # chatter, and distillation is the extra per-turn model call we are
        # avoiding. Fact extraction still runs on full-pipeline turns.

    async def _maybe_distill_facts(self, user: str, reply: str):
        # Skipping this saves one full LLM generation per chat turn.
        if not self.distill_facts:
            return
        await self._distill_facts(user, reply)

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
