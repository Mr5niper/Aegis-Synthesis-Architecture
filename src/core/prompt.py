# Tool descriptions shown to the router so the model knows WHAT each tool does
# and WHEN to use it. Keep this in sync with AsyncToolRegistry.
TOOL_DESCRIPTIONS = {
    "search_web": "Search the live internet and get a list of result links with short snippets. Use when you just need to find pages. args: {\"query\": \"...\", \"k\": 5}",
    "research_web": "Search the web AND read the top results, returning what each source says with its URL. Use this for most 'look it up' / 'search online' / current-info questions, because it finds the answer and the source in one step. args: {\"query\": \"...\", \"k\": 4}",
    "fetch_url": "Download and read the text of a specific web page. args: {\"url\": \"https://...\"}",
    "ingest_url": "Download a web page and store it in the knowledge base for later. args: {\"url\": \"https://...\"}",
    "calc": "Evaluate a arithmetic expression exactly. args: {\"expr\": \"23 * 456\"}",
    "now": "Get the current local date and time. args: {}",
    "kb_query": "Search the user's private local knowledge base. args: {\"query\": \"...\", \"k\": 3}",
    "kb_add": "Store a piece of text in the local knowledge base. args: {\"text\": \"...\", \"source\": \"...\"}",
    "code_exec": "Run a short Python snippet in a sandbox. args: {\"code\": \"...\"}",
    "none": "Use this when you already know the answer and no tool is needed.",
}

TOOLS_SCHEMA = """To use a tool, output ONLY a single JSON object on one line, with this exact schema and NOTHING else:
{ "tool": "<tool_name>", "args": { ... }, "rationale": "<one short sentence>" }
If no tool is needed because you can answer directly, output exactly:
{ "tool": "none", "args": {}, "rationale": "I can answer directly." }

Output the single JSON object and then STOP. Do not write an Observation,
do not write the answer, do not continue the conversation, do not invent
further turns. Exactly one JSON object, nothing before or after it."""

# Few-shot examples steer small models hard. The web-search examples are the
# ones that were previously missing, which is why the model rarely searched.
ROUTER_EXAMPLES = """Examples:
User: What is 19% of 240?
{ "tool": "calc", "args": { "expr": "240 * 0.19" }, "rationale": "Exact arithmetic." }

User: Who won the F1 race last weekend?
{ "tool": "research_web", "args": { "query": "F1 race winner last weekend", "k": 4 }, "rationale": "Recent event; find it and read the sources." }

User: What's the latest stable version of Python?
{ "tool": "research_web", "args": { "query": "latest stable Python version", "k": 4 }, "rationale": "Version info changes; look it up and cite." }

User: Summarize what's on this page https://example.com/post
{ "tool": "fetch_url", "args": { "url": "https://example.com/post" }, "rationale": "Need the page contents." }

User: you have web access can you check espn.com
{ "tool": "fetch_url", "args": { "url": "https://espn.com" }, "rationale": "User asked me to read a specific site; add https:// to the bare domain." }

User: can you look at what's on wikipedia.org about otters
{ "tool": "search_web", "args": { "query": "otters site:wikipedia.org", "k": 5 }, "rationale": "Named site plus a topic; search it live." }

User: check the news on cnn.com
{ "tool": "fetch_url", "args": { "url": "https://cnn.com" }, "rationale": "User named a site to read; fetch it." }

User: who did the Portland Trail Blazers just trade for?
{ "tool": "research_web", "args": { "query": "Portland Trail Blazers latest trade 2026", "k": 4 }, "rationale": "Recent event; my memory is not current, look it up." }

User: what's the newest iPhone?
{ "tool": "research_web", "args": { "query": "newest iPhone model", "k": 4 }, "rationale": "Product lineup changes; verify online." }

User: search online for that
{ "tool": "research_web", "args": { "query": "<the topic from the recent conversation>", "k": 4 }, "rationale": "User explicitly asked to search." }

User: What time is it?
{ "tool": "now", "args": {}, "rationale": "Needs the current clock." }

User: Write me a haiku about the sea.
{ "tool": "none", "args": {}, "rationale": "Creative task, no tool needed." }

User: Hello, what is your name?
{ "tool": "none", "args": {}, "rationale": "I can answer about myself directly." }

User: What can you do?
{ "tool": "none", "args": {}, "rationale": "Question about myself, answer directly." }"""


def _tool_menu(tools_list: list[str]) -> str:
    lines = []
    for name in tools_list:
        desc = TOOL_DESCRIPTIONS.get(name, "(no description)")
        lines.append(f"- {name}: {desc}")
    return "\n".join(lines)


def react_step_prompt(system: str, tools_list: list[str], scratchpad: str, user: str) -> str:
    return (
        f"System:\n{system}\n\n"
        f"You can call ONE tool to help answer the user. Available tools:\n"
        f"{_tool_menu(tools_list)}\n\n"
        f"{TOOLS_SCHEMA}\n\n"
        f"Guidance: Your built-in knowledge is FROZEN at training time and is "
        f"NOT up to date. For anything that could have changed or happened "
        f"recently - current events, news, sports scores or trades, prices, "
        f"stock quotes, software versions, 'latest' or 'current' or 'today' or "
        f"'this year', who currently holds a role, or 'who just did X' - you do "
        f"NOT know the answer from memory and you MUST use research_web to look "
        f"it up. Do not answer these from memory and do not say you searched "
        f"unless a tool result is actually present in the observations. If you "
        f"are not certain your memorized answer is still correct today, use "
        f"research_web.\n"
        f"For genuinely timeless things - greetings, small talk, questions about "
        f"yourself, opinions, explanations, definitions, math, writing - choose "
        f"\"none\" and answer directly. Never use kb_add or kb_query for simple "
        f"conversational questions; the knowledge base is only for information "
        f"the user explicitly asked you to store or look up.\n"
        f"Tool choice: research_web for most 'look it up' / 'search online' / "
        f"current-info questions (it searches and reads the top results so you "
        f"can answer with a source); search_web if you only need a list of "
        f"links; calc for arithmetic; now for the current time; fetch_url for "
        f"one specific page. When the user names a website or asks you to check, "
        f"open, read, or look at a site (even a bare domain like \"espn.com\"), "
        f"you DO have web access through these tools: use fetch_url for that "
        f"page (add \"https://\" to a bare domain), or research_web if they name "
        f"a site plus a topic. Never reply that you cannot access the internet "
        f"or a website; the tools above are your web access.\n\n"
        f"{ROUTER_EXAMPLES}\n\n"
        f"Conversation and observations so far:\n{scratchpad}\n\n"
        f"User: {user}\n"
        f"Respond with the JSON object only:"
    )


def final_answer_prompt(system: str, chat: str, rag: str, observations: str, user: str) -> str:
    # The style instruction goes in the SYSTEM block, not just before the answer.
    # Small models parrot whatever instruction sits right before the generation
    # point, so putting "answer in plain English" at the end made it echo that
    # sentence verbatim. Kept high up, it steers without being copied.
    style = (
        "You are answering a person in a chat. Reply with a single, direct answer "
        "in plain, natural English prose. Do NOT output JSON, key/value pairs, code "
        "blocks, curly braces, or field names. Do NOT write \"Observation\", "
        "\"Action\", \"Note\", stage directions in parentheses, or any further "
        "turns of dialogue. Write the answer and then stop."
    )
    parts = [f"System:\n{system}\n\n{style}"]
    if chat:
        parts.append("Recent conversation:\n" + chat)
    if rag:
        parts.append("Knowledge context:\n" + rag)
    if observations:
        parts.append("Tool observations (use these for your answer; cite URLs when present):\n" + observations)
    parts.append("User:\n" + user + "\nAssistant:")
    return "\n\n".join(parts)


def build_answer_messages(system: str, history: list, rag: str, observations: str, user: str) -> list:
    """Build a messages list for the model's native chat template
    (create_chat_completion). This replaces the flat User:/Assistant: string
    format the models were never trained on. history is a list of prior turns
    as {'role': 'user'|'assistant', 'content': str}; rag/observations are folded
    into the system message as context so they do not pollute the turn roles.
    """
    style = (
        "You are answering a person in a chat. Reply with a single, direct answer "
        "in plain, natural English prose. Do NOT output JSON, key/value pairs, code "
        "blocks, curly braces, or field names. Do NOT write \"Observation\", "
        "\"Action\", \"Note\", stage directions in parentheses, or any further "
        "turns of dialogue. Write the answer and then stop."
    )
    sys_content = f"{system}\n\n{style}"
    if rag:
        sys_content += "\n\nKnowledge context:\n" + rag
    if observations:
        sys_content += ("\n\nTool observations (use these for your answer; cite "
                        "URLs when present):\n" + observations)
    messages = [{"role": "system", "content": sys_content}]
    # Prior conversation turns, if any, so the template frames real multi-turn.
    for turn in (history or []):
        role = turn.get("role")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user})
    return messages
